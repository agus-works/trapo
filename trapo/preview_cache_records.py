from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from trapo.db import DuckConnection
from trapo.filesystem_safety import write_bytes_file
from trapo.ingest.page_images import RenderedPageImage


PREVIEW_JPEG_QUALITY = 88
PREVIEW_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PreviewVariantSpec:
    variant: str
    max_side: int


@dataclass(frozen=True)
class DocumentPreviewImage:
    file_hash: str
    page_no: int
    variant: str
    page_width: float
    page_height: float
    render_width: int
    render_height: int
    mime_type: str
    image_bytes: int
    image_sha256: str
    cache_path: Path
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ImageRecordRequest:
    file_hash: str
    page: RenderedPageImage
    variant: str
    content: bytes
    render_size: tuple[int, int]
    cache_dir: Path


PREVIEW_VARIANTS: tuple[PreviewVariantSpec, ...] = (
    PreviewVariantSpec("normalized", 1600),
    PreviewVariantSpec("thumb_sm", 48),
    PreviewVariantSpec("thumb_md", 96),
    PreviewVariantSpec("thumb_lg", 160),
    PreviewVariantSpec("thumb_xl", 256),
)


def preview_variant_names() -> set[str]:
    return {spec.variant for spec in PREVIEW_VARIANTS}


def write_page_variants(
    connection: DuckConnection,
    file_hash: str,
    page: RenderedPageImage,
    cache_dir: Path,
) -> list[DocumentPreviewImage]:
    images: list[DocumentPreviewImage] = []
    with Image.open(BytesIO(page.image_bytes)) as source:
        normalized = source.convert("RGB")
        for spec in PREVIEW_VARIANTS:
            image = _resized_image(normalized, max_side=spec.max_side)
            content = _jpeg_bytes(image)
            record = _write_image_record(
                connection,
                ImageRecordRequest(
                    file_hash=file_hash,
                    page=page,
                    variant=spec.variant,
                    content=content,
                    render_size=image.size,
                    cache_dir=cache_dir,
                ),
            )
            images.append(record)
    return images


def preview_image_from_row(row: tuple[object, ...]) -> DocumentPreviewImage:
    metadata = row[11]
    if isinstance(metadata, str):
        parsed_metadata = json.loads(metadata)
    elif isinstance(metadata, dict):
        parsed_metadata = metadata
    else:
        parsed_metadata = {}
    return DocumentPreviewImage(
        file_hash=str(row[0]),
        page_no=int(str(row[1])),
        variant=str(row[2]),
        page_width=float(str(row[3])),
        page_height=float(str(row[4])),
        render_width=int(str(row[5])),
        render_height=int(str(row[6])),
        mime_type=str(row[7]),
        image_bytes=int(str(row[8])),
        image_sha256=str(row[9]),
        cache_path=Path(str(row[10])),
        metadata=parsed_metadata,
    )


def _write_image_record(
    connection: DuckConnection,
    request: ImageRecordRequest,
) -> DocumentPreviewImage:
    image_sha256 = hashlib.sha256(request.content).hexdigest()
    cache_path = (
        request.cache_dir / f"page-{request.page.page_no:04d}-{request.variant}.jpg"
    )
    write_bytes_file(cache_path, request.content, root=request.cache_dir)
    metadata = {
        "schema_version": PREVIEW_CACHE_SCHEMA_VERSION,
        "variant": request.variant,
        "source_render_sha256": request.page.image_sha256,
        "preview_jpeg_quality": PREVIEW_JPEG_QUALITY,
    }
    connection.execute(
        """
        INSERT INTO document_preview_images (
            file_hash, page_no, variant, page_width, page_height,
            render_width, render_height, mime_type, image_bytes,
            image_sha256, cache_path, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
        ON CONFLICT (file_hash, page_no, variant) DO UPDATE SET
            page_width = excluded.page_width,
            page_height = excluded.page_height,
            render_width = excluded.render_width,
            render_height = excluded.render_height,
            mime_type = excluded.mime_type,
            image_bytes = excluded.image_bytes,
            image_sha256 = excluded.image_sha256,
            cache_path = excluded.cache_path,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            request.file_hash,
            request.page.page_no,
            request.variant,
            request.page.width,
            request.page.height,
            request.render_size[0],
            request.render_size[1],
            "image/jpeg",
            len(request.content),
            image_sha256,
            str(cache_path),
            json.dumps(metadata),
        ],
    )
    return DocumentPreviewImage(
        file_hash=request.file_hash,
        page_no=request.page.page_no,
        variant=request.variant,
        page_width=request.page.width,
        page_height=request.page.height,
        render_width=request.render_size[0],
        render_height=request.render_size[1],
        mime_type="image/jpeg",
        image_bytes=len(request.content),
        image_sha256=image_sha256,
        cache_path=cache_path,
        metadata=metadata,
    )


def _resized_image(image: Image.Image, *, max_side: int) -> Image.Image:
    longest_side = max(image.size)
    if longest_side <= max_side:
        return image.copy()
    scale = max_side / longest_side
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _jpeg_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=PREVIEW_JPEG_QUALITY, optimize=True)
    return output.getvalue()
