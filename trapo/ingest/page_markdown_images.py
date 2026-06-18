from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from trapo.ingest.page_images import iter_rendered_pages
from trapo.ingest.page_markdown_cache import (
    load_cached_pages,
    markdown_cache_dir,
    normalized_markdown_image_format,
    write_manifest,
    write_page_artifacts,
)
from trapo.ingest.page_markdown_types import (
    DEFAULT_PAGE_MARKDOWN_CACHE_ROOT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE,
    DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    DEFAULT_PAGE_MARKDOWN_RENDER_DPI,
    MarkdownPageImage,
    MarkdownRenderOptions,
)


__all__ = [
    "DEFAULT_PAGE_MARKDOWN_CACHE_ROOT",
    "DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT",
    "DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE",
    "DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY",
    "DEFAULT_PAGE_MARKDOWN_RENDER_DPI",
    "MarkdownPageImage",
    "MarkdownRenderOptions",
    "iter_markdown_page_images",
]


def iter_markdown_page_images(
    path: Path,
    *,
    options: MarkdownRenderOptions,
    log: Callable[[str], None] | None = None,
) -> Iterator[MarkdownPageImage]:
    """Yield JPEG-oriented page images for Markdown generation and cache artifacts."""
    if options.cache_enabled:
        cached_pages = load_cached_pages(options, log)
        if cached_pages:
            yield from cached_pages
            return

    cache_dir = markdown_cache_dir(options) if options.cache_enabled else None
    rendered_pages: list[MarkdownPageImage] = []
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    effective_format = normalized_markdown_image_format(options.image_format)
    if options.image_format.strip().upper() not in {"JPG", "JPEG"}:
        _log(
            log,
            "Page Markdown prompt images are always JPEG; "
            f"ignoring requested format={options.image_format!r}",
        )
    _log(
        log,
        "Rendering Markdown page images: "
        f"source={path} ppi={options.render_dpi} max_side={options.image_max_side} "
        f"format={effective_format} jpeg_quality={options.jpeg_quality} "
        f"cache={'on' if options.cache_enabled else 'off'}",
    )
    for page in iter_rendered_pages(
        path,
        dpi=options.render_dpi,
        max_side=options.image_max_side,
        image_format=effective_format,
        jpeg_quality=options.jpeg_quality,
        image_rotation_degrees_by_page=options.image_rotation_degrees_by_page,
    ):
        markdown_page = write_page_artifacts(page, options, cache_dir, log)
        rendered_pages.append(markdown_page)
        yield markdown_page
    if cache_dir is not None:
        write_manifest(cache_dir, rendered_pages, options, path)


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)
