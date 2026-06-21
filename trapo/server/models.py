from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, PrivateAttr


class HealthResponse(BaseModel):
    status: str = "ok"
    db_path: str
    runtime_id: str | None = None
    source_root: str | None = None


class DatabaseStatusResponse(BaseModel):
    db_path: str
    schema_version: str | None = None
    files: int = 0
    chunks: int = 0
    regions: int = 0
    terms: int = 0
    failed_docs: int = 0
    runtime_id: str | None = None
    source_root: str | None = None


class SearchHighlightRecord(BaseModel):
    field: str
    start: int
    end: int
    match_kind: str
    source: Literal[
        "exact_phrase",
        "exact_token",
        "fuzzy_alignment",
        "fts_term",
        "region_fallback",
        "chunk_fallback",
    ]
    score_contribution: float = 0.0


class CommandActionRecord(BaseModel):
    type: str
    route: str | None = None
    search: dict[str, object] = Field(default_factory=dict)


class CommandSearchResultRecord(BaseModel):
    command_id: str
    label: str
    description: str
    group: str
    score: float
    action: CommandActionRecord
    highlights: list[SearchHighlightRecord] = Field(default_factory=list)
    shortcut: str | None = None


class GlobalSearchResultRecord(BaseModel):
    result_id: str
    source_type: str
    source_id: str
    label: str
    snippet: str
    route: dict[str, object] = Field(default_factory=dict)
    score: float
    rank_source: str
    navigation_granularity: Literal["word", "region", "chunk", "file", "record"]
    highlights: list[SearchHighlightRecord] = Field(default_factory=list)
    file_hash: str | None = None
    chunk_id: int | None = None
    region_id: str | None = None
    page_no: int | None = None
    word_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentSummary(BaseModel):
    file_hash: str
    filename: str
    extension: str | None = None
    size_bytes: int
    modified_at: datetime | None = None
    created_at: datetime | None = None
    path: str | None = None
    docling_status: str | None = None
    docling_error: str | None = None
    mineru_status: str | None = None
    mineru_error: str | None = None
    infinity_status: str | None = None
    infinity_error: str | None = None
    chunk_count: int = 0
    region_count: int = 0


class PageInfo(BaseModel):
    page_no: int
    width: float
    height: float
    _image_base_height: float | None = PrivateAttr(default=None)
    _image_base_width: float | None = PrivateAttr(default=None)
    _image_orientation: int | None = PrivateAttr(default=None)
    _image_rotation_degrees: int = PrivateAttr(default=0)
    _source_height: float | None = PrivateAttr(default=None)
    _source_width: float | None = PrivateAttr(default=None)


class RawBBox(BaseModel):
    left: float = Field(validation_alias=AliasChoices("left", "l"))
    top: float = Field(validation_alias=AliasChoices("top", "t"))
    right: float = Field(validation_alias=AliasChoices("right", "r"))
    bottom: float = Field(validation_alias=AliasChoices("bottom", "b"))
    coord_origin: str = "BOTTOMLEFT"


class NormalizedBBox(BaseModel):
    left_pct: float
    top_pct: float
    width_pct: float
    height_pct: float


class AnnotationStyle(BaseModel):
    stroke_color: str
    fill_color: str
    stroke_opacity: float = 0.82
    fill_opacity: float = 0.14
    stroke_width: float = 2.0


class OverlayBox(BaseModel):
    overlay_id: str
    file_hash: str
    annotation_engine: str = "docling"
    annotation_provider: str = "local-docling"
    annotation_model: str = "docling"
    chunk_id: int
    chunk_index: int
    page_no: int
    raw_bbox: RawBBox
    bbox: NormalizedBBox
    source_ref: str | None = None
    label: str | None = None
    region_kind: str = "text"
    text_preview: str
    hidden: bool = False
    style: AnnotationStyle


class DocumentDetail(DocumentSummary):
    pages: list[PageInfo] = Field(default_factory=list)


class DocumentPreviewImageRecord(BaseModel):
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
    url: str
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentPreviewImagesPayload(BaseModel):
    document: DocumentDetail
    images: list[DocumentPreviewImageRecord] = Field(default_factory=list)


class DocumentRegionsPayload(BaseModel):
    document: DocumentDetail
    overlays: list[OverlayBox]


class MarkdownRegionSpan(BaseModel):
    anchor_id: str
    region_id: str
    char_start: int
    char_end: int
    confidence: float | None = None
    markdown_excerpt: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class PageMarkdownRecord(BaseModel):
    page_no: int
    markdown_engine: str
    markdown_provider: str
    markdown_model: str
    markdown_text: str
    page_width: float | None = None
    page_height: float | None = None
    render_sha256: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    mappings: list[MarkdownRegionSpan] = Field(default_factory=list)


class MarkdownEngineRecord(BaseModel):
    markdown_engine: str
    label: str
    markdown_provider: str = ""
    markdown_model: str = ""
    status: str | None = None
    error: str | None = None
    page_count: int = 0
    is_virtual: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentMarkdownPayload(BaseModel):
    document: DocumentDetail
    markdown_engine: str
    available_engines: list[MarkdownEngineRecord] = Field(default_factory=list)
    pages: list[PageMarkdownRecord] = Field(default_factory=list)


class AnnotationStyleSetting(BaseModel):
    annotation_engine: str
    region_kind: str
    label: str = ""
    style: AnnotationStyle


class AnnotationSettingsPayload(BaseModel):
    settings: list[AnnotationStyleSetting]


class AnnotationVisibilityOverride(BaseModel):
    overlay_id: str
    hidden: bool


class AnnotationVisibilityUpdate(BaseModel):
    overrides: list[AnnotationVisibilityOverride]


class AnnotationVisibilityResponse(BaseModel):
    updated: int
