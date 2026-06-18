from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trapo.filesystem_safety import (
    read_bytes_file,
    read_text_file,
    write_bytes_file,
    write_text_file,
)
from trapo.ingest.page_images import RenderedPageImage
from trapo.ingest.page_markdown_types import (
    CACHE_SCHEMA_VERSION,
    DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    MAX_MARKDOWN_CACHE_IMAGE_BYTES,
    MAX_MARKDOWN_CACHE_MANIFEST_BYTES,
    MAX_MARKDOWN_CACHE_METADATA_BYTES,
    MarkdownPageImage,
    MarkdownRenderOptions,
)


def load_cached_pages(
    options: MarkdownRenderOptions,
    log: Callable[[str], None] | None,
) -> list[MarkdownPageImage]:
    cache_dir = markdown_cache_dir(options)
    manifest = _read_cache_manifest(options)
    pages = _manifest_pages(manifest, options)
    cached = _read_cached_page_records(cache_dir, pages) if pages else []
    if cached:
        _log(
            log,
            f"Using cached Markdown page images: pages={len(cached)} cache_dir={cache_dir}",
        )
    return sorted(cached, key=lambda item: item.page.page_no)


def _read_cache_manifest(options: MarkdownRenderOptions) -> dict[str, Any] | None:
    cache_dir = markdown_cache_dir(options)
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        loaded = json.loads(
            read_text_file(
                manifest_path,
                root=cache_dir,
                max_bytes=MAX_MARKDOWN_CACHE_MANIFEST_BYTES,
            )
        )
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _manifest_pages(
    manifest: dict[str, Any] | None,
    options: MarkdownRenderOptions,
) -> list[object]:
    if manifest is None or manifest.get("render_key") != markdown_render_key(options):
        return []
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        return []
    return pages


def write_page_artifacts(
    page: RenderedPageImage,
    options: MarkdownRenderOptions,
    cache_dir: Path | None,
    log: Callable[[str], None] | None,
) -> MarkdownPageImage:
    image_path = _image_path(cache_dir, page) if cache_dir is not None else None
    metadata_path = _metadata_path(cache_dir, page) if cache_dir is not None else None
    if image_path is not None:
        write_bytes_file(image_path, page.image_bytes, root=cache_dir)
    metadata = _page_metadata(
        page, options, image_path=image_path, metadata_path=metadata_path
    )
    if metadata_path is not None:
        write_text_file(
            metadata_path,
            json.dumps(metadata, indent=2),
            root=cache_dir,
            encoding="utf-8",
        )
    _log(
        log,
        "Rendered Markdown page image: "
        f"page={page.page_no} render={page.render_width}x{page.render_height} "
        f"bytes={len(page.image_bytes)} sha256={page.image_sha256} "
        f"cache_path={image_path or '-'}",
    )
    return MarkdownPageImage(
        page=page,
        cache_hit=False,
        image_path=image_path,
        metadata_path=metadata_path,
        metadata=metadata,
    )


def write_manifest(
    cache_dir: Path,
    pages: list[MarkdownPageImage],
    options: MarkdownRenderOptions,
    source_path: Path,
) -> None:
    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "render_key": markdown_render_key(options),
        "file_hash": options.file_hash,
        "source_path": str(source_path),
        "page_count": len(pages),
        "pages": [
            {
                "page_no": page.page.page_no,
                "image_filename": page.image_path.name
                if page.image_path is not None
                else None,
                "metadata_filename": page.metadata_path.name
                if page.metadata_path is not None
                else None,
            }
            for page in pages
        ],
    }
    write_text_file(
        cache_dir / "manifest.json",
        json.dumps(manifest, indent=2),
        root=cache_dir,
        encoding="utf-8",
    )


def markdown_cache_dir(options: MarkdownRenderOptions) -> Path:
    return Path(options.cache_root) / options.file_hash / markdown_render_key(options)


def markdown_render_key(options: MarkdownRenderOptions) -> str:
    return (
        f"dpi{options.render_dpi}-side{options.image_max_side}-"
        f"{normalized_markdown_image_format(options.image_format).lower()}"
        f"-q{options.jpeg_quality}"
    )


