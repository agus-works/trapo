from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.ingest.page_images import RenderedPageImage


DEFAULT_PAGE_MARKDOWN_RENDER_DPI = 120
DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE = 1280
DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT = "JPEG"
DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY = 82
DEFAULT_PAGE_MARKDOWN_CACHE_ROOT = ".cache/trapo/page-markdown"
CACHE_SCHEMA_VERSION = 2
MAX_MARKDOWN_CACHE_MANIFEST_BYTES = 1024 * 1024
MAX_MARKDOWN_CACHE_METADATA_BYTES = 1024 * 1024
MAX_MARKDOWN_CACHE_IMAGE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class MarkdownPageImage:
    page: RenderedPageImage
    cache_hit: bool
    image_path: Path | None
    metadata_path: Path | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MarkdownRenderOptions:
    file_hash: str
    render_dpi: int = DEFAULT_PAGE_MARKDOWN_RENDER_DPI
    image_max_side: int = DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE
    image_format: str = DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT
    jpeg_quality: int = DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY
    cache_enabled: bool = True
    cache_root: str = DEFAULT_PAGE_MARKDOWN_CACHE_ROOT
    image_rotation_degrees_by_page: dict[int, int] | None = None
