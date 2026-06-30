from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote, unquote, urlparse
import json
import mimetypes
import re
import shutil
import subprocess
import unicodedata

import requests
from PIL import Image, ImageOps

from mumemo_bot.config import BotConfig, PROJECT_ROOT
from mumemo_bot.location import UNKNOWN_LOCATION, infer_location, normalize_location
from mumemo_bot.slack_post import MumemoSlackPost, SlackImageFile


_STORE_LOCK = Lock()
PROTECTED_ROUTE_DIRS = {"assets", "data", "locations"}
THUMBNAIL_SIZE = (640, 640)
THUMBNAIL_QUALITY = 82
DETAIL_IMAGE_MAX_SIZE = 1024
DETAIL_IMAGE_QUALITY = 86
DETAIL_IMAGE_DIRNAME = "display"
ORIGINAL_IMAGE_KEY = "originalImage"
ORIGINAL_IMAGES_KEY = "originalImages"


@dataclass(frozen=True)
class SavedImage:
    file_id: str
    source_name: str
    path: Path
    url: str
    original_url: str | None = None
    thumbnail_path: Path | None = None
    thumbnail_url: str | None = None
    display_path: Path | None = None
    display_url: str | None = None


@dataclass(frozen=True)
class StoreResult:
    created: bool
    title: str
    image_count: int
    data_path: Path
    memo_id: str | None = None
    page_url: str | None = None
    location: str = ""


@dataclass(frozen=True)
class MemoListItem:
    id: str
    title: str
    body: str
    image: str
    images: list[str]
    image_count: int
    location: str
    fixed: bool


@dataclass(frozen=True)
class MemoChangeResult:
    title: str
    image_count: int
    data_path: Path


class MemoNotFoundError(RuntimeError):
    pass


class ProtectedMemoError(RuntimeError):
    pass


def save_post_as_memo(
    config: BotConfig,
    post: MumemoSlackPost,
    *,
    location: str | None = None,
) -> StoreResult:
    config.data_path.parent.mkdir(parents=True, exist_ok=True)
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        existing = _find_existing_slack_memo(memos, post)
        if existing is not None:
            existing_index = memos.index(existing)
            memo_id = _memo_ids(memos)[existing_index]
            return StoreResult(
                created=False,
                title=str(existing.get("title") or post.title),
                image_count=_memo_image_count(existing),
                data_path=config.data_path,
                memo_id=memo_id,
                page_url=_memo_page_url(config, memos, existing_index),
                location=_memo_location(existing),
            )

    saved_images = download_images(
        bot_token=config.slack_bot_token,
        post=post,
        asset_dir=config.asset_dir,
        asset_url_prefix=config.asset_url_prefix,
        original_asset_dir=config.original_asset_dir,
        github_repo_url=config.github_repo_url,
        github_branch=config.github_branch,
    )

    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        existing = _find_existing_slack_memo(memos, post)
        if existing is not None:
            existing_index = memos.index(existing)
            memo_id = _memo_ids(memos)[existing_index]
            return StoreResult(
                created=False,
                title=str(existing.get("title") or post.title),
                image_count=_memo_image_count(existing),
                data_path=config.data_path,
                memo_id=memo_id,
                page_url=_memo_page_url(config, memos, existing_index),
                location=_memo_location(existing),
            )

        memo = _memo_from_post(config, post, saved_images, location=location)
        if _has_title_conflict(memos, post):
            memo["slug"] = _next_duplicate_slug(memos, post.title)
        insert_index = _new_memo_insert_index(memos)
        memos.insert(insert_index, memo)
        _write_memos(config.data_path, memos)
        build_route_pages(config)
        memo_id = _memo_ids(memos)[insert_index]
        page_url = _memo_page_url(config, memos, insert_index)

    return StoreResult(
        created=True,
        title=post.title,
        image_count=len(saved_images),
        data_path=config.data_path,
        memo_id=memo_id,
        page_url=page_url,
        location=_memo_location(memo),
    )


def list_memos(
    config: BotConfig,
    *,
    include_fixed: bool = False,
    limit: int | None = None,
) -> list[MemoListItem]:
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        ids = _memo_ids(memos)
        items = [
            _list_item(memo, ids[index])
            for index, memo in enumerate(memos)
            if include_fixed or not bool(memo.get("fixed"))
        ]
    if limit is None:
        return items
    return items[:limit]


