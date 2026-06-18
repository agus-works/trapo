from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from trapo.db import DuckConnection
from trapo.page_orientation import read_page_orientation_overrides
from trapo.preview_cache import (
    DocumentPreviewImage,
    PreviewCacheOptions,
    ensure_document_preview_cache,
    ensure_document_preview_page,
    preview_variant_names,
    read_document_preview_images,
)
from trapo.server.models import (
    DocumentDetail,
    DocumentPreviewImageRecord,
    DocumentPreviewImagesPayload,
)


def preview_images_payload(
    con: DuckConnection,
    file_hash: str,
    detail: DocumentDetail,
    path: Path,
) -> DocumentPreviewImagesPayload:
    images = _ensure_preview_cache(con, path, file_hash)
    return DocumentPreviewImagesPayload(
        document=detail,
        images=[_preview_image_response(image) for image in images],
    )


def preview_image_for_file(
    con: DuckConnection,
    file_hash: str,
    variant: str,
    page_no: int,
    path: Path,
) -> DocumentPreviewImage:
    if page_no <= 0:
        raise HTTPException(
            status_code=400, detail="Preview page must be greater than zero."
        )
    if variant not in preview_variant_names():
        allowed = ", ".join(sorted(preview_variant_names()))
        raise HTTPException(
            status_code=404,
            detail=f"Unknown preview image variant: {variant}. Allowed: {allowed}",
        )

    _ensure_preview_page(con, path, file_hash, page_no)
    matches = read_document_preview_images(
        con, file_hash, page_no=page_no, variant=variant
    )
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"Preview image not found: page {page_no} {variant}",
        )

    image = matches[0]
    if not image.cache_path.exists():
        images = _ensure_preview_page(con, path, file_hash, page_no)
        image = next(
            (
                item
                for item in images
                if item.page_no == page_no
                and item.variant == variant
                and item.cache_path.exists()
            ),
            image,
        )
    if not image.cache_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Cached preview image is missing: {image.cache_path}",
        )
    return image


def _ensure_preview_cache(
    con: DuckConnection,
    path: Path,
    file_hash: str,
) -> list[DocumentPreviewImage]:
    overrides = read_page_orientation_overrides(con, file_hash)
    return ensure_document_preview_cache(
        con,
        path,
        file_hash,
        options=PreviewCacheOptions(
            rotation_degrees_by_page={
                page_no: override.clockwise_degrees
                for page_no, override in overrides.items()
            },
        ),
    )


def _ensure_preview_page(
    con: DuckConnection,
    path: Path,
    file_hash: str,
    page_no: int,
) -> list[DocumentPreviewImage]:
    overrides = read_page_orientation_overrides(con, file_hash)
    return ensure_document_preview_page(
        con,
        path,
        file_hash,
        page_no,
        options=PreviewCacheOptions(
            rotation_degrees_by_page={
                page_no: override.clockwise_degrees
                for page_no, override in overrides.items()
            },
        ),
    )


def _preview_image_response(image: DocumentPreviewImage) -> DocumentPreviewImageRecord:
    return DocumentPreviewImageRecord(
        file_hash=image.file_hash,
        page_no=image.page_no,
        variant=image.variant,
        page_width=image.page_width,
        page_height=image.page_height,
        render_width=image.render_width,
        render_height=image.render_height,
        mime_type=image.mime_type,
        image_bytes=image.image_bytes,
        image_sha256=image.image_sha256,
        url=(
            f"/api/documents/{image.file_hash}/preview-images/"
            f"{image.variant}/{image.page_no}"
        ),
        metadata=image.metadata,
    )
