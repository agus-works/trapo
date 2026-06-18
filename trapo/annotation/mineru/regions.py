from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.annotation.docling.regions import rebuild_document_terms
from trapo.mineru_bbox import (
    bbox_from_mineru_content_bbox,
    bbox_from_mineru_middle_bbox,
    page_metadata,
)
from trapo.server.models import PageInfo, RawBBox
from trapo.server.provenance import parse_json_value


MINERU_ENGINE = "mineru"
MINERU_PROVIDER = "local-mineru"
MIN_PAGE_SIZE_VALUES = 2
REGION_KIND_FRAGMENTS = (
    ("table", "table"),
    ("equation", "formula"),
    ("math", "formula"),
    ("formula", "formula"),
    ("image", "image"),
    ("chart", "chart"),
    ("code", "code"),
    ("algorithm", "code"),
    ("list", "list"),
    ("index", "list"),
    ("title", "title"),
    ("header", "header"),
    ("footer", "footer"),
    ("footnote", "footnote"),
    ("page_number", "page_number"),
)


@dataclass(frozen=True)
class MinerURegion:
    source_ref: str
    page_no: int
    label: str
    region_kind: str
    text: str
    raw_bbox: RawBBox
    metadata: dict[str, Any]


def rebuild_mineru_document_regions(  # noqa: PLR0913
    connection: DuckConnection,
    file_hash: str,
    mineru_output_json: object,
    target_pages: Iterable[PageInfo] | None = None,
    annotation_engine: str = MINERU_ENGINE,
    annotation_provider: str = MINERU_PROVIDER,
    annotation_model: str | None = None,
) -> int:
    """Persist MinerU annotation boxes for one file."""
    if not table_exists(connection, "document_regions"):
        return 0
    _delete_mineru_regions(connection, file_hash, annotation_engine)
    source_pages_by_no = _page_map(extract_mineru_pages(mineru_output_json))
    target_pages_by_no = (
        _page_map(target_pages) if target_pages is not None else source_pages_by_no
    )
    regions = _mineru_regions(
        mineru_output_json, source_pages_by_no, target_pages_by_no
    )
    rows: list[list[object]] = []
    for region in regions:
        region_id = _region_id(file_hash, annotation_engine, region)
        rows.append(
            [
                region_id,
                file_hash,
                annotation_engine,
                annotation_provider,
                annotation_model or str(region.metadata.get("model") or "mineru"),
                region.page_no,
                region.source_ref,
                region.label,
                region.text,
                region.text,
                json.dumps(region.raw_bbox.model_dump()),
                region.region_kind,
                json.dumps(region.metadata),
            ]
        )

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


def extract_mineru_pages(mineru_output_json: object) -> list[PageInfo]:
    data = parse_json_value(mineru_output_json)
    middle_json = parse_json_value(data.get("middle_json"))
    pdf_info = middle_json.get("pdf_info")
    if not isinstance(pdf_info, list):
        return []
    pages: list[PageInfo] = []
    for fallback_index, page in enumerate(pdf_info, start=1):
        if not isinstance(page, dict):
            continue
        page_size = page.get("page_size")
        if not isinstance(page_size, list) or len(page_size) < MIN_PAGE_SIZE_VALUES:
            continue
        width = _float_or_none(page_size[0])
        height = _float_or_none(page_size[1])
        if width is None or height is None:
            continue
        page_idx = _int_or_none(page.get("page_idx"))
        pages.append(
            PageInfo(
                page_no=(page_idx + 1) if page_idx is not None else fallback_index,
                width=width,
                height=height,
            )
        )
    return sorted(pages, key=lambda item: item.page_no)


def _mineru_regions(
    mineru_output_json: object,
    source_pages_by_no: dict[int, PageInfo],
    target_pages_by_no: dict[int, PageInfo],
) -> list[MinerURegion]:
    data = parse_json_value(mineru_output_json)
    regions = _regions_from_content_list(data, source_pages_by_no, target_pages_by_no)
    if regions:
        return regions
    return _regions_from_middle_json(data, source_pages_by_no, target_pages_by_no)


