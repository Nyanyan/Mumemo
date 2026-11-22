from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
import json

from mumemo_bot.slack_post import SlackImageFile


def review_image_path(directory: Path, channel_id: str, message_ts: str) -> Path:
    key = sha256(f"{channel_id}:{message_ts}".encode()).hexdigest()
    return directory / f"{key}.json"


def load_review_images(path: Path) -> list[SlackImageFile]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [SlackImageFile(**image) for image in json.loads(content)]


def save_review_images(path: Path, images: list[SlackImageFile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = NamedTemporaryFile(
        mode="w", dir=path.parent, encoding="utf-8", delete=False
    )
    temporary_path = Path(output.name)
    try:
        with output:
            json.dump([asdict(image) for image in images], output, ensure_ascii=False)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
