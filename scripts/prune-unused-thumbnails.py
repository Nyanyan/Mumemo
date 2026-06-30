from pathlib import Path
from urllib.parse import unquote, urlparse
import argparse
import json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MEMOS_PATH = PROJECT_ROOT / "docs" / "data" / "memos.json"
ASSET_ROOT = PROJECT_ROOT / "docs" / "assets" / "posts"
ASSET_URL_PREFIX = "/assets/posts/"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    referenced_thumbnails = referenced_thumbnail_paths()
    thumbnail_files = {
        path.resolve()
        for path in ASSET_ROOT.rglob("*")
        if path.is_file() and path.parent.name == "thumbs"
    }
    unused_thumbnails = sorted(thumbnail_files - referenced_thumbnails)

    if args.delete:
        for path in unused_thumbnails:
            path.unlink()
        remove_empty_thumbnail_dirs()

    print(f"thumbnail_files={len(thumbnail_files)}")
    print(f"referenced_thumbnails={len(thumbnail_files & referenced_thumbnails)}")
    print(f"unused_thumbnails={len(unused_thumbnails)}")
    if args.delete:
        print(f"deleted_unused_thumbnails={len(unused_thumbnails)}")


def referenced_thumbnail_paths() -> set[Path]:
    memos = json.loads(MEMOS_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(memos, list):
        raise RuntimeError(f"{MEMOS_PATH} must contain a JSON array")

    paths: set[Path] = set()
    for memo in memos:
        if not isinstance(memo, dict):
            continue
        thumbnail = str(memo.get("thumbnail") or "").strip()
        parsed = urlparse(thumbnail)
        if parsed.scheme or parsed.netloc:
            continue
        path = unquote(parsed.path)
        if not path.startswith(ASSET_URL_PREFIX):
            continue
        relative_url = path[len(ASSET_URL_PREFIX) :]
        if not relative_url:
            continue
        candidate = (ASSET_ROOT / Path(*relative_url.split("/"))).resolve()
        if is_relative_to(candidate, ASSET_ROOT.resolve()):
            paths.add(candidate)
    return paths


def remove_empty_thumbnail_dirs() -> None:
    for path in sorted(ASSET_ROOT.rglob("thumbs"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    main()
