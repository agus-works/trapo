from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.server.models import PageInfo, RawBBox
from trapo.server.provenance import _normalize_bbox, parse_json_value


MAX_TEXT_LENGTH = 180
DEFAULT_MAX_ITEMS_PER_PAGE = 80


def lmstudio_evidence_by_page(
    connection: DuckConnection,
    file_hash: str,
    pages: Iterable[PageInfo] | None,
    *,
    max_items_per_page: int = DEFAULT_MAX_ITEMS_PER_PAGE,
) -> dict[int, list[dict[str, Any]]]:
    """Return compact Docling/MinerU region hints for LM Studio page prompts."""
    if not table_exists(connection, "document_regions"):
        return {}
    pages_by_no = {page.page_no: page for page in pages or []}
    rows = connection.execute(
        """
        SELECT
            region_id, annotation_engine, page_no, label, region_kind, text,
            raw_bbox_json
        FROM document_regions
        WHERE file_hash = ?
          AND annotation_engine IN ('docling', 'mineru')
        ORDER BY page_no, annotation_engine, source_ref, region_id
        """,
        [file_hash],
    ).fetchall()
    evidence: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        page_no = _int_value(row[2])
        page = pages_by_no.get(page_no)
        if page is None:
            continue
        bbox = _raw_bbox(row[6])
        if bbox is None:
            continue
        page_items = evidence.setdefault(page_no, [])
        if len(page_items) >= max_items_per_page:
            continue
        normalized = _normalize_bbox(bbox, page)
        page_items.append(
            {
                "region_id": str(row[0]),
                "engine": str(row[1]),
                "label": str(row[3] or ""),
                "region_kind": str(row[4] or "text"),
                "text": _short_text(str(row[5] or "")),
                "box_2d": [
                    round(normalized.top_pct * 10),
                    round(normalized.left_pct * 10),
                    round((normalized.top_pct + normalized.height_pct) * 10),
                    round((normalized.left_pct + normalized.width_pct) * 10),
                ],
            }
        )
    return evidence


def _raw_bbox(value: object) -> RawBBox | None:
    data = parse_json_value(value)
    if not data:
        return None
    try:
        return RawBBox.model_validate(data)
    except Exception:
        return None


def _short_text(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= MAX_TEXT_LENGTH:
        return normalized
    return f"{normalized[: MAX_TEXT_LENGTH - 1]}..."


def _int_value(value: object) -> int:
    result = 0
    if isinstance(value, bool | int | float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            result = 0
    return result
