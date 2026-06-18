from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


LMSTUDIO_MARKDOWN_ENGINE = "lmstudio_markdown"
INFINITY_MARKDOWN_ENGINE = "infinity_markdown"
MARKITDOWN_MARKDOWN_ENGINE = "markitdown"
MARKITDOWN_CU_MARKDOWN_ENGINE = "markitdown_cu"
BEST_AVAILABLE_MARKDOWN_ENGINE = "best_available_markdown"
DEFAULT_MARKDOWN_ENGINE = LMSTUDIO_MARKDOWN_ENGINE
DEFAULT_MARKDOWN_PROVIDER = "local-lmstudio"
MARKDOWN_ENGINE_PRIORITY = (
    LMSTUDIO_MARKDOWN_ENGINE,
    INFINITY_MARKDOWN_ENGINE,
    MARKITDOWN_MARKDOWN_ENGINE,
    MARKITDOWN_CU_MARKDOWN_ENGINE,
)
MARKDOWN_ENGINE_LABELS = {
    BEST_AVAILABLE_MARKDOWN_ENGINE: "Best available",
    LMSTUDIO_MARKDOWN_ENGINE: "LM Studio",
    INFINITY_MARKDOWN_ENGINE: "Infinity Parser2",
    MARKITDOWN_MARKDOWN_ENGINE: "MarkItDown",
    MARKITDOWN_CU_MARKDOWN_ENGINE: "MarkItDown CU",
}


@dataclass(frozen=True)
class MarkdownRegionMapping:
    anchor_id: str
    region_id: str
    char_start: int
    char_end: int
    confidence: float | None = None
    markdown_excerpt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageMarkdown:
    file_hash: str
    page_no: int
    markdown_text: str
    markdown_engine: str = DEFAULT_MARKDOWN_ENGINE
    markdown_provider: str = DEFAULT_MARKDOWN_PROVIDER
    markdown_model: str = ""
    page_width: float | None = None
    page_height: float | None = None
    render_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    mappings: list[MarkdownRegionMapping] = field(default_factory=list)


@dataclass(frozen=True)
class MarkdownEngineStatus:
    markdown_engine: str
    label: str
    markdown_provider: str = ""
    markdown_model: str = ""
    status: str | None = None
    error: str | None = None
    page_count: int = 0
    is_virtual: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarkdownGeneratorRecord:
    file_hash: str
    markdown_engine: str
    ingest_run_id: int
    markdown_provider: str
    markdown_model: str
    status: str
    page_count: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
