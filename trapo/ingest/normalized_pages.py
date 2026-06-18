from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from trapo.db import DuckConnection
from trapo.mineru_bbox import page_metadata
from trapo.page_orientation import read_page_orientation_overrides
from trapo.preview_cache import (
    DocumentPreviewImage,
    PreviewCacheOptions,
    build_document_preview_cache,
    read_document_preview_images,
)
from trapo.server.models import PageInfo

NORMALIZED_PREVIEW_VARIANT = "normalized"


@dataclass(frozen=True)
class NormalizedPreviewPage:
    page_no: int
    image_path: Path
    page: PageInfo
    image_sha256: str


def normalized_preview_pages(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    log: Callable[[str], None] | None = None,
) -> list[NormalizedPreviewPage]:
    images = _normalized_images(connection, file_hash)
    if not images or not all(image.cache_path.exists() for image in images):
        overrides = read_page_orientation_overrides(connection, file_hash)
        build_document_preview_cache(
            connection,
            path,
            file_hash,
            options=PreviewCacheOptions(
                rotation_degrees_by_page={
                    page_no: override.clockwise_degrees
                    for page_no, override in overrides.items()
                },
                log=log,
            ),
        )
        images = _normalized_images(connection, file_hash)
    return [
        NormalizedPreviewPage(
            page_no=image.page_no,
            image_path=image.cache_path,
            page=PageInfo(
                page_no=image.page_no,
                width=float(image.render_width),
                height=float(image.render_height),
            ),
            image_sha256=image.image_sha256,
        )
        for image in images
        if image.cache_path.exists()
    ]


def normalized_metadata(pages: list[NormalizedPreviewPage]) -> dict[str, object]:
    return {
        "input": "normalized_preview_jpg",
        "variant": NORMALIZED_PREVIEW_VARIANT,
        "pages": [
            {
                "page_no": page.page_no,
                "image_path": str(page.image_path),
                "image_sha256": page.image_sha256,
                "target_page": page_metadata(page.page),
            }
            for page in pages
        ],
    }


def _normalized_images(
    connection: DuckConnection,
    file_hash: str,
) -> list[DocumentPreviewImage]:
    return read_document_preview_images(
        connection,
        file_hash,
        variant=NORMALIZED_PREVIEW_VARIANT,
    )
