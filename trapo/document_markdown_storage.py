from __future__ import annotations

import json

from trapo.db import DuckConnection, table_exists
from trapo.document_markdown_fallback import fallback_document_markdown
from trapo.document_markdown_helpers import (
    float_or_none,
    int_value,
    is_usable_markdown_text,
)
from trapo.document_markdown_mappings import (
    read_markdown_mappings_by_engine_and_page,
    read_markdown_mappings_by_page,
    replace_markdown_mappings,
)
from trapo.document_markdown_models import (
    BEST_AVAILABLE_MARKDOWN_ENGINE,
    DEFAULT_MARKDOWN_ENGINE,
    MARKDOWN_ENGINE_PRIORITY,
    MarkdownRegionMapping,
    PageMarkdown,
)
from trapo.server.provenance import parse_json_value


def upsert_page_markdown(connection: DuckConnection, page: PageMarkdown) -> None:
    if not table_exists(connection, "document_page_markdown"):
        return
    connection.execute(
        """
        INSERT INTO document_page_markdown (
            file_hash, page_no, markdown_engine, markdown_provider, markdown_model,
            markdown_text, page_width, page_height, render_sha256, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
        ON CONFLICT (file_hash, page_no, markdown_engine) DO UPDATE SET
            markdown_provider = excluded.markdown_provider,
            markdown_model = excluded.markdown_model,
            markdown_text = excluded.markdown_text,
            page_width = excluded.page_width,
            page_height = excluded.page_height,
            render_sha256 = excluded.render_sha256,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            page.file_hash,
            page.page_no,
            page.markdown_engine,
            page.markdown_provider,
            page.markdown_model,
            page.markdown_text,
            page.page_width,
            page.page_height,
            page.render_sha256,
            json.dumps(page.metadata),
        ],
    )
    replace_markdown_mappings(connection, page)


def read_document_markdown(
    connection: DuckConnection,
    file_hash: str,
    *,
    markdown_engine: str = DEFAULT_MARKDOWN_ENGINE,
    page_no: int | None = None,
) -> list[PageMarkdown]:
    pages: list[PageMarkdown] = []
    if table_exists(connection, "document_page_markdown"):
        if markdown_engine == BEST_AVAILABLE_MARKDOWN_ENGINE:
            pages = _best_available_markdown(connection, file_hash, page_no=page_no)
        elif markdown_engine not in MARKDOWN_ENGINE_PRIORITY:
            pages = []
        else:
            pages = _provider_markdown(
                connection, file_hash, markdown_engine=markdown_engine, page_no=page_no
            )
            if not pages:
                pages = _fallback_markdown(
                    connection, file_hash, markdown_engine, page_no=page_no
                )
    return pages


def markdown_complete(
    connection: DuckConnection,
    file_hash: str,
    *,
    markdown_engine: str = DEFAULT_MARKDOWN_ENGINE,
    page_numbers: list[int] | None = None,
) -> bool:
    if not table_exists(connection, "document_page_markdown"):
        return False
    rows = connection.execute(
        """
        SELECT page_no, markdown_text
        FROM document_page_markdown
        WHERE file_hash = ? AND markdown_engine = ?
        """,
        [file_hash, markdown_engine],
    ).fetchall()
    usable_pages = {
        int_value(row[0]) for row in rows if is_usable_markdown_text(str(row[1] or ""))
    }
    if page_numbers is None:
        return bool(usable_pages)
    expected_pages = {page_no for page_no in page_numbers if page_no > 0}
    return bool(expected_pages) and expected_pages.issubset(usable_pages)


def _provider_markdown(
    connection: DuckConnection,
    file_hash: str,
    *,
    markdown_engine: str,
    page_no: int | None,
) -> list[PageMarkdown]:
    filters = ["file_hash = ?", "markdown_engine = ?"]
    parameters: list[object] = [file_hash, markdown_engine]
    if page_no is not None:
        filters.append("page_no = ?")
        parameters.append(page_no)
    rows = connection.execute(
        f"""
        SELECT
            file_hash, page_no, markdown_engine, markdown_provider, markdown_model,
            markdown_text, page_width, page_height, render_sha256, metadata_json
        FROM document_page_markdown
        WHERE {" AND ".join(filters)}
        ORDER BY page_no
        """,
        parameters,
    ).fetchall()
    mappings_by_page = read_markdown_mappings_by_page(
        connection, file_hash, markdown_engine, page_no=page_no
    )
    return [
        _page_from_row(row, mappings=mappings_by_page.get(int_value(row[1]), []))
        for row in rows
    ]


def _best_available_markdown(
    connection: DuckConnection,
    file_hash: str,
    *,
    page_no: int | None = None,
) -> list[PageMarkdown]:
    rows = _stored_markdown_pages(connection, file_hash, page_no=page_no)
    by_page: dict[int, dict[str, PageMarkdown]] = {}
    for page in rows:
        by_page.setdefault(page.page_no, {})[page.markdown_engine] = page

    selected: list[PageMarkdown] = []
    for page_number in sorted(by_page):
        page = _best_page(by_page[page_number])
        if page is not None:
            selected.append(page)
    if selected:
        return selected
    return _fallback_markdown(
        connection, file_hash, BEST_AVAILABLE_MARKDOWN_ENGINE, page_no=page_no
    )


def _best_page(pages_by_engine: dict[str, PageMarkdown]) -> PageMarkdown | None:
    for engine in MARKDOWN_ENGINE_PRIORITY:
        page = pages_by_engine.get(engine)
        if page is not None and is_usable_markdown_text(page.markdown_text):
            return PageMarkdown(
                file_hash=page.file_hash,
                page_no=page.page_no,
                markdown_engine=BEST_AVAILABLE_MARKDOWN_ENGINE,
                markdown_provider=page.markdown_provider,
                markdown_model=page.markdown_model,
                markdown_text=page.markdown_text,
                page_width=page.page_width,
                page_height=page.page_height,
                render_sha256=page.render_sha256,
                metadata={
                    **page.metadata,
                    "source_markdown_engine": page.markdown_engine,
                    "virtual_engine": BEST_AVAILABLE_MARKDOWN_ENGINE,
                },
                mappings=page.mappings,
            )
    return None


def _stored_markdown_pages(
    connection: DuckConnection,
    file_hash: str,
    *,
    page_no: int | None = None,
) -> list[PageMarkdown]:
    engine_placeholders = ", ".join("?" for _engine in MARKDOWN_ENGINE_PRIORITY)
    filters = ["file_hash = ?", f"markdown_engine IN ({engine_placeholders})"]
    parameters: list[object] = [file_hash, *MARKDOWN_ENGINE_PRIORITY]
    if page_no is not None:
        filters.append("page_no = ?")
        parameters.append(page_no)
    rows = connection.execute(
        f"""
        SELECT
            file_hash, page_no, markdown_engine, markdown_provider, markdown_model,
            markdown_text, page_width, page_height, render_sha256, metadata_json
        FROM document_page_markdown
        WHERE {" AND ".join(filters)}
        ORDER BY page_no, markdown_engine
        """,
        parameters,
    ).fetchall()
    mappings_by_key = read_markdown_mappings_by_engine_and_page(
        connection, file_hash, page_no=page_no
    )
    return [
        _page_from_row(
            row,
            mappings=mappings_by_key.get((str(row[2]), int_value(row[1])), []),
        )
        for row in rows
    ]


def _page_from_row(
    row: tuple[object, ...], *, mappings: list[MarkdownRegionMapping] | None = None
) -> PageMarkdown:
    return PageMarkdown(
        file_hash=str(row[0]),
        page_no=int_value(row[1]),
        markdown_engine=str(row[2]),
        markdown_provider=str(row[3]),
        markdown_model=str(row[4]),
        markdown_text=str(row[5] or ""),
        page_width=float_or_none(row[6]),
        page_height=float_or_none(row[7]),
        render_sha256=str(row[8]) if row[8] is not None else None,
        metadata=parse_json_value(row[9]),
        mappings=mappings or [],
    )


def _fallback_markdown(
    connection: DuckConnection,
    file_hash: str,
    markdown_engine: str,
    *,
    page_no: int | None,
) -> list[PageMarkdown]:
    fallback = fallback_document_markdown(connection, file_hash, markdown_engine)
    if page_no is None:
        return fallback
    return [page for page in fallback if page.page_no == page_no]