def normalized_markdown_image_format(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"JPG", "JPEG"}:
        return "JPEG"
    return DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT


def _read_cached_page_records(
    cache_dir: Path, pages: list[object]
) -> list[MarkdownPageImage]:
    cached: list[MarkdownPageImage] = []
    for item in pages:
        page = _read_cached_page_record(cache_dir, item)
        if page is None:
            return []
        cached.append(page)
    return cached


def _read_cached_page_record(cache_dir: Path, item: object) -> MarkdownPageImage | None:
    result: MarkdownPageImage | None = None
    if isinstance(item, dict):
        metadata_path = _cache_child(cache_dir, item.get("metadata_filename"), ".json")
        image_path = _cache_child(cache_dir, item.get("image_filename"), ".jpg")
        if (
            metadata_path is not None
            and image_path is not None
            and metadata_path.exists()
            and image_path.exists()
        ):
            result = _cached_page_from_files(cache_dir, metadata_path, image_path)
    return result


def _cached_page_from_files(
    cache_dir: Path,
    metadata_path: Path,
    image_path: Path,
) -> MarkdownPageImage:
    metadata = json.loads(
        read_text_file(
            metadata_path,
            root=cache_dir,
            max_bytes=MAX_MARKDOWN_CACHE_METADATA_BYTES,
        )
    )
    image_bytes = read_bytes_file(
        image_path,
        root=cache_dir,
        max_bytes=MAX_MARKDOWN_CACHE_IMAGE_BYTES,
    )
    page = RenderedPageImage(
        page_no=int(metadata["page_no"]),
        width=float(metadata["page_width"]),
        height=float(metadata["page_height"]),
        render_width=int(metadata["render_width"]),
        render_height=int(metadata["render_height"]),
        mime_type=str(metadata["mime_type"]),
        image_bytes=image_bytes,
        image_sha256=str(metadata["image_sha256"]),
    )
    return MarkdownPageImage(
        page=page,
        cache_hit=True,
        image_path=image_path,
        metadata_path=metadata_path,
        metadata={**metadata, "cache_hit": True},
    )


def _page_metadata(
    page: RenderedPageImage,
    options: MarkdownRenderOptions,
    *,
    image_path: Path | None,
    metadata_path: Path | None,
) -> dict[str, Any]:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "render_key": markdown_render_key(options),
        "file_hash": options.file_hash,
        "page_no": page.page_no,
        "page_width": page.width,
        "page_height": page.height,
        "render_width": page.render_width,
        "render_height": page.render_height,
        "render_dpi": options.render_dpi,
        "render_pixels_per_inch": options.render_dpi,
        "image_max_side": options.image_max_side,
        "image_format": normalized_markdown_image_format(options.image_format),
        "requested_image_format": options.image_format,
        "jpeg_quality": options.jpeg_quality,
        "mime_type": page.mime_type,
        "image_bytes": len(page.image_bytes),
        "data_url_chars": len(page.data_url),
        "image_sha256": page.image_sha256,
        "rotation_degrees": (options.image_rotation_degrees_by_page or {}).get(
            page.page_no, 0
        ),
        "cache_hit": False,
        "image_path": str(image_path) if image_path is not None else None,
        "metadata_path": str(metadata_path) if metadata_path is not None else None,
    }


def _image_path(cache_dir: Path | None, page: RenderedPageImage) -> Path:
    if cache_dir is None:
        raise RuntimeError("cache_dir is required for image paths")
    return cache_dir / f"page-{page.page_no:04d}.jpg"


def _metadata_path(cache_dir: Path | None, page: RenderedPageImage) -> Path:
    if cache_dir is None:
        raise RuntimeError("cache_dir is required for metadata paths")
    return cache_dir / f"page-{page.page_no:04d}.json"


def _cache_child(cache_dir: Path, filename: object, suffix: str) -> Path | None:
    if not isinstance(filename, str) or not filename:
        return None
    child = Path(filename)
    if child.name != filename or child.suffix.lower() != suffix:
        return None
    return cache_dir / filename


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)
