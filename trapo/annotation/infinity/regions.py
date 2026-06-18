from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from trapo.annotation.docling.regions import rebuild_document_terms
from trapo.annotation.infinity.bbox import bbox_from_infinity_item, bbox_value
from trapo.db import DuckConnection, table_exists
from trapo.ingest.infinity_models import INFINITY_ENGINE, INFINITY_PROVIDER
from trapo.mineru_bbox import page_metadata
from trapo.server.models import PageInfo, RawBBox
from trapo.server.provenance import parse_json_value


REGION_KIND_BY_CATEGORY = {
    "header": "header",
    "title": "title",
    "text": "text",
    "figure": "image",
    "image": "image",
    "chart": "chart",
    "table": "table",
    "formula": "formula",
    "footer": "footer",
    "figure_caption": "text",
    "table_caption": "text",
    "formula_caption": "text",
    "figure_footnote": "footnote",
    "table_footnote": "footnote",
    "page_footnote": "footnote",
}


@dataclass(frozen=True)
class InfinityRegion:
    source_ref: str
    page_no: int
    label: str
    region_kind: str
    text: str
    raw_bbox: RawBBox
    metadata: dict[str, Any]


def rebuild_infinity_document_regions(  # noqa: PLR0913
    connection: DuckConnection,
    file_hash: str,
    infinity_output_json: object,
    *,
    annotation_engine: str = INFINITY_ENGINE,
    annotation_provider: str = INFINITY_PROVIDER,
    annotation_model: str | None = None,
) -> int:
    """Persist Infinity Parser2 layout boxes for one file."""
    if not table_exists(connection, "document_regions"):
        return 0
    data = parse_json_value(infinity_output_json)
    _delete_infinity_regions(connection, file_hash, annotation_engine)
    regions = _infinity_regions(data)
    rows = [
        [
            _region_id(file_hash, annotation_engine, region),
            file_hash,
            annotation_engine,
            annotation_provider,
            annotation_model or str(data.get("model") or "infinity-parser2"),
            region.page_no,
            region.source_ref,
            region.label,
            region.text,
            region.text,
            json.dumps(region.raw_bbox.model_dump()),
            region.region_kind,
            json.dumps(region.metadata),
        ]
        for region in regions
    ]
    if rows:
        connection.executemany(
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
            rows,
        )
    rebuild_document_terms(connection, file_hash)
    return len(rows)


def _infinity_regions(data: dict[str, Any]) -> list[InfinityRegion]:
    pages = data.get("pages")
    if not isinstance(pages, list):
        return []
    regions: list[InfinityRegion] = []
    model = str(data.get("model") or "infinity-parser2")
    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, dict) or page.get("status") == "error":
            continue
        page_info = _page_info(page, page_index)
        if page_info is None:
            continue
        for item_index, item in enumerate(_layout_items(page.get("result"))):
            bbox = _bbox_from_item(item, page_info)
            if bbox is None:
                continue
            label = _label_for_item(item)
            text = _text_for_item(item) or label
            regions.append(
                InfinityRegion(
                    source_ref=f"infinity:page:{page_info.page_no}:region:{item_index}",
                    page_no=page_info.page_no,
                    label=label,
                    region_kind=_region_kind(label),
                    text=text,
                    raw_bbox=bbox,
                    metadata={
                        "source": "infinity_parser2_json",
                        "model": model,
                        "raw_item": item,
                        "page": page_metadata(page_info),
                        "render_sha256": page.get("render_sha256"),
                        "image_path": page.get("image_path"),
                        "elapsed_seconds": page.get("elapsed_seconds"),
                    },
                )
            )
    return regions


def _layout_items(value: object) -> list[dict[str, Any]]:  # noqa: PLR0911
    data = _json_data(value)
    if isinstance(data, dict):
        for key in ("elements", "layout", "regions", "items", "blocks"):
            child = data.get(key)
            if isinstance(child, list):
                return [item for item in child if isinstance(item, dict)]
        if bbox_value(data) is not None:
            return [data]
        nested: list[dict[str, Any]] = []
        for child in data.values():
            nested.extend(_layout_items(child))
        return nested
    if isinstance(data, list):
        items: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict) and bbox_value(item) is not None:
                items.append(item)
            else:
                items.extend(_layout_items(item))
        return items
    return []


def _json_data(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value


def _bbox_from_item(  # noqa: PLR0911
    item: dict[str, Any], page: PageInfo
) -> RawBBox | None:
    return bbox_from_infinity_item(item, page)


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


def _label_for_item(item: dict[str, Any]) -> str:
    return str(
        item.get("category")
        or item.get("type")
        or item.get("label")
        or item.get("region_kind")
        or "infinity_region"
    )


def _text_for_item(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("text", "content", "markdown", "html", "table_body"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value)
    return "\n\n".join(value.strip() for value in values)


def _region_kind(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in REGION_KIND_BY_CATEGORY:
        return REGION_KIND_BY_CATEGORY[normalized]
    for fragment, region_kind in REGION_KIND_BY_CATEGORY.items():
        if fragment in normalized:
            return region_kind
    return "other"


def _delete_infinity_regions(
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


def _region_id(
    file_hash: str, annotation_engine: str, region: InfinityRegion
) -> str:
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


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value)
    return result
