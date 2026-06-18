from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from trapo.db import DuckConnection, table_exists
from trapo.ingest.page_images import iter_rendered_pages
from trapo.preview_cache_records import (
    DocumentPreviewImage,
    PREVIEW_JPEG_QUALITY,
    preview_image_from_row,
    preview_variant_names,
    write_page_variants,
)


DEFAULT_PREVIEW_CACHE_ROOT = ".cache/trapo/preview"
DEFAULT_PREVIEW_RENDER_DPI = 144
NORMALIZED_PREVIEW_MAX_SIDE = 1600

__all__ = [
    "DocumentPreviewImage",
    "PreviewCacheOptions",
    "build_document_preview_cache",
    "ensure_document_preview_cache",
    "ensure_document_preview_page",
    "preview_variant_names",
    "read_document_preview_images",
]


@dataclass(frozen=True)
class PreviewCacheOptions:
    cache_root: str = DEFAULT_PREVIEW_CACHE_ROOT
    rotation_degrees_by_page: dict[int, int] | None = None
    log: Callable[[str], None] | None = None


def build_document_preview_cache(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    *,
    options: PreviewCacheOptions | None = None,
    page_numbers: set[int] | None = None,
) -> list[DocumentPreviewImage]:
    """Render normalized per-page JPGs and Windows-style thumbnail variants."""
    if not table_exists(connection, "document_preview_images"):
        return []

    cache_options = options or PreviewCacheOptions()
    target_pages = _normalized_page_numbers(page_numbers)
    cache_dir = Path(cache_options.cache_root) / file_hash
    cache_dir.mkdir(parents=True, exist_ok=True)
    _delete_preview_rows(connection, file_hash, target_pages)
    rendered: list[DocumentPreviewImage] = []
    _log_render_start(cache_options, path, cache_dir, target_pages)

    for page in iter_rendered_pages(
        path,
        dpi=DEFAULT_PREVIEW_RENDER_DPI,
        max_side=NORMALIZED_PREVIEW_MAX_SIDE,
        image_format="JPEG",
        jpeg_quality=PREVIEW_JPEG_QUALITY,
        image_rotation_degrees_by_page=cache_options.rotation_degrees_by_page or {},
        page_numbers=target_pages,
    ):
        rendered.extend(write_page_variants(connection, file_hash, page, cache_dir))

    _log_render_complete(cache_options, rendered)
    return rendered


def ensure_document_preview_cache(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    *,
    options: PreviewCacheOptions | None = None,
) -> list[DocumentPreviewImage]:
    cached = read_document_preview_images(connection, file_hash)
    if cached and all(item.cache_path.exists() for item in cached):
        return cached
    return build_document_preview_cache(
        connection,
        path,
        file_hash,
        options=options,
    )


def ensure_document_preview_page(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    page_no: int,
    *,
    options: PreviewCacheOptions | None = None,
) -> list[DocumentPreviewImage]:
    cached = read_document_preview_images(connection, file_hash, page_no=page_no)
    if cached and all(item.cache_path.exists() for item in cached):
        return cached
    return build_document_preview_cache(
        connection,
        path,
        file_hash,
        options=options,
        page_numbers={page_no},
    )


def read_document_preview_images(
    connection: DuckConnection,
    file_hash: str,
    *,
    page_no: int | None = None,
    variant: str | None = None,
) -> list[DocumentPreviewImage]:
    if not table_exists(connection, "document_preview_images"):
        return []
    filters = ["file_hash = ?"]
    parameters: list[object] = [file_hash]
    if page_no is not None:
        filters.append("page_no = ?")
        parameters.append(page_no)
    if variant is not None:
        filters.append("variant = ?")
        parameters.append(variant)
    rows = connection.execute(
        f"""
        SELECT
            file_hash, page_no, variant, page_width, page_height,
            render_width, render_height, mime_type, image_bytes,
            image_sha256, cache_path, metadata_json
        FROM document_preview_images
        WHERE {" AND ".join(filters)}
        ORDER BY page_no, variant
        """,
        parameters,
    ).fetchall()
    return [preview_image_from_row(row) for row in rows]


def _delete_preview_rows(
    connection: DuckConnection,
    file_hash: str,
    page_numbers: set[int] | None,
) -> None:
    if page_numbers is None:
        connection.execute(
            "DELETE FROM document_preview_images WHERE file_hash = ?", [file_hash]
        )
        return
    for page_no in page_numbers:
        connection.execute(
            "DELETE FROM document_preview_images WHERE file_hash = ? AND page_no = ?",
            [file_hash, page_no],
        )


def _normalized_page_numbers(page_numbers: set[int] | None) -> set[int] | None:
    if page_numbers is None:
        return None
    return {page_no for page_no in page_numbers if page_no > 0}


def _log_render_start(
    options: PreviewCacheOptions,
    path: Path,
    cache_dir: Path,
    page_numbers: set[int] | None,
) -> None:
    if options.log is None:
        return
    page_text = (
        "all" if page_numbers is None else ",".join(map(str, sorted(page_numbers)))
    )
    options.log(
        f"Rendering preview cache: source={path} pages={page_text} cache_dir={cache_dir}"
    )


def _log_render_complete(
    options: PreviewCacheOptions,
    rendered: list[DocumentPreviewImage],
) -> None:
    if options.log is None:
        return
    page_count = len({image.page_no for image in rendered})
    options.log(f"Stored preview cache: pages={page_count} images={len(rendered)}")
