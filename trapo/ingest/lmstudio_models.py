from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from trapo.ingest.page_images import DEFAULT_MAX_SIDE, DEFAULT_RENDER_DPI
from trapo.ingest.page_markdown_images import (
    DEFAULT_PAGE_MARKDOWN_CACHE_ROOT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT,
    DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE,
    DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY,
    DEFAULT_PAGE_MARKDOWN_RENDER_DPI,
)


LMSTUDIO_ENGINE = "lmstudio"
LMSTUDIO_PROVIDER = "local-lmstudio"
DEFAULT_LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
DEFAULT_LMSTUDIO_MODEL = "google/gemma-4-26b-a4b-qat"
DEFAULT_LMSTUDIO_TIMEOUT_SECONDS = 900.0
DEFAULT_LMSTUDIO_CONTEXT_TOKENS = 262_144
DEFAULT_LMSTUDIO_ORIENTATION_MAX_SIDE = 1024
DEFAULT_LMSTUDIO_ORIENTATION_MIN_CONFIDENCE = 0.6
DEFAULT_LMSTUDIO_TEMPERATURE = 0.0
DEFAULT_LMSTUDIO_BOX_ORIGIN = "BOTTOMLEFT"


class LmStudioRegionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="region")
    region_kind: str = Field(default="text")
    text: str = Field(default="")
    box_2d: list[int] = Field(
        min_length=4,
        max_length=4,
        description=(
            "Bounding box as [y0, left, y1, right] on a 0-1000 grid. "
            "The y-axis origin is recorded by the engine output."
        ),
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_region_ids: list[str] = Field(default_factory=list)


class LmStudioPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_summary: str | None = None
    regions: list[LmStudioRegionCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LmStudioPageOrientationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clockwise_degrees: Literal[0, 90, 180, 270] = Field(
        description="Clockwise rotation needed to make the visible page upright."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    text_orientation: Literal[
        "upright",
        "rotated_clockwise",
        "rotated_counterclockwise",
        "upside_down",
        "unknown",
    ] = "unknown"
    rationale: str = ""
    warnings: list[str] = Field(default_factory=list)


class LmStudioPageMarkdownResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markdown: str = Field(
        description="Faithful Markdown representation of the visible page."
    )
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LmStudioReadResult:
    text: str
    data: dict[str, Any]
    provider: str = LMSTUDIO_PROVIDER
    model: str = DEFAULT_LMSTUDIO_MODEL


@dataclass(frozen=True)
class LmStudioOptions:
    base_url: str = DEFAULT_LMSTUDIO_BASE_URL
    model: str = DEFAULT_LMSTUDIO_MODEL
    timeout_seconds: float = DEFAULT_LMSTUDIO_TIMEOUT_SECONDS
    render_dpi: int = DEFAULT_RENDER_DPI
    image_max_side: int = DEFAULT_MAX_SIDE
    max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    temperature: float = DEFAULT_LMSTUDIO_TEMPERATURE
    box_origin: str = DEFAULT_LMSTUDIO_BOX_ORIGIN
    include_evidence: bool = True
    image_rotation_degrees_by_page: dict[int, int] = field(default_factory=dict)
    annotation_engine: str = LMSTUDIO_ENGINE
    prompt_profile: str = "balanced"
    profile_instructions: str = ""


@dataclass(frozen=True)
class LmStudioMarkdownOptions:
    base_url: str = DEFAULT_LMSTUDIO_BASE_URL
    model: str = DEFAULT_LMSTUDIO_MODEL
    timeout_seconds: float = DEFAULT_LMSTUDIO_TIMEOUT_SECONDS
    render_dpi: int = DEFAULT_PAGE_MARKDOWN_RENDER_DPI
    image_max_side: int = DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE
    image_format: str = DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT
    jpeg_quality: int = DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY
    cache_enabled: bool = True
    cache_root: str = DEFAULT_PAGE_MARKDOWN_CACHE_ROOT
    markdown_max_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    temperature: float = DEFAULT_LMSTUDIO_TEMPERATURE
    image_rotation_degrees_by_page: dict[int, int] = field(default_factory=dict)
    markdown_engine: str = "lmstudio_markdown"
