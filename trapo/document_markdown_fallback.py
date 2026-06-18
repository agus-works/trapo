from __future__ import annotations

import re
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.document_markdown_models import PageMarkdown
from trapo.server.provenance import parse_json_value


def fallback_document_markdown(
    connection: DuckConnection,
    file_hash: str,
    markdown_engine: str,
) -> list[PageMarkdown]:
    pages_info = _preview_pages(connection, file_hash)
    ocr_rows = _ocr_rows(connection, file_hash)
    if not ocr_rows or not pages_info:
        return []

    engine, text, output_json, provider, model = _preferred_ocr_row(ocr_rows)
    pages_text = _comment_pages_text(text)
    if not pages_text and output_json:
        pages_text = _extract_json_pages_text(output_json)
    if not pages_text:
        pages_text = {pages_info[0][0]: text}

    return [
        PageMarkdown(
            file_hash=file_hash,
            page_no=page_no,
            markdown_engine=markdown_engine,
            markdown_provider=provider or "fallback",
            markdown_model=model or engine,
            markdown_text=pages_text.get(page_no, ""),
            page_width=page_width,
            page_height=page_height,
            metadata={"fallback": True, "source_engine": engine},
        )
        for page_no, page_width, page_height in pages_info
    ]


def _preview_pages(
    connection: DuckConnection, file_hash: str
) -> list[tuple[int, float, float]]:
    if not table_exists(connection, "document_preview_images"):
        return []
    rows = connection.execute(
        """
        SELECT DISTINCT page_no, page_width, page_height
        FROM document_preview_images
        WHERE file_hash = ?
        ORDER BY page_no
        """,
        [file_hash],
    ).fetchall()
    return [(int(row[0]), float(row[1]), float(row[2])) for row in rows]


def _ocr_rows(connection: DuckConnection, file_hash: str) -> list[tuple[object, ...]]:
    rows = []
    if table_exists(connection, "ocr_documents"):
        rows = connection.execute(
            """
            SELECT annotation_engine, text, output_json, reader_provider, reader_model
            FROM ocr_documents
            WHERE file_hash = ? AND status = 'ok'
            """,
            [file_hash],
        ).fetchall()

    if rows or not table_exists(connection, "docling_documents"):
        return rows
    docling_row = connection.execute(
        """
        SELECT 'docling', text, docling_json, reader_provider, reader_model
        FROM docling_documents
        WHERE file_hash = ? AND status = 'ok'
        """,
        [file_hash],
    ).fetchone()
    return [docling_row] if docling_row else []


def _preferred_ocr_row(
    rows: list[tuple[object, ...]],
) -> tuple[str, str, object, str, str]:
    preference = {
        "fusion": 0,
        "docling_normalized": 1,
        "mineru_normalized": 2,
        "docling": 3,
        "mineru": 4,
    }
    best_row = sorted(rows, key=lambda row: preference.get(str(row[0]), 10))[0]
    return (
        str(best_row[0]),
        str(best_row[1] or ""),
        best_row[2],
        str(best_row[3] or ""),
        str(best_row[4] or ""),
    )


def _comment_pages_text(text: str) -> dict[int, str]:
    parts = re.split(r"<!--\s*page\s+(\d+)\s*-->", text)
    pages_text: dict[int, str] = {}
    if len(parts) <= 1:
        return pages_text
    first_part = parts[0].strip()
    if first_part:
        pages_text[1] = first_part
    for index in range(1, len(parts), 2):
        pages_text[int(parts[index])] = parts[index + 1].strip()
    return pages_text


def _extract_json_pages_text(output_json: object) -> dict[int, str]:
    data = parse_json_value(output_json)
    pages_text: dict[int, str] = {}
    if isinstance(data, dict):
        if "texts" in data:
            pages_text = _docling_pages_text(data)
        elif "content_list" in data:
            pages_text = _mineru_pages_text(data)
    return pages_text


def _docling_pages_text(data: dict[str, Any]) -> dict[int, str]:
    pages_lines: dict[int, list[str]] = {}
    texts = data.get("texts", [])
    if not isinstance(texts, list):
        return {}
    for item in texts:
        if not isinstance(item, dict):
            continue
        content = item.get("text") or item.get("orig")
        prov = item.get("prov", [])
        if content and prov and isinstance(prov, list):
            page_no = prov[0].get("page_no")
            if isinstance(page_no, int):
                pages_lines.setdefault(page_no, []).append(str(content))
    return {page_no: "\n\n".join(lines) for page_no, lines in pages_lines.items()}


def _mineru_pages_text(data: dict[str, Any]) -> dict[int, str]:
    pages_lines: dict[int, list[str]] = {}
    content_list = data.get("content_list", [])
    if not isinstance(content_list, list):
        return {}
    for item in content_list:
        if not isinstance(item, dict):
            continue
        content = item.get("text") or item.get("content")
        page_idx = item.get("page_idx")
        if content and isinstance(page_idx, int):
            pages_lines.setdefault(page_idx + 1, []).append(str(content))
    return {page_no: "\n\n".join(lines) for page_no, lines in pages_lines.items()}
