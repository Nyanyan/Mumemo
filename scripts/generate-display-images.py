from pathlib import Path
from urllib.parse import unquote, urlparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"
MEMOS_PATH = DOCS_DIR / "data" / "memos.json"
ASSET_DIR = DOCS_DIR / "assets" / "slack"
ASSET_URL_PREFIX = "/assets/slack"
ORIGINAL_ASSET_DIR = PROJECT_ROOT / "originals" / "slack"

sys.path.insert(0, str(PROJECT_ROOT))
from mumemo_bot.site_store import _create_detail_image  # noqa: E402


def main() -> None:
    memos = json.loads(MEMOS_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(memos, list):
        raise RuntimeError(f"{MEMOS_PATH} must contain a JSON array")

    image_paths = collect_image_paths(memos)
    generated = 0
    skipped = 0
    failed: list[tuple[Path, str]] = []

    for image_path in image_paths:
        try:
            _create_detail_image(image_path, display_output_path(image_path))
            generated += 1
        except OSError as error:
            skipped += 1
            failed.append((image_path, str(error)))

    print(f"Synced {generated} detail image(s).")
    if skipped:
        print(f"Skipped {skipped} image(s):")
        for image_path, reason in failed:
            print(f"- {image_path}: {reason}")


def collect_image_paths(memos: list[object]) -> list[Path]:
    image_paths: list[Path] = []
    seen: set[Path] = set()

    if ORIGINAL_ASSET_DIR.exists():
        for image_path in ORIGINAL_ASSET_DIR.rglob("*"):
            if image_path.is_file() and image_path not in seen:
                seen.add(image_path)
                image_paths.append(image_path)

    for memo in memos:
        if not isinstance(memo, dict):
            continue
        for image_url in memo_image_urls(memo):
            image_path = local_asset_path(image_url)
            if image_path is None or image_path in seen:
                continue
            seen.add(image_path)
            image_paths.append(image_path)

    return image_paths


def display_output_path(image_path: Path) -> Path | None:
    try:
        relative_path = image_path.resolve().relative_to(ORIGINAL_ASSET_DIR.resolve())
    except ValueError:
        return None
    public_image_path = ASSET_DIR / relative_path
    return public_image_path.parent / "display" / f"{public_image_path.stem}-display.jpg"


def memo_image_urls(memo: dict[str, object]) -> list[str]:
    urls: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value.strip():
            urls.append(value.strip())

    add(memo.get("image"))
    images = memo.get("images")
    if isinstance(images, list):
        for image_url in images:
            add(image_url)
    return urls


def local_asset_path(image_url: str) -> Path | None:
    parsed = urlparse(image_url)
    if parsed.scheme or parsed.netloc:
        return None

    path = unquote(parsed.path)
    prefix = ASSET_URL_PREFIX.rstrip("/") + "/"
    if not path.startswith(prefix):
        return None

    relative_url = path[len(prefix) :]
    if not relative_url:
        return None
    relative_path = Path(*relative_url.split("/"))
    candidate = (ASSET_DIR / relative_path).resolve()
    asset_root = ASSET_DIR.resolve()
    if not is_relative_to(candidate, asset_root):
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    if candidate.parent.name in {"thumbs", "display"}:
        return None
    return candidate


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    main()
