from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
import json
import mimetypes
import re
import subprocess

import requests

from mumemo_bot.config import BotConfig, PROJECT_ROOT
from mumemo_bot.slack_post import MumemoSlackPost, SlackImageFile


_STORE_LOCK = Lock()


@dataclass(frozen=True)
class SavedImage:
    file_id: str
    source_name: str
    path: Path
    url: str


@dataclass(frozen=True)
class StoreResult:
    created: bool
    title: str
    image_count: int
    data_path: Path
    memo_id: str | None = None


@dataclass(frozen=True)
class MemoListItem:
    id: str
    title: str
    body: str
    image: str
    images: list[str]
    image_count: int
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


def save_post_as_memo(config: BotConfig, post: MumemoSlackPost) -> StoreResult:
    config.data_path.parent.mkdir(parents=True, exist_ok=True)
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        existing = _find_existing_slack_memo(memos, post)
        if existing is not None:
            memo_id = _memo_ids(memos)[memos.index(existing)]
            return StoreResult(
                created=False,
                title=str(existing.get("title") or post.title),
                image_count=_memo_image_count(existing),
                data_path=config.data_path,
                memo_id=memo_id,
            )

    saved_images = download_images(
        bot_token=config.slack_bot_token,
        post=post,
        asset_dir=config.asset_dir,
        asset_url_prefix=config.asset_url_prefix,
    )

    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        existing = _find_existing_slack_memo(memos, post)
        if existing is not None:
            memo_id = _memo_ids(memos)[memos.index(existing)]
            return StoreResult(
                created=False,
                title=str(existing.get("title") or post.title),
                image_count=_memo_image_count(existing),
                data_path=config.data_path,
                memo_id=memo_id,
            )

        memo = _memo_from_post(config, post, saved_images)
        memos.insert(_new_memo_insert_index(memos), memo)
        _write_memos(config.data_path, memos)
        build_route_pages(config)

    return StoreResult(
        created=True,
        title=post.title,
        image_count=len(saved_images),
        data_path=config.data_path,
        memo_id=str(memo.get("id")),
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


def update_memo(
    config: BotConfig,
    *,
    memo_id: str,
    title: str,
    body: str,
    image: str,
    images: list[str],
) -> MemoChangeResult:
    title = title.strip()
    if not title:
        raise ValueError("タイトルは空にできません")

    clean_images = _clean_image_list(images)
    clean_image = image.strip() or (clean_images[0] if clean_images else config.default_image)

    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        memo = memos[index]
        if bool(memo.get("fixed")):
            raise ProtectedMemoError("固定メモはSlack管理画面から編集できません")

        memo["id"] = str(memo.get("id") or memo_id)
        memo["title"] = title
        memo["body"] = body
        memo["image"] = clean_image
        if clean_images:
            memo["images"] = clean_images
        else:
            memo.pop("images", None)

        _write_memos(config.data_path, memos)
        build_route_pages(config)

    return MemoChangeResult(
        title=title,
        image_count=len(clean_images) if clean_images else (1 if clean_image else 0),
        data_path=config.data_path,
    )


def delete_memo(config: BotConfig, *, memo_id: str) -> MemoChangeResult:
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        index = _find_memo_index(memos, memo_id)
        memo = memos[index]
        if bool(memo.get("fixed")):
            raise ProtectedMemoError("固定メモはSlack管理画面から削除できません")

        removed = memos.pop(index)
        _write_memos(config.data_path, memos)
        build_route_pages(config)

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
) -> list[SavedImage]:
    if not post.images:
        return []

    asset_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {bot_token}"})
    saved_images: list[SavedImage] = []

    for image in post.images:
        saved_path = asset_dir / _image_filename(post.title, image)
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

        saved_images.append(
            SavedImage(
                file_id=image.file_id,
                source_name=image.name,
                path=saved_path,
                url=f"{asset_url_prefix}/{saved_path.name}",
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
) -> dict[str, Any]:
    memo: dict[str, Any] = {
        "id": _slack_memo_id(post.channel_id, post.message_ts),
        "title": post.title,
        "body": post.body,
        "image": saved_images[0].url if saved_images else config.default_image,
        "source": {
            "type": "slack",
            "channel_id": post.channel_id,
            "message_ts": post.message_ts,
            "user_id": post.user_id,
        },
    }
    posted_at = _slack_ts_to_iso(post.message_ts)
    if posted_at:
        memo["postedAt"] = posted_at
    if saved_images:
        memo["images"] = [image.url for image in saved_images]
    return memo


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
        fixed=bool(memo.get("fixed")),
    )


def _memo_images(memo: dict[str, Any]) -> list[str]:
    images = memo.get("images")
    if isinstance(images, list):
        return [str(image) for image in images if str(image).strip()]
    image = str(memo.get("image") or "").strip()
    return [image] if image else []


def _memo_image_count(memo: dict[str, Any]) -> int:
    return len(_memo_images(memo))


def _find_existing_slack_memo(
    memos: list[dict[str, Any]],
    post: MumemoSlackPost,
) -> dict[str, Any] | None:
    for memo in memos:
        source = memo.get("source")
        if not isinstance(source, dict):
            continue
        if (
            source.get("type") == "slack"
            and source.get("channel_id") == post.channel_id
            and source.get("message_ts") == post.message_ts
        ):
            return memo
    return None


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


def _slack_ts_to_iso(message_ts: str) -> str | None:
    try:
        timestamp = float(message_ts)
    except ValueError:
        return None
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


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


def _image_filename(title: str, image: SlackImageFile) -> str:
    extension = Path(image.name).suffix.lower()
    if not extension:
        extension = mimetypes.guess_extension(image.mimetype) or ".image"
    title_part = _safe_filename(title)[:48] or "memo"
    file_id = _safe_filename(image.file_id) or "file"
    return f"{title_part}-{file_id}{extension}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")


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
