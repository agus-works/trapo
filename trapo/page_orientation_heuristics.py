from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import median
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.page_orientation import PageOrientationOverrideUpdate
from trapo.server.models import PageInfo, RawBBox
from trapo.server.provenance import parse_json_value


MIN_TEXT_LENGTH = 8
MIN_VERTICAL_BOXES = 3
VERTICAL_ASPECT_RATIO = 2.0
MIN_VERTICAL_RATIO = 0.4
LEFT_ROTATION_THRESHOLD = 0.45
RIGHT_ROTATION_THRESHOLD = 0.55


@dataclass(frozen=True)
class LayoutCandidate:
    x_center: float
    y_center: float
    vertical: bool


def infer_docling_image_rotation(
    connection: DuckConnection,
    *,
    file_hash: str,
    page: PageInfo,
) -> PageOrientationOverrideUpdate | None:
    """Infer no-EXIF image rotation from Docling text-box layout when possible."""
    override: PageOrientationOverrideUpdate | None = None
    if table_exists(connection, "document_regions"):
        rows = connection.execute(
            """
            SELECT text, raw_bbox_json
            FROM document_regions
            WHERE file_hash = ?
              AND page_no = ?
              AND annotation_engine = 'docling'
              AND region_kind IN ('text', 'title', 'header', 'footer')
            """,
            [file_hash, page.page_no],
        ).fetchall()
        candidates = [
            candidate for row in rows if (candidate := _candidate(row[0], row[1], page))
        ]
        if len(candidates) >= MIN_VERTICAL_BOXES:
            override = _override_from_candidates(file_hash, page, candidates)
    return override


def _override_from_candidates(
    file_hash: str,
    page: PageInfo,
    candidates: list[LayoutCandidate],
) -> PageOrientationOverrideUpdate | None:
    override: PageOrientationOverrideUpdate | None = None
    vertical_candidates = [candidate for candidate in candidates if candidate.vertical]
    vertical_ratio = len(vertical_candidates) / len(candidates)
    if (
        len(vertical_candidates) >= MIN_VERTICAL_BOXES
        and vertical_ratio >= MIN_VERTICAL_RATIO
    ):
        median_x_pct = median(
            candidate.x_center for candidate in vertical_candidates
        ) / max(page.width, 1.0)
        degrees = _rotation_from_median_x(median_x_pct)
        if degrees is not None:
            confidence = min(0.9, 0.55 + (vertical_ratio * 0.35))
            override = PageOrientationOverrideUpdate(
                file_hash=file_hash,
                page_no=page.page_no,
                clockwise_degrees=degrees,
                source="docling_layout_heuristic",
                confidence=confidence,
                metadata={
                    "eligible_box_count": len(candidates),
                    "vertical_box_count": len(vertical_candidates),
                    "vertical_ratio": vertical_ratio,
                    "median_x_pct": median_x_pct,
                },
            )
    return override


def _rotation_from_median_x(median_x_pct: float) -> int | None:
    degrees: int | None = None
    if median_x_pct >= RIGHT_ROTATION_THRESHOLD:
        degrees = 90
    elif median_x_pct <= LEFT_ROTATION_THRESHOLD:
        degrees = 270
    return degrees


def _candidate(
    text_value: object, bbox_value: object, page: PageInfo
) -> LayoutCandidate | None:
    candidate: LayoutCandidate | None = None
    text = str(text_value or "").strip()
    if len(text) >= MIN_TEXT_LENGTH:
        bbox = _raw_bbox(bbox_value)
        if bbox is not None:
            left = min(bbox.left, bbox.right)
            width = abs(bbox.right - bbox.left)
            if bbox.coord_origin.upper() == "TOPLEFT":
                top = min(bbox.top, bbox.bottom)
                height = abs(bbox.bottom - bbox.top)
            else:
                top = page.height - max(bbox.top, bbox.bottom)
                height = abs(bbox.top - bbox.bottom)
            if width > 0 and height > 0:
                candidate = LayoutCandidate(
                    x_center=left + (width / 2.0),
                    y_center=top + (height / 2.0),
                    vertical=height / width >= VERTICAL_ASPECT_RATIO,
                )
    return candidate


def _raw_bbox(value: object) -> RawBBox | None:
    data: dict[str, Any]
    if isinstance(value, str):
        data = parse_json_value(value)
    elif isinstance(value, dict):
        data = value
    else:
        try:
            data = parse_json_value(json.dumps(value))
        except TypeError:
            data = {}
    if not data:
        return None
    try:
        return RawBBox.model_validate(data)
    except ValueError:
        return None
