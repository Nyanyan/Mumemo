from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import hashlib
import json
import re
import unicodedata

from PIL import Image, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
MEMOS_PATH = DOCS_DIR / "data" / "memos.json"
OGP_DIR = DOCS_DIR / "assets" / "ogp"
MANIFEST_PATH = OGP_DIR / "manifest.json"
HOME_OGP_SOURCE = REPO_ROOT / "OGP.jpg"
HOME_OGP_THUMB = DOCS_DIR / "OGP_thumb.jpg"
HOME_OGP_THUMB_SIZE = (480, 252)
LANDSCAPE_SIZE = (1200, 630)
SQUARE_SIZE = (800, 800)
JPEG_QUALITY = 86
THUMBNAIL_QUALITY = 76
DEFAULT_IMAGE = "/website_icon_small.png"


def main() -> None:
    raw_memos = json.loads(MEMOS_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(raw_memos, list):
        raise RuntimeError(f"{MEMOS_PATH} must contain a JSON array")

    OGP_DIR.mkdir(parents=True, exist_ok=True)
    sync_home_ogp_thumbnail()
    manifest: dict[str, dict[str, object]] = {}
    expected_paths: set[Path] = set()

    for memo in add_slugs(raw_memos):
        if not isinstance(memo, dict):
            continue
        slug = str(memo.get("slug") or "memo")
        output_path = OGP_DIR / ogp_filename(slug)
        generated = generate_ogp_image(memo, output_path)
        if generated is None:
            continue
        width, height = generated
        expected_paths.add(output_path.resolve())
        manifest[slug] = {
            "url": url_for_docs_path(output_path),
            "width": width,
            "height": height,
        }

    cleanup_stale_ogp_files(expected_paths)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(manifest)} OGP image(s).")


def generate_ogp_image(memo: dict[str, object], output_path: Path) -> tuple[int, int] | None:
    for image_url in candidate_image_urls(memo):
        source_path = local_docs_path(image_url)
        if source_path is None or not source_path.exists() or not source_path.is_file():
            continue
        try:
            return write_ogp_image(source_path, output_path)
        except OSError as error:
            print(f"Skipped OGP source {source_path}: {error}")
    return None


def sync_home_ogp_thumbnail() -> None:
    if not HOME_OGP_SOURCE.exists():
        return
    with Image.open(HOME_OGP_SOURCE) as source:
        image = ImageOps.exif_transpose(source)
        image = ImageOps.fit(image, HOME_OGP_THUMB_SIZE, method=Image.Resampling.LANCZOS)
        image = flatten_to_rgb(image)
        image.save(
            HOME_OGP_THUMB,
            format="JPEG",
            quality=THUMBNAIL_QUALITY,
            optimize=True,
            progressive=True,
        )


def write_ogp_image(source_path: Path, output_path: Path) -> tuple[int, int]:
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source)
        width, height = image.size
        target_size = LANDSCAPE_SIZE if width > height else SQUARE_SIZE
        image = ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS)
        image = flatten_to_rgb(image)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(
            output_path,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        return target_size


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        return background
    return image.convert("RGB")


def candidate_image_urls(memo: dict[str, object]) -> list[str]:
    urls: list[str] = []

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        clean_value = value.strip()
        if clean_value and clean_value not in urls:
            urls.append(clean_value)

    add(memo.get("image"))
    images = memo.get("images")
    if isinstance(images, list):
        for image in images:
            add(image)
    add(memo.get("thumbnail"))
    add(DEFAULT_IMAGE)
    return urls


def local_docs_path(image_url: str) -> Path | None:
    parsed = urlparse(image_url)
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    if not path.startswith("/"):
        return None
    candidate = (DOCS_DIR / path.lstrip("/")).resolve()
    docs_root = DOCS_DIR.resolve()
    if not is_relative_to(candidate, docs_root):
        return None
    return candidate


def add_slugs(items: list[object]) -> list[dict[str, object]]:
    seen: dict[str, int] = {}
    output: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        base = slug_base(str(item.get("slug") or item.get("title") or ""))
        count = seen.get(base, 0)
        seen[base] = count + 1
        memo = dict(item)
        memo["slug"] = base if count == 0 else f"{base}-{count + 1}"
        output.append(memo)
    return output


def slug_base(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[\\/#?%&=+]+", " ", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "memo"


def ogp_filename(slug: str) -> str:
    safe_slug = re.sub(r"[<>:\"|*]+", "_", slug).strip(". ") or "memo"
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:8]
    return f"{safe_slug}-{digest}.jpg"


def url_for_docs_path(path: Path) -> str:
    relative_path = path.resolve().relative_to(DOCS_DIR.resolve())
    return "/" + "/".join(quote(part) for part in relative_path.parts)


def cleanup_stale_ogp_files(expected_paths: set[Path]) -> None:
    for path in OGP_DIR.glob("*.jpg"):
        if path.resolve() not in expected_paths:
            path.unlink()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