def get_memo(config: BotConfig, memo_id: str) -> MemoListItem:
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        return _list_item(memos[index], _memo_ids(memos)[index])


def find_title_conflict(config: BotConfig, post: MumemoSlackPost) -> MemoListItem | None:
    title_key = _title_key(post.title)
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        ids = _memo_ids(memos)
        for index, memo in enumerate(memos):
            if bool(memo.get("fixed")):
                continue
            if _same_slack_source(memo, post):
                continue
            if _title_key(str(memo.get("title") or "")) == title_key:
                return _list_item(memo, ids[index])
    return None


def update_memo(
    config: BotConfig,
    *,
    memo_id: str,
    title: str,
    body: str,
    image: str,
    images: list[str],
    original_images: list[str] | None = None,
    new_original_images_by_image: dict[str, str] | None = None,
    location: str | None = None,
) -> MemoChangeResult:
    title = title.strip()
    if not title:
        raise ValueError("タイトルは空にできません")

    clean_images = _clean_image_list(images)
    clean_image = image.strip() or (clean_images[0] if clean_images else config.default_image)
    clean_location = _location_for_update(config, title, body, location)
    thumbnail = _thumbnail_url_for_image_url(config, clean_image)
    _ensure_detail_images_for_urls(config, clean_images or [clean_image])

    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        old_memos = [dict(item) for item in memos]
        old_memo = dict(memos[index])
        memo = memos[index]
        old_original_image_map = _original_image_map(old_memo)
        if new_original_images_by_image:
            old_original_image_map.update(
                {
                    image_url.strip(): original_url.strip()
                    for image_url, original_url in new_original_images_by_image.items()
                    if image_url.strip() and original_url.strip()
                }
            )
        clean_original_images = (
            _clean_image_list(original_images)
            if original_images is not None
            else _align_original_images(clean_images, old_original_image_map)
        )

        memo["id"] = str(memo.get("id") or memo_id)
        memo["title"] = title
        memo["body"] = body
        memo["location"] = clean_location
        memo["image"] = clean_image
        if thumbnail:
            memo["thumbnail"] = thumbnail
        else:
            memo.pop("thumbnail", None)
        if clean_images:
            memo["images"] = clean_images
        else:
            memo.pop("images", None)
        _set_original_image_fields(memo, clean_image, clean_images, clean_original_images)

        _write_memos(config.data_path, memos)
        build_route_pages(config)
        _cleanup_replaced_memo(config, old_memos, old_memo, memos)

    return MemoChangeResult(
        title=title,
        image_count=len(clean_images) if clean_images else (1 if clean_image else 0),
        data_path=config.data_path,
    )


def overwrite_memo_with_post(
    config: BotConfig,
    *,
    memo_id: str,
    post: MumemoSlackPost,
    preserve_existing_identity: bool,
    location: str | None = None,
) -> StoreResult:
    saved_images = download_images(
        bot_token=config.slack_bot_token,
        post=post,
        asset_dir=config.asset_dir,
        asset_url_prefix=config.asset_url_prefix,
        original_asset_dir=config.original_asset_dir,
        github_repo_url=config.github_repo_url,
        github_branch=config.github_branch,
    )

    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        old_memo = dict(memos[index])
        if bool(old_memo.get("fixed")):
            raise ProtectedMemoError("固定メモはSlack管理画面から上書きできません")

        old_memos = [dict(item) for item in memos]
        new_memo = _memo_from_post(config, post, saved_images, location=location)
        if preserve_existing_identity:
            _preserve_existing_identity(old_memo, new_memo, memo_id)

        memos[index] = new_memo
        _write_memos(config.data_path, memos)
        build_route_pages(config)
        _cleanup_replaced_memo(config, old_memos, old_memo, memos)
        memo_id = _memo_ids(memos)[index]
        page_url = _memo_page_url(config, memos, index)

    return StoreResult(
        created=False,
        title=post.title,
        image_count=len(saved_images),
        data_path=config.data_path,
        memo_id=memo_id,
        page_url=page_url,
        location=_memo_location(new_memo),
    )


