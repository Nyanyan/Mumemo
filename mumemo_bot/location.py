from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import time
import unicodedata

import requests


UNKNOWN_LOCATION = "不明"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.1
_RATE_LOCK = Lock()
_LAST_REQUEST_AT = 0.0


class LocationInferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocationInference:
    location: str
    source: str
    matched: str
    query: str


def normalize_location(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not normalized or normalized.casefold() in {"unknown", "none", "null", "-"}:
        return UNKNOWN_LOCATION
    if normalized in {UNKNOWN_LOCATION, "不詳", "未設定"}:
        return UNKNOWN_LOCATION
    return normalized


def infer_location(
    title: str,
    body: str = "",
    *,
    nominatim_user_agent: str,
    nominatim_email: str = "",
    nominatim_endpoint: str = NOMINATIM_SEARCH_URL,
    timeout_seconds: float = 10.0,
) -> str:
    return infer_location_detail(
        title,
        body,
        nominatim_user_agent=nominatim_user_agent,
        nominatim_email=nominatim_email,
        nominatim_endpoint=nominatim_endpoint,
        timeout_seconds=timeout_seconds,
    ).location


def infer_location_detail(
    title: str,
    body: str = "",
    *,
    nominatim_user_agent: str,
    nominatim_email: str = "",
    nominatim_endpoint: str = NOMINATIM_SEARCH_URL,
    timeout_seconds: float = 10.0,
) -> LocationInference:
    query = _nominatim_query(title, body)
    if not query:
        return _location_result(UNKNOWN_LOCATION, "nominatim_empty_query", "", "")

    endpoint = str(nominatim_endpoint or "").strip() or NOMINATIM_SEARCH_URL
    user_agent = str(nominatim_user_agent or "").strip()
    if not user_agent:
        raise LocationInferenceError("MUMEMO_NOMINATIM_USER_AGENT is required")

    params: dict[str, str | int] = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "accept-language": "ja",
    }
    email = str(nominatim_email or "").strip()
    if email:
        params["email"] = email

    print(
        "[location:nominatim] request: "
        f"query={query!r}, endpoint={endpoint!r}, email_configured={bool(email)}",
        flush=True,
    )

    _wait_for_rate_limit()
    try:
        response = requests.get(
            endpoint,
            params=params,
            headers={"User-Agent": user_agent},
            timeout=max(0.5, float(timeout_seconds or 10.0)),
        )
        response.raise_for_status()
        payload = response.json()
    except (ValueError, requests.RequestException) as error:
        print(
            "[location:nominatim] failed: "
            f"query={query!r}, error={type(error).__name__}: {error}",
            flush=True,
        )
        raise LocationInferenceError(f"Nominatim request failed: {type(error).__name__}: {error}") from error

    if not isinstance(payload, list):
        raise LocationInferenceError("Nominatim response must be a JSON array")
    if not payload:
        return _location_result(UNKNOWN_LOCATION, "nominatim_no_results", "", query)

    first_result = payload[0]
    if not isinstance(first_result, dict):
        raise LocationInferenceError("Nominatim result must be an object")

    address = first_result.get("address")
    if not isinstance(address, dict):
        return _location_result(UNKNOWN_LOCATION, "nominatim_no_address", _display_name(first_result), query)

    country_code = str(address.get("country_code") or "").casefold()
    if country_code == "jp":
        for address_key in ("state", "province", "region"):
            administrative_area = _address_value(address, address_key)
            if administrative_area:
                return _location_result(
                    normalize_location(administrative_area),
                    f"nominatim_{address_key}",
                    _display_name(first_result),
                    query,
                )
        return _location_result(UNKNOWN_LOCATION, "nominatim_japan_without_administrative_area", _display_name(first_result), query)

    country = _address_value(address, "country")
    if country:
        return _location_result(normalize_location(country), "nominatim_country", _display_name(first_result), query)

    return _location_result(UNKNOWN_LOCATION, "nominatim_no_country", _display_name(first_result), query)


def _nominatim_query(title: str, _body: str) -> str:
    return unicodedata.normalize("NFKC", str(title or "")).strip()[:180]


def _location_result(location: str, source: str, matched: str, query: str) -> LocationInference:
    result = LocationInference(location, source, matched, query)
    print(
        "[location:nominatim] result: "
        f"location={result.location!r}, source={result.source!r}, "
        f"matched={result.matched!r}, query={result.query!r}",
        flush=True,
    )
    return result


def _address_value(address: dict[object, object], key: str) -> str:
    value = address.get(key)
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _display_name(result: dict[object, object]) -> str:
    return unicodedata.normalize("NFKC", str(result.get("display_name") or "")).strip()


def _wait_for_rate_limit() -> None:
    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        elapsed = time.monotonic() - _LAST_REQUEST_AT
        wait_seconds = NOMINATIM_MIN_INTERVAL_SECONDS - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _LAST_REQUEST_AT = time.monotonic()
