from __future__ import annotations

import json

from trapo.db import DuckConnection, table_exists
from trapo.document_markdown_helpers import float_or_none, int_value
from trapo.document_markdown_models import (
    MARKDOWN_ENGINE_PRIORITY,
    MarkdownRegionMapping,
    PageMarkdown,
)
from trapo.server.provenance import parse_json_value


def replace_markdown_mappings(connection: DuckConnection, page: PageMarkdown) -> None:
    if not table_exists(connection, "document_page_markdown_regions"):
        return
    connection.execute(
        """
        DELETE FROM document_page_markdown_regions
        WHERE file_hash = ? AND page_no = ? AND markdown_engine = ?
        """,
        [page.file_hash, page.page_no, page.markdown_engine],
    )
    for mapping in page.mappings:
        connection.execute(
            """
            INSERT INTO document_page_markdown_regions (
                file_hash, page_no, markdown_engine, anchor_id, region_id,
                char_start, char_end, confidence, markdown_excerpt, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
            """,
            [
                page.file_hash,
                page.page_no,
                page.markdown_engine,
                mapping.anchor_id,
                mapping.region_id,
                mapping.char_start,
                mapping.char_end,
                mapping.confidence,
                mapping.markdown_excerpt,
                json.dumps(mapping.metadata),
            ],
        )


def read_markdown_mappings_by_engine_and_page(
    connection: DuckConnection,
    file_hash: str,
    *,
    page_no: int | None = None,
) -> dict[tuple[str, int], list[MarkdownRegionMapping]]:
    if not table_exists(connection, "document_page_markdown_regions"):
        return {}
    engine_placeholders = ", ".join("?" for _engine in MARKDOWN_ENGINE_PRIORITY)
    filters = ["file_hash = ?", f"markdown_engine IN ({engine_placeholders})"]
    parameters: list[object] = [file_hash, *MARKDOWN_ENGINE_PRIORITY]
    if page_no is not None:
        filters.append("page_no = ?")
        parameters.append(page_no)
    rows = connection.execute(
        f"""
        SELECT
            markdown_engine, page_no, anchor_id, region_id, char_start, char_end,
            confidence, markdown_excerpt, metadata_json
        FROM document_page_markdown_regions
        WHERE {" AND ".join(filters)}
        ORDER BY page_no, markdown_engine, char_start, anchor_id, region_id
        """,
        parameters,
    ).fetchall()
    by_key: dict[tuple[str, int], list[MarkdownRegionMapping]] = {}
    for row in rows:
        key = (str(row[0]), int_value(row[1]))
        by_key.setdefault(key, []).append(_mapping_from_row(row[2:]))
    return by_key


def read_markdown_mappings_by_page(
    connection: DuckConnection,
    file_hash: str,
    markdown_engine: str,
    *,
    page_no: int | None = None,
) -> dict[int, list[MarkdownRegionMapping]]:
    if not table_exists(connection, "document_page_markdown_regions"):
        return {}
    filters = ["file_hash = ?", "markdown_engine = ?"]
    parameters: list[object] = [file_hash, markdown_engine]
    if page_no is not None:
        filters.append("page_no = ?")
        parameters.append(page_no)
    rows = connection.execute(
        f"""
        SELECT
            page_no, anchor_id, region_id, char_start, char_end,
            confidence, markdown_excerpt, metadata_json
        FROM document_page_markdown_regions
        WHERE {" AND ".join(filters)}
        ORDER BY page_no, char_start, anchor_id, region_id
        """,
        parameters,
    ).fetchall()
    by_page: dict[int, list[MarkdownRegionMapping]] = {}
    for row in rows:
        page_number = int_value(row[0])
        by_page.setdefault(page_number, []).append(_mapping_from_row(row[1:]))
    return by_page


def _mapping_from_row(row: tuple[object, ...]) -> MarkdownRegionMapping:
    return MarkdownRegionMapping(
        anchor_id=str(row[0]),
        region_id=str(row[1]),
        char_start=int_value(row[2]),
        char_end=int_value(row[3]),
        confidence=float_or_none(row[4]),
        markdown_excerpt=str(row[5] or ""),
        metadata=parse_json_value(row[6]),
    )