def append_memo_with_post(
    config: BotConfig,
    *,
    memo_id: str,
    post: MumemoSlackPost,
    location: str | None = None,
) -> StoreResult:
    saved_images = download_images(
        bot_token=config.slack_bot_token,
        post=post,
        asset_dir=config.asset_dir,
        asset_url_prefix=config.asset_url_prefix,
        original_asset_dir=config.original_asset_dir,
        github_repo_url=config.github_repo_url,
        github_branch=config.github_branch,
    )

    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        memo = memos[index]
        if bool(memo.get("fixed")):
            raise ProtectedMemoError("固定メモはSlack管理画面から追記できません")

        old_body = str(memo.get("body") or "")
        memo["body"] = _append_body(old_body, post.body)

        new_image_urls = [image.url for image in saved_images]
        new_original_urls_by_image = {
            image.url: image.original_url
            for image in saved_images
            if image.original_url
        }
        current_images = [
            image_url
            for image_url in _memo_images(memo)
            if image_url != config.default_image
        ]
        merged_images = _merge_image_urls(current_images, new_image_urls)
        original_image_map = {
            **_original_image_map(memo),
            **new_original_urls_by_image,
        }
        if merged_images:
            memo["images"] = merged_images
        else:
            memo.pop("images", None)

        current_image = str(memo.get("image") or "").strip()
        if not str(memo.get("location") or "").strip():
            memo["location"] = _location_for_store(
                config,
                str(memo.get("title") or post.title),
                str(memo.get("body") or ""),
                location,
            )
        _ensure_detail_images_for_urls(config, merged_images)
        if saved_images and (not current_image or current_image == config.default_image):
            memo["image"] = saved_images[0].url
            if saved_images[0].thumbnail_url:
                memo["thumbnail"] = saved_images[0].thumbnail_url
        elif not str(memo.get("thumbnail") or "").strip():
            thumbnail = _thumbnail_url_for_image_url(config, current_image)
            if thumbnail:
                memo["thumbnail"] = thumbnail
        _set_original_image_fields(
            memo,
            str(memo.get("image") or ""),
            merged_images,
            _align_original_images(merged_images, original_image_map),
        )

        _write_memos(config.data_path, memos)
        build_route_pages(config)
        page_url = _memo_page_url(config, memos, index)

    return StoreResult(
        created=False,
        title=str(memo.get("title") or post.title),
        image_count=len(saved_images),
        data_path=config.data_path,
        memo_id=_memo_ids(memos)[index],
        page_url=page_url,
        location=_memo_location(memo),
    )

def delete_memo(config: BotConfig, *, memo_id: str) -> MemoChangeResult:
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        memo = memos[index]
        if bool(memo.get("fixed")):
            raise ProtectedMemoError("固定メモはSlack管理画面から削除できません")

        old_memos = [dict(item) for item in memos]
        removed = memos.pop(index)
        _write_memos(config.data_path, memos)
        build_route_pages(config)
        _cleanup_replaced_memo(config, old_memos, removed, memos)

    return MemoChangeResult(
        title=str(removed.get("title") or memo_id),
        image_count=_memo_image_count(removed),
        data_path=config.data_path,
    )


def download_images(
    bot_token: str,
    post: MumemoSlackPost,
    asset_dir: Path,
    asset_url_prefix: str,
    original_asset_dir: Path | None = None,
    github_repo_url: str = "",
    github_branch: str = "main",
) -> list[SavedImage]:
    if not post.images:
        return []

    title_folder = _safe_title_folder(post.title)
    public_memo_asset_dir = asset_dir / title_folder
    original_root = original_asset_dir or asset_dir
    original_memo_asset_dir = original_root / title_folder
    public_memo_asset_dir.mkdir(parents=True, exist_ok=True)
    original_memo_asset_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {bot_token}"})
    saved_images: list[SavedImage] = []

    for image_index, image in enumerate(post.images):
        filename = _image_filename(image)
        saved_path = original_memo_asset_dir / filename
        public_image_path = public_memo_asset_dir / filename
        response = session.get(image.download_url, stream=True, timeout=60)
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise RuntimeError(
                f"Failed to download Slack image {image.file_id}: "
                f"HTTP {response.status_code} {response.text}"
            ) from error

        with saved_path.open("wb") as output_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)

        thumbnail_path = (
            _create_thumbnail(
                saved_path,
                _thumbnail_path_for_image_path(public_image_path),
            )
            if image_index == 0
            else None
        )
        display_path = _create_detail_image(
            saved_path,
            _detail_image_path_for_image_path(public_image_path),
        )
        display_url = _asset_url(asset_url_prefix, display_path.relative_to(asset_dir))
        thumbnail_url = (
            _asset_url(asset_url_prefix, thumbnail_path.relative_to(asset_dir))
            if thumbnail_path
            else None
        )
        saved_images.append(
            SavedImage(
                file_id=image.file_id,
                source_name=image.name,
                path=saved_path,
                url=display_url,
                original_url=_github_raw_url(github_repo_url, github_branch, saved_path),
                thumbnail_path=thumbnail_path,
                thumbnail_url=thumbnail_url,
                display_path=display_path,
                display_url=display_url,
            )
        )

    return saved_images