def _regions_from_content_list(
    data: dict[str, Any],
    source_pages_by_no: dict[int, PageInfo],
    target_pages_by_no: dict[int, PageInfo],
) -> list[MinerURegion]:
    content_list = data.get("content_list")
    if not isinstance(content_list, list):
        content_list = data.get("content_list_v2")
    regions: list[MinerURegion] = []
    for index, item in enumerate(_flatten_content_items(content_list)):
        if not isinstance(item, dict):
            continue
        page_no = (_int_or_none(item.get("page_idx")) or 0) + 1
        source_page = source_pages_by_no.get(page_no)
        target_page = target_pages_by_no.get(page_no)
        bbox = bbox_from_mineru_content_bbox(item.get("bbox"), target_page)
        if target_page is None or bbox is None:
            continue
        label = _label_for_item(item)
        text = _text_for_item(item)
        if not text:
            text = label
        regions.append(
            MinerURegion(
                source_ref=f"mineru:content:{index}",
                page_no=page_no,
                label=label,
                region_kind=_region_kind(label),
                text=text,
                raw_bbox=bbox,
                metadata={
                    "source": "content_list",
                    "raw_item": item,
                    "source_page": page_metadata(source_page),
                    "target_page": page_metadata(target_page),
                    "model": data.get("backend"),
                },
            )
        )
    return regions


def _regions_from_middle_json(
    data: dict[str, Any],
    source_pages_by_no: dict[int, PageInfo],
    target_pages_by_no: dict[int, PageInfo],
) -> list[MinerURegion]:
    middle_json = parse_json_value(data.get("middle_json"))
    pdf_info = middle_json.get("pdf_info")
    if not isinstance(pdf_info, list):
        return []
    regions: list[MinerURegion] = []
    for page_index, page_data in enumerate(pdf_info, start=1):
        if not isinstance(page_data, dict):
            continue
        page_no = (_int_or_none(page_data.get("page_idx")) or page_index - 1) + 1
        source_page = source_pages_by_no.get(page_no)
        target_page = target_pages_by_no.get(page_no)
        if source_page is None or target_page is None:
            continue
        for item_index, item in enumerate(_walk_bbox_items(page_data)):
            bbox = bbox_from_mineru_middle_bbox(
                item.get("bbox"), source_page, target_page
            )
            if bbox is None:
                continue
            label = _label_for_item(item)
            text = _text_for_item(item) or label
            regions.append(
                MinerURegion(
                    source_ref=f"mineru:middle:{page_no}:{item_index}",
                    page_no=page_no,
                    label=label,
                    region_kind=_region_kind(label),
                    text=text,
                    raw_bbox=bbox,
                    metadata={
                        "source": "middle_json",
                        "raw_item": item,
                        "source_page": page_metadata(source_page),
                        "target_page": page_metadata(target_page),
                        "model": data.get("backend"),
                    },
                )
            )
    return regions


def _delete_mineru_regions(
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


def _flatten_content_items(value: object) -> Iterable[object]:
    if not isinstance(value, list):
        return []
    if all(isinstance(item, list) for item in value):
        return (child for page in value for child in page if isinstance(page, list))
    return value


def _walk_bbox_items(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("bbox"), list):
            yield value
        for child in value.values():
            yield from _walk_bbox_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_bbox_items(child)


def _label_for_item(item: dict[str, Any]) -> str:
    label = str(item.get("type") or item.get("sub_type") or "mineru_region")
    sub_type = item.get("sub_type")
    if sub_type and str(sub_type) not in label:
        label = f"{label}:{sub_type}"
    return label


def _text_for_item(item: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "text",
        "content",
        "table_body",
        "code_body",
        "algorithm_content",
        "paragraph_content",
        "title_content",
        "math_content",
        "image_caption",
        "image_footnote",
        "table_caption",
        "table_footnote",
        "chart_caption",
        "chart_footnote",
        "list_items",
    ):
        values.extend(_text_values(item.get(key)))
    return " ".join(
        " ".join(value.split()) for value in values if value.strip()
    ).strip()


def _text_values(value: object) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            values.extend(_text_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_text_values(child))
    return values


def _region_kind(label: str) -> str:
    normalized = label.casefold()
    return next(
        (
            region_kind
            for fragment, region_kind in REGION_KIND_FRAGMENTS
            if fragment in normalized
        ),
        "text",
    )


def _region_id(file_hash: str, annotation_engine: str, region: MinerURegion) -> str:
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


def _page_map(pages: Iterable[PageInfo] | None) -> dict[int, PageInfo]:
    if pages is None:
        return {}
    return {page.page_no: page for page in pages}


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
