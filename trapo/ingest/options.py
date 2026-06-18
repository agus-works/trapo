from __future__ import annotations

from dataclasses import dataclass

from trapo.annotation.fusion.profiles import DEFAULT_FUSION_PROFILE
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_BOX_ORIGIN,
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    DEFAULT_LMSTUDIO_MODEL,
    DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE,
    DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE,
    DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
)
from trapo.ingest.page_markdown_images import (
    DEFAULT_PAGE_MARKDOWN_CACHE_ROOT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE,
    DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    DEFAULT_PAGE_MARKDOWN_RENDER_DPI,
)

DEFAULT_DOCLING_BATCH_SIZE = 1
DEFAULT_DOCLING_QUEUE_MAX_SIZE = 8
DEFAULT_MINERU_PROCESSING_WINDOW_SIZE = 16


@dataclass(frozen=True)
class IngestOptions:
    reprocess: bool = False
    max_chars: int = 4000
    overlap_chars: int = 400
    chunker: str = "docling-hybrid"
    max_chunk_tokens: int = 1200
    docling_device: str = "auto"
    docling_num_threads: int = 4
    docling_page_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    docling_ocr_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    docling_layout_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    docling_table_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    docling_queue_max_size: int = DEFAULT_DOCLING_QUEUE_MAX_SIZE
    annotation_engines: str = "docling,mineru"
    mineru_backend: str = "pipeline"
    mineru_parse_method: str = "auto"
    mineru_language: str = "en"
    mineru_processing_window_size: int = DEFAULT_MINERU_PROCESSING_WINDOW_SIZE
    lmstudio_base_url: str = DEFAULT_LMSTUDIO_BASE_URL
    lmstudio_model: str = DEFAULT_LMSTUDIO_MODEL
    lmstudio_timeout_seconds: float = DEFAULT_LMSTUDIO_TIMEOUT_SECONDS
    lmstudio_render_dpi: int = 200
    lmstudio_image_max_side: int = 2048
    lmstudio_max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    lmstudio_box_origin: str = DEFAULT_LMSTUDIO_BOX_ORIGIN
    lmstudio_include_evidence: bool = True
    lmstudio_profiles: str = "balanced"
    lmstudio_orientation: str = "auto"
    lmstudio_orientation_min_confidence: float = (
        DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE
    )
    lmstudio_orientation_max_side: int = DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE
    lmstudio_orientation_max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    lmstudio_maximize_context: bool = True
    page_markdown: bool = True
    page_markdown_engines: str = "markitdown"
    page_markdown_render_dpi: int = DEFAULT_PAGE_MARKDOWN_RENDER_DPI
    page_markdown_image_max_side: int = DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE
    page_markdown_image_format: str = DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT
    page_markdown_jpeg_quality: int = DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY
    page_markdown_cache: bool = True
    page_markdown_cache_root: str = DEFAULT_PAGE_MARKDOWN_CACHE_ROOT
    page_markdown_max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    markitdown_lmstudio_ocr: bool = False
    markitdown_content_understanding: bool = False
    markitdown_cu_endpoint: str = ""
    markitdown_cu_analyzer: str = ""
    fuse_regions: bool = True
    fusion_profiles: str = DEFAULT_FUSION_PROFILE
    verbosity: int = 0


@dataclass(frozen=True)
class IngestSummary:
    files_seen: int
    files_processed: int
    files_skipped: int
    chunks_created: int
    errors: int
