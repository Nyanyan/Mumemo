from dataclasses import dataclass
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


def save_post_as_memo(config: BotConfig, post: MumemoSlackPost) -> StoreResult:
    config.data_path.parent.mkdir(parents=True, exist_ok=True)
    with _STORE_LOCK:
        memos = _load_memos(config.data_path)
        existing = _find_existing_slack_memo(memos, post)
        if existing is not None:
            return StoreResult(
                created=False,
                title=str(existing.get("title") or post.title),
                image_count=_memo_image_count(existing),
                data_path=config.data_path,
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
            return StoreResult(
                created=False,
                title=str(existing.get("title") or post.title),
                image_count=_memo_image_count(existing),
                data_path=config.data_path,
            )

        memo = _memo_from_post(config, post, saved_images)
        memos.append(memo)
        _write_memos(config.data_path, memos)
        build_route_pages(config)

    return StoreResult(
        created=True,
        title=post.title,
        image_count=len(saved_images),
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
    data = json.loads(data_path.read_text(encoding="utf-8"))
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
    if saved_images:
        memo["images"] = [image.url for image in saved_images]
    return memo


def _memo_image_count(memo: dict[str, Any]) -> int:
    images = memo.get("images")
    if isinstance(images, list):
        return len(images)
    return 1 if memo.get("image") else 0


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


def _image_filename(title: str, image: SlackImageFile) -> str:
    extension = Path(image.name).suffix.lower()
    if not extension:
        extension = mimetypes.guess_extension(image.mimetype) or ".image"
    title_part = _safe_filename(title)[:48] or "memo"
    file_id = _safe_filename(image.file_id) or "file"
    return f"{title_part}-{file_id}{extension}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")