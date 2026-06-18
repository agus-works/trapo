from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.annotation.docling.regions import rebuild_document_terms
from trapo.ingest.lmstudio_models import LMSTUDIO_ENGINE, LMSTUDIO_PROVIDER
from trapo.mineru_bbox import page_metadata
from trapo.server.models import PageInfo, RawBBox
from trapo.server.provenance import parse_json_value


KNOWN_REGION_KINDS = {
    "text",
    "title",
    "table",
    "table_cell",
    "formula",
    "image",
    "chart",
    "code",
    "list",
    "header",
    "footer",
    "footnote",
    "page_number",
    "signature",
    "checkbox",
    "stamp",
    "other",
}
BOX_2D_VALUE_COUNT = 4
BOTTOMLEFT_ORIGIN = "BOTTOMLEFT"
TOPLEFT_ORIGIN = "TOPLEFT"


@dataclass(frozen=True)
class LmStudioRegion:
    source_ref: str
    page_no: int
    label: str
    region_kind: str
    text: str
    raw_bbox: RawBBox
    metadata: dict[str, Any]


def rebuild_lmstudio_document_regions(
    connection: DuckConnection,
    file_hash: str,
    lmstudio_output_json: object,
    *,
    annotation_engine: str | None = None,
) -> int:
    """Persist LM Studio page regions for one file."""
    if not table_exists(connection, "document_regions"):
        return 0
    data = parse_json_value(lmstudio_output_json)
    engine = _annotation_engine(data, annotation_engine)
    _delete_lmstudio_regions(connection, file_hash, engine)
    regions = _lmstudio_regions(data, engine)
    inserted = 0
    for region in regions:
        region_id = _region_id(file_hash, region, engine)
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, annotation_engine, annotation_provider,
                annotation_model, chunk_id, chunk_index, page_no, source_ref,
                parent_ref, label, text, context_text, raw_bbox_json,
                region_kind, metadata_json
            )
            VALUES (
                ?, ?, ?, ?, ?, NULL, NULL, ?, ?,
                NULL, ?, ?, ?, ?::JSON, ?, ?::JSON
            )
            ON CONFLICT (region_id) DO UPDATE SET
                annotation_engine = excluded.annotation_engine,
                annotation_provider = excluded.annotation_provider,
                annotation_model = excluded.annotation_model,
                page_no = excluded.page_no,
                source_ref = excluded.source_ref,
                label = excluded.label,
                text = excluded.text,
                context_text = excluded.context_text,
                raw_bbox_json = excluded.raw_bbox_json,
                region_kind = excluded.region_kind,
                metadata_json = excluded.metadata_json,
                updated_at = now()
            """,
            [
                region_id,
                file_hash,
                engine,
                LMSTUDIO_PROVIDER,
                str(region.metadata.get("model") or data.get("model") or "lmstudio"),
                region.page_no,
                region.source_ref,
                region.label,
                region.text,
                region.text,
                json.dumps(region.raw_bbox.model_dump()),
                region.region_kind,
                json.dumps(region.metadata),
            ],
        )
        inserted += 1
    rebuild_document_terms(connection, file_hash)
    return inserted


def _lmstudio_regions(
    data: dict[str, Any], annotation_engine: str
) -> list[LmStudioRegion]:
    pages = data.get("pages")
    if not isinstance(pages, list):
        return []
    regions: list[LmStudioRegion] = []
    model = str(data.get("model") or "lmstudio")
    box_origin = _box_origin(data.get("box_2d_coord_origin"))
    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        page_info = _page_info(page, page_index)
        if page_info is None:
            continue
        page_regions = page.get("regions")
        if not isinstance(page_regions, list):
            continue
        for region_index, item in enumerate(page_regions):
            if not isinstance(item, dict):
                continue
            raw_bbox = _bbox_from_box_2d(item.get("box_2d"), page_info, box_origin)
            if raw_bbox is None:
                continue
            label = str(
                item.get("label") or item.get("region_kind") or "lmstudio_region"
            )
            region_kind = _region_kind(item.get("region_kind"))
            text = _region_text(item, label)
            regions.append(
                LmStudioRegion(
                    source_ref=f"lmstudio:page:{page_info.page_no}:region:{region_index}",
                    page_no=page_info.page_no,
                    label=label,
                    region_kind=region_kind,
                    text=text,
                    raw_bbox=raw_bbox,
                    metadata={
                        "source": "lmstudio_page_json",
                        "annotation_engine": annotation_engine,
                        "model": model,
                        "prompt_profile": data.get("prompt_profile"),
                        "profile_instructions": data.get("profile_instructions"),
                        "raw_item": item,
                        "page": page_metadata(page_info),
                        "box_2d_coord_origin": box_origin,
                        "page_summary": page.get("page_summary"),
                        "page_warnings": page.get("warnings"),
                        "render_width": page.get("render_width"),
                        "render_height": page.get("render_height"),
                        "render_sha256": page.get("render_sha256"),
                        "evidence_count": page.get("evidence_count"),
                    },
                )
            )
    return regions


def _bbox_from_box_2d(value: object, page: PageInfo, box_origin: str) -> RawBBox | None:
    values = _box_2d_values(value)
    if values is None:
        return None
    y0, left, y1, right = values
    y0 = _clamp(y0, 0.0, 1000.0)
    left = _clamp(left, 0.0, 1000.0)
    y1 = _clamp(y1, 0.0, 1000.0)
    right = _clamp(right, 0.0, 1000.0)
    if y1 <= y0 or right <= left:
        return None
    top, bottom = _display_y_interval(y0, y1, page, box_origin)
    return RawBBox(
        left=left / 1000.0 * page.width,
        top=top,
        right=right / 1000.0 * page.width,
        bottom=bottom,
        coord_origin="TOPLEFT",
    )


def _display_y_interval(
    y0: float, y1: float, page: PageInfo, box_origin: str
) -> tuple[float, float]:
    if box_origin == BOTTOMLEFT_ORIGIN:
        return (1000.0 - y1) / 1000.0 * page.height, (
            1000.0 - y0
        ) / 1000.0 * page.height
    return y0 / 1000.0 * page.height, y1 / 1000.0 * page.height


def _box_origin(value: object) -> str:
    normalized = str(value or "").strip().upper().replace("-", "").replace("_", "")
    if normalized in {"BOTTOMLEFT", "BOTTOM"}:
        return BOTTOMLEFT_ORIGIN
    return TOPLEFT_ORIGIN


def _annotation_engine(data: dict[str, Any], override: str | None) -> str:
    candidate = (override or str(data.get("engine") or "")).strip().lower()
    return candidate or LMSTUDIO_ENGINE


def _box_2d_values(value: object) -> tuple[float, float, float, float] | None:
    result: tuple[float, float, float, float] | None = None
    if isinstance(value, list) and len(value) == BOX_2D_VALUE_COUNT:
        top = _float_or_none(value[0])
        left = _float_or_none(value[1])
        bottom = _float_or_none(value[2])
        right = _float_or_none(value[3])
        if (
            top is not None
            and left is not None
            and bottom is not None
            and right is not None
        ):
            result = (top, left, bottom, right)
    return result


def _page_info(page: dict[str, Any], fallback_page_no: int) -> PageInfo | None:
    width = _float_or_none(page.get("width"))
    height = _float_or_none(page.get("height"))
    if width is None or height is None or width <= 0 or height <= 0:
        return None
    return PageInfo(
        page_no=_int_or_none(page.get("page_no")) or fallback_page_no,
        width=width,
        height=height,
    )


def _region_kind(value: object) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in KNOWN_REGION_KINDS else "other"


def _region_text(item: dict[str, Any], fallback: str) -> str:
    text = item.get("text")
    if isinstance(text, str) and text.strip():
        return " ".join(text.split())
    return fallback


def _delete_lmstudio_regions(
    connection: DuckConnection,
    file_hash: str,
    annotation_engine: str,
) -> None:
    if table_exists(connection, "document_terms"):
        connection.execute(
            "DELETE FROM document_terms WHERE file_hash = ? AND annotation_engine = ?",
            [file_hash, annotation_engine],
        )
    connection.execute(
        "DELETE FROM document_regions WHERE file_hash = ? AND annotation_engine = ?",
        [file_hash, annotation_engine],
    )


def _region_id(file_hash: str, region: LmStudioRegion, annotation_engine: str) -> str:
    key = "|".join(
        str(part)
        for part in (
            file_hash,
            annotation_engine,
            region.source_ref,
            region.page_no,
            round(region.raw_bbox.left, 3),
            round(region.raw_bbox.top, 3),
            round(region.raw_bbox.right, 3),
            round(region.raw_bbox.bottom, 3),
        )
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value)
    return result


def _float_or_none(value: object) -> float | None:
    result: float | None = None
    if isinstance(value, int | float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            result = None
    return result


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
