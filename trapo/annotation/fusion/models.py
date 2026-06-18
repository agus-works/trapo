from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trapo.server.models import RawBBox


FUSION_ENGINE = "fusion"
FUSION_PROVIDER = "trapo"
FUSION_MODEL = "trapo-region-fusion-v1"
SOURCE_ENGINES = {"docling", "mineru", "lmstudio", "infinity"}
CORE_SOURCE_ENGINES = {"docling", "mineru", "lmstudio"}


@dataclass(frozen=True)
class FusionCandidate:
    region_id: str
    overlay_id: str
    annotation_engine: str
    page_no: int
    label: str
    region_kind: str
    text: str
    raw_bbox: RawBBox
    area: float


@dataclass(frozen=True)
class FusedRegion:
    source_ref: str
    page_no: int
    label: str
    region_kind: str
    text: str
    raw_bbox: RawBBox
    metadata: dict[str, Any]


@dataclass(frozen=True)
class FusionResult:
    text: str
    data: dict[str, Any]
    region_count: int