def build_route_pages(config: BotConfig) -> None:
    result = subprocess.run(
        config.route_build_command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"Route page build failed with exit code {result.returncode}: {detail}"
        )


def _load_memos(data_path: Path) -> list[dict[str, Any]]:
    if not data_path.exists():
        return []
    data = json.loads(data_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise RuntimeError(f"{data_path} must contain a JSON array")
    return data


def _write_memos(data_path: Path, memos: list[dict[str, Any]]) -> None:
    data_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = data_path.with_suffix(data_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(memos, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(data_path)


def _memo_from_post(
    config: BotConfig,
    post: MumemoSlackPost,
    saved_images: list[SavedImage],
    *,
    location: str | None = None,
) -> dict[str, Any]:
    primary_image = saved_images[0] if saved_images else None
    memo: dict[str, Any] = {
        "id": _slack_memo_id(post.channel_id, post.message_ts),
        "title": post.title,
        "body": post.body,
        "location": _location_for_store(config, post.title, post.body, location),
        "image": primary_image.url if primary_image else config.default_image,
        "thumbnail": primary_image.thumbnail_url if primary_image and primary_image.thumbnail_url else config.default_image,
        "source": {
            "type": "slack",
            "channel_id": post.channel_id,
            "message_ts": post.message_ts,
            "user_id": post.user_id,
        },
    }
    posted_at = _slack_ts_to_date(post.message_ts)
    if posted_at:
        memo["postedAt"] = posted_at
    if saved_images:
        memo["images"] = [image.url for image in saved_images]
        original_images = [image.original_url for image in saved_images if image.original_url]
        if original_images:
            memo[ORIGINAL_IMAGE_KEY] = original_images[0]
            memo[ORIGINAL_IMAGES_KEY] = original_images
    return memo


def _location_for_update(config: BotConfig, title: str, body: str, location: str | None) -> str:
    clean_location = str(location or "").strip()
    if clean_location:
        return normalize_location(clean_location)
    return _infer_location(config, title, body)


def _location_for_store(config: BotConfig, title: str, body: str, location: str | None) -> str:
    clean_location = str(location or "").strip()
    if clean_location:
        return normalize_location(clean_location)
    return _infer_location(config, title, body)


def _infer_location(config: BotConfig, title: str, body: str) -> str:
    return infer_location(
        title,
        body,
        nominatim_user_agent=config.nominatim_user_agent,
        nominatim_email=config.nominatim_email,
        nominatim_endpoint=config.nominatim_endpoint,
        timeout_seconds=config.nominatim_timeout_seconds,
    )

def _list_item(memo: dict[str, Any], memo_id: str) -> MemoListItem:
    image = str(memo.get("image") or "")
    images = _memo_images(memo)
    return MemoListItem(
        id=memo_id,
        title=str(memo.get("title") or "(無題)"),
        body=str(memo.get("body") or ""),
        image=image,
        images=images,
        image_count=len(images) if images else (1 if image else 0),
        location=_memo_location(memo),
        fixed=bool(memo.get("fixed")),
    )


def _memo_location(memo: dict[str, Any]) -> str:
    clean_location = str(memo.get("location") or "").strip()
    if clean_location:
        return normalize_location(clean_location)
    return UNKNOWN_LOCATION

def _memo_images(memo: dict[str, Any]) -> list[str]:
    images = memo.get("images")
    if isinstance(images, list):
        return [str(image) for image in images if str(image).strip()]
    image = str(memo.get("image") or "").strip()
    return [image] if image else []


def _memo_original_images(memo: dict[str, Any]) -> list[str]:
    originals = memo.get(ORIGINAL_IMAGES_KEY)
    if isinstance(originals, list):
        return [str(image).strip() for image in originals]
    original = str(memo.get(ORIGINAL_IMAGE_KEY) or "").strip()
    return [original] if original else []


def _original_image_map(memo: dict[str, Any]) -> dict[str, str]:
    return {
        image: original
        for image, original in zip(_memo_images(memo), _memo_original_images(memo))
        if image and original
    }


def _align_original_images(images: list[str], original_image_map: dict[str, str]) -> list[str]:
    return [
        original_image_map.get(image, "")
        for image in images
    ]


def _set_original_image_fields(
    memo: dict[str, Any],
    image: str,
    images: list[str],
    original_images: list[str],
) -> None:
    if not images or not any(original_images):
        memo.pop(ORIGINAL_IMAGE_KEY, None)
        memo.pop(ORIGINAL_IMAGES_KEY, None)
        return

    memo[ORIGINAL_IMAGES_KEY] = original_images
    primary_original = ""
    if image in images:
        image_index = images.index(image)
        if image_index < len(original_images):
            primary_original = original_images[image_index]
    memo[ORIGINAL_IMAGE_KEY] = primary_original or original_images[0]


def _memo_referenced_images(memo: dict[str, Any]) -> list[str]:
    images: list[str] = []
    seen: set[str] = set()
    for image in [
        str(memo.get("thumbnail") or ""),
        str(memo.get("image") or ""),
        *_memo_images(memo),
    ]:
        clean_image = image.strip()
        if not clean_image or clean_image in seen:
            continue
        seen.add(clean_image)
        images.append(clean_image)
    return images


def _memo_image_count(memo: dict[str, Any]) -> int:
    return len(_memo_images(memo))


def _find_existing_slack_memo(
    memos: list[dict[str, Any]],
    post: MumemoSlackPost,
) -> dict[str, Any] | None:
    for memo in memos:
        if _same_slack_source(memo, post):
            return memo
    return None


def _has_title_conflict(memos: list[dict[str, Any]], post: MumemoSlackPost) -> bool:
    title_key = _title_key(post.title)
    return any(
        not bool(memo.get("fixed"))
        and not _same_slack_source(memo, post)
        and _title_key(str(memo.get("title") or "")) == title_key
        for memo in memos
    )


def _next_duplicate_slug(memos: list[dict[str, Any]], title: str) -> str:
    base = _slug_base(title)
    existing_slugs = set(_memo_slugs(memos))
    suffix = 2
    while f"{base}-{suffix}" in existing_slugs:
        suffix += 1
    return f"{base}-{suffix}"


def _append_body(existing_body: str, new_body: str) -> str:
    existing_body = existing_body.rstrip()
    new_body = new_body.strip()
    if existing_body and new_body:
        return f"{existing_body}\n\n{new_body}"
    return existing_body or new_body


def _merge_image_urls(existing_images: list[str], new_images: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for image_url in [*existing_images, *new_images]:
        clean_image_url = image_url.strip()
        if not clean_image_url or clean_image_url in seen:
            continue
        seen.add(clean_image_url)
        merged.append(clean_image_url)
    return merged

def _same_slack_source(memo: dict[str, Any], post: MumemoSlackPost) -> bool:
    source = memo.get("source")
    if not isinstance(source, dict):
        return False
    return (
        source.get("type") == "slack"
        and source.get("channel_id") == post.channel_id
        and source.get("message_ts") == post.message_ts
    )


def _find_memo_index(memos: list[dict[str, Any]], memo_id: str) -> int:
    for index, current_id in enumerate(_memo_ids(memos)):
        if current_id == memo_id:
            return index
    raise MemoNotFoundError(f"メモが見つかりません: {memo_id}")


def _memo_ids(memos: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, int] = {}
    ids: list[str] = []
    for index, memo in enumerate(memos):
        base = _memo_id_base(memo, index)
        count = seen.get(base, 0)
        seen[base] = count + 1
        ids.append(base if count == 0 else f"{base}-{count + 1}")
    return ids


def _memo_id_base(memo: dict[str, Any], index: int) -> str:
    memo_id = memo.get("id")
    if isinstance(memo_id, str) and memo_id.strip():
        return _safe_id(memo_id)

    source = memo.get("source")
    if isinstance(source, dict) and source.get("type") == "slack":
        channel_id = str(source.get("channel_id") or "unknown")
        message_ts = str(source.get("message_ts") or index + 1)
        return _slack_memo_id(channel_id, message_ts)

    title = str(memo.get("title") or "")
    return _safe_id(title) or f"memo-{index + 1}"


def _slack_memo_id(channel_id: str, message_ts: str) -> str:
    return _safe_id(f"slack-{channel_id}-{message_ts}")


def _slack_ts_to_date(message_ts: str) -> str | None:
    try:
        timestamp = float(message_ts)
    except ValueError:
        return None
    return datetime.fromtimestamp(
        timestamp,
        timezone(timedelta(hours=9)),
    ).date().isoformat()


def _safe_id(value: str) -> str:
    normalized = value.strip().replace("\\", " ").replace("/", " ")
    normalized = re.sub(r"[#?%&=+]+", " ", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "memo"


def _new_memo_insert_index(memos: list[dict[str, Any]]) -> int:
    index = 0
    while index < len(memos) and bool(memos[index].get("fixed")):
        index += 1
    return index


def _preserve_existing_identity(
    old_memo: dict[str, Any],
    new_memo: dict[str, Any],
    memo_id: str,
) -> None:
    new_memo["id"] = str(old_memo.get("id") or memo_id)
    for key in ("slug", "source", "postedAt", "posted_at", "createdAt", "created_at"):
        if key in old_memo:
            new_memo[key] = old_memo[key]


def _image_filename(image: SlackImageFile) -> str:
    extension = Path(image.name).suffix.lower()
    if not extension:
        extension = mimetypes.guess_extension(image.mimetype) or ".image"
    file_id = _safe_filename(image.file_id) or "file"
    return f"{file_id}{extension}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")


def _title_key(title: str) -> str:
    return unicodedata.normalize("NFKC", title).strip().casefold()


def _safe_title_folder(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).strip()
    normalized = re.sub(r"[<>:\"/\\|?*\x00-\x1F]+", "_", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ._")
    return normalized[:96] or "memo"


def _memo_page_url(config: BotConfig, memos: list[dict[str, Any]], index: int) -> str:
    slug = _memo_slugs(memos)[index]
    path = f"/{quote(slug, safe='')}/"
    base_url = config.site_base_url.strip().rstrip("/")
    return f"{base_url}{path}" if base_url else path

def _asset_url(asset_url_prefix: str, relative_path: Path) -> str:
    prefix = "/" + asset_url_prefix.strip("/")
    encoded_parts = [quote(part) for part in relative_path.parts]
    return f"{prefix}/{'/'.join(encoded_parts)}"


def _github_raw_url(repo_url: str, branch: str, path: Path) -> str | None:
    clean_repo_url = repo_url.strip().rstrip("/")
    if clean_repo_url.endswith(".git"):
        clean_repo_url = clean_repo_url[:-4]
    clean_branch = branch.strip() or "main"
    if not clean_repo_url:
        return None
    raw_base_url = _github_raw_base_url(clean_repo_url)
    if not raw_base_url:
        return None
    try:
        relative_path = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    encoded_parts = [quote(part) for part in relative_path.parts]
    return f"{raw_base_url}/{quote(clean_branch)}/{'/'.join(encoded_parts)}"


def _github_raw_base_url(repo_url: str) -> str | None:
    parsed = urlparse(repo_url)
    if parsed.netloc not in {"github.com", "www.github.com", "raw.githubusercontent.com"}:
        return None

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None

    owner = quote(parts[0], safe="")
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    repo = quote(repo, safe="")
    return f"https://raw.githubusercontent.com/{owner}/{repo}"


def _ensure_detail_images_for_urls(config: BotConfig, image_urls: list[str]) -> None:
    for image_url in image_urls:
        image_path = _local_asset_path(config, image_url)
        if image_path is None or not image_path.exists() or not image_path.is_file():
            continue
        if image_path.parent.name in {"thumbs", DETAIL_IMAGE_DIRNAME}:
            continue
        try:
            _create_detail_image(image_path)
        except OSError:
            continue


def _thumbnail_url_for_image_url(config: BotConfig, image_url: str) -> str | None:
    clean_image_url = image_url.strip()
    if not clean_image_url:
        return None
    if clean_image_url in {config.default_image, "/website_icon_small.png"}:
        return clean_image_url

    image_path = _local_asset_path(config, clean_image_url)
    if image_path is None or not image_path.exists() or not image_path.is_file():
        return None
    if image_path.parent.name == "thumbs":
        return clean_image_url
    if image_path.parent.name == DETAIL_IMAGE_DIRNAME:
        thumbnail_path = _thumbnail_path_for_detail_image_path(image_path)
        if thumbnail_path.exists() and thumbnail_path.is_file():
            return _asset_url(config.asset_url_prefix, thumbnail_path.relative_to(config.asset_dir))
        try:
            _create_thumbnail(image_path, thumbnail_path)
        except OSError:
            return None
        return _asset_url(config.asset_url_prefix, thumbnail_path.relative_to(config.asset_dir))

    try:
        thumbnail_path = _create_thumbnail(image_path)
    except OSError:
        return None
    return _asset_url(config.asset_url_prefix, thumbnail_path.relative_to(config.asset_dir))


def _create_thumbnail(image_path: Path, thumbnail_path: Path | None = None) -> Path:
    thumbnail_path = thumbnail_path or _thumbnail_path_for_image_path(image_path)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        image = ImageOps.fit(image, THUMBNAIL_SIZE, method=Image.Resampling.LANCZOS)
        image = _flatten_to_rgb(image)
        image.save(
            thumbnail_path,
            format="JPEG",
            quality=THUMBNAIL_QUALITY,
            optimize=True,
            progressive=True,
        )
    return thumbnail_path


def _create_detail_image(image_path: Path, detail_image_path: Path | None = None) -> Path:
    detail_image_path = detail_image_path or _detail_image_path_for_image_path(image_path)
    detail_image_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail(
            (DETAIL_IMAGE_MAX_SIZE, DETAIL_IMAGE_MAX_SIZE),
            Image.Resampling.LANCZOS,
        )
        image = _flatten_to_rgb(image)
        image.save(
            detail_image_path,
            format="JPEG",
            quality=DETAIL_IMAGE_QUALITY,
            optimize=True,
            progressive=True,
        )
    return detail_image_path


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def _thumbnail_path_for_image_path(image_path: Path) -> Path:
    return image_path.parent / "thumbs" / f"{image_path.stem}-thumb.jpg"


def _detail_image_path_for_image_path(image_path: Path) -> Path:
    return image_path.parent / DETAIL_IMAGE_DIRNAME / f"{image_path.stem}-display.jpg"


def _thumbnail_path_for_detail_image_path(image_path: Path) -> Path:
    stem = image_path.stem
    if stem.endswith("-display"):
        stem = stem[: -len("-display")]
    return image_path.parent.parent / "thumbs" / f"{stem}-thumb.jpg"

def _clean_image_list(images: list[str]) -> list[str]:
    clean_images: list[str] = []
    seen: set[str] = set()
    for image in images:
        clean_image = image.strip()
        if not clean_image or clean_image in seen:
            continue
        seen.add(clean_image)
        clean_images.append(clean_image)
    return clean_images


def _cleanup_replaced_memo(
    config: BotConfig,
    old_memos: list[dict[str, Any]],
    removed: dict[str, Any],
    remaining_memos: list[dict[str, Any]],
) -> None:
    asset_root = config.asset_dir.resolve()
    original_asset_root = config.original_asset_dir.resolve()
    remaining_asset_paths = {
        asset_path
        for memo in remaining_memos
        for asset_path in _memo_referenced_asset_paths(config, memo)
    }
    remaining_original_asset_paths = {
        asset_path
        for memo in remaining_memos
        for asset_path in _memo_referenced_original_asset_paths(config, memo)
    }
    for asset_path in _memo_referenced_asset_paths(config, removed):
        if asset_path in remaining_asset_paths:
            continue
        if not asset_path.exists() or not asset_path.is_file():
            continue
        asset_path.unlink()
        _remove_empty_asset_parents(asset_path.parent, asset_root)
    for asset_path in _memo_referenced_original_asset_paths(config, removed):
        if asset_path in remaining_original_asset_paths:
            continue
        if not asset_path.exists() or not asset_path.is_file():
            continue
        asset_path.unlink()
        _remove_empty_asset_parents(asset_path.parent, original_asset_root)

    _cleanup_stale_route_pages(old_memos, remaining_memos)


def _memo_referenced_asset_paths(config: BotConfig, memo: dict[str, Any]) -> list[Path]:
    asset_paths: list[Path] = []
    seen: set[Path] = set()
    for image_url in _memo_referenced_images(memo):
        image_path = _local_asset_path(config, image_url)
        if image_path is None:
            continue
        for asset_path in _image_asset_paths(image_path):
            if asset_path in seen:
                continue
            seen.add(asset_path)
            asset_paths.append(asset_path)
    return asset_paths


def _memo_referenced_original_asset_paths(config: BotConfig, memo: dict[str, Any]) -> list[Path]:
    asset_paths: list[Path] = []
    seen: set[Path] = set()
    for image_url in [str(memo.get(ORIGINAL_IMAGE_KEY) or ""), *_memo_original_images(memo)]:
        image_path = _local_original_asset_path(config, image_url)
        if image_path is None or image_path in seen:
            continue
        seen.add(image_path)
        asset_paths.append(image_path)
    return asset_paths


def _image_asset_paths(image_path: Path) -> list[Path]:
    if image_path.parent.name in {"thumbs", DETAIL_IMAGE_DIRNAME}:
        return [image_path]
    return [
        image_path,
        _thumbnail_path_for_image_path(image_path),
        _detail_image_path_for_image_path(image_path),
    ]


def _cleanup_stale_route_pages(
    old_memos: list[dict[str, Any]],
    current_memos: list[dict[str, Any]],
) -> None:
    current_slugs = set(_memo_slugs(current_memos))
    for slug in _memo_slugs(old_memos):
        if slug in current_slugs:
            continue
        _remove_route_dir(slug)


def _remove_route_dir(slug: str) -> None:
    if slug in PROTECTED_ROUTE_DIRS:
        return

    docs_dir = (PROJECT_ROOT / "docs").resolve()
    route_dir = (docs_dir / slug).resolve()
    if route_dir == docs_dir or not _is_relative_to(route_dir, docs_dir):
        return
    if route_dir.exists() and route_dir.is_dir():
        shutil.rmtree(route_dir)


def _local_asset_path(config: BotConfig, image_url: str) -> Path | None:
    parsed = urlparse(image_url)
    if parsed.scheme or parsed.netloc:
        return None

    prefix = "/" + config.asset_url_prefix.strip("/")
    path = unquote(parsed.path)
    if not path.startswith(prefix + "/"):
        return None

    relative_url = path[len(prefix) + 1 :]
    if not relative_url:
        return None
    relative_path = Path(*relative_url.split("/"))
    asset_root = config.asset_dir.resolve()
    candidate = (asset_root / relative_path).resolve()
    if not _is_relative_to(candidate, asset_root):
        return None
    return candidate


def _local_original_asset_path(config: BotConfig, image_url: str) -> Path | None:
    clean_image_url = image_url.strip()
    if not clean_image_url:
        return None

    parsed = urlparse(clean_image_url)
    relative_url = ""
    repo_url = config.github_repo_url.strip().rstrip("/")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]

    if parsed.scheme and parsed.netloc:
        repo_path = urlparse(repo_url).path.rstrip("/")
        branch = quote(config.github_branch.strip() or "main")
        blob_prefix = f"{repo_path}/blob/{branch}/"
        raw_prefix = f"{repo_path}/{branch}/"
        if parsed.netloc == "raw.githubusercontent.com" and parsed.path.startswith(raw_prefix):
            relative_url = parsed.path[len(raw_prefix) :]
        elif parsed.path.startswith(blob_prefix):
            relative_url = parsed.path[len(blob_prefix) :]
        else:
            return None
    else:
        relative_url = unquote(parsed.path).lstrip("/")

    if not relative_url:
        return None

    relative_path = Path(*unquote(relative_url).split("/"))
    asset_root = config.original_asset_dir.resolve()
    candidate = (PROJECT_ROOT / relative_path).resolve()
    if not _is_relative_to(candidate, asset_root):
        return None
    return candidate


def _remove_empty_asset_parents(path: Path, asset_root: Path) -> None:
    current = path.resolve()
    while current != asset_root and _is_relative_to(current, asset_root):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _memo_slugs(memos: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, int] = {}
    slugs: list[str] = []
    for memo in memos:
        base = _slug_base(str(memo.get("slug") or memo.get("title") or ""))
        count = seen.get(base, 0)
        seen[base] = count + 1
        slugs.append(base if count == 0 else f"{base}-{count + 1}")
    return slugs


def _slug_base(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[\\/#?%&=+]+", " ", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "memo"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
