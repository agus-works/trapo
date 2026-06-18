from __future__ import annotations

from trapo.db import DuckConnection, table_exists
from trapo.search_models import (
    DocumentRegionResultInput,
    GlobalSearchResult,
    PageMarkdownResultInput,
)
from trapo.search_text import (
    global_score,
    like_query,
    optional_int,
    overlay_id,
    snippet_match,
)


def search_document_regions_scan(
    connection: DuckConnection, query: str, limit: int
) -> list[GlobalSearchResult]:
    if not table_exists(connection, "document_regions"):
        return []
    rows = connection.execute(
        """
        SELECT
            r.region_id,
            r.file_hash,
            coalesce(f.filename, r.file_hash) AS filename,
            r.text,
            coalesce(r.context_text, '') AS context_text,
            coalesce(r.label, '') AS label,
            coalesce(r.annotation_engine, 'docling') AS annotation_engine,
            r.chunk_id,
            r.page_no
        FROM document_regions r
        LEFT JOIN files f ON f.file_hash = r.file_hash
        WHERE lower(
            coalesce(r.text, '') || ' ' ||
            coalesce(r.context_text, '') || ' ' ||
            coalesce(r.label, '') || ' ' ||
            coalesce(r.source_ref, '')
        ) LIKE ?
        ORDER BY r.updated_at DESC, r.created_at DESC, r.region_id
        LIMIT ?
        """,
        [like_query(query), limit],
    ).fetchall()
    return [
        _document_region_result(
            query,
            DocumentRegionResultInput(
                region_id=str(row[0]),
                file_hash=str(row[1]),
                filename=str(row[2]),
                text=str(row[3] or ""),
                context_text=str(row[4] or ""),
                label=str(row[5] or ""),
                annotation_engine=str(row[6] or "docling"),
                chunk_id=optional_int(row[7]),
                page_no=int(row[8]) if row[8] is not None else 1,
                score=global_score(
                    query,
                    str(row[2]),
                    " ".join(str(value or "") for value in row[3:6]),
                    base=78.0,
                ),
                rank_source="document_regions_scan",
            ),
        )
        for row in rows
    ]


def search_page_markdown_scan(
    connection: DuckConnection, query: str, limit: int
) -> list[GlobalSearchResult]:
    if not table_exists(connection, "document_page_markdown"):
        return []
    rows = connection.execute(
        """
        SELECT
            m.file_hash,
            coalesce(f.filename, m.file_hash) AS filename,
            m.page_no,
            m.markdown_engine,
            m.markdown_provider,
            m.markdown_model,
            m.markdown_text
        FROM document_page_markdown m
        LEFT JOIN files f ON f.file_hash = m.file_hash
        WHERE lower(m.markdown_text) LIKE ?
        ORDER BY m.updated_at DESC, m.file_hash, m.page_no
        LIMIT ?
        """,
        [like_query(query), limit],
    ).fetchall()
    return [
        _page_markdown_result(
            query,
            PageMarkdownResultInput(
                file_hash=str(row[0]),
                filename=str(row[1]),
                page_no=int(row[2]) if row[2] is not None else 1,
                markdown_engine=str(row[3]),
                markdown_provider=str(row[4]),
                markdown_model=str(row[5]),
                markdown_text=str(row[6] or ""),
                score=global_score(query, str(row[1]), str(row[6] or ""), base=74.0),
                rank_source="page_markdown_scan",
            ),
        )
        for row in rows
    ]


def _document_region_result(
    query: str,
    region: DocumentRegionResultInput,
) -> GlobalSearchResult:
    search_text = _region_search_text(region)
    match = snippet_match(search_text, query, field="snippet")
    route_search: dict[str, object] = {
        "file": region.file_hash,
        "page": region.page_no,
        "overlay": overlay_id(region.region_id),
        "overlays": "selected",
        "highlight": query,
    }
    return GlobalSearchResult(
        result_id=f"region:{region.region_id}",
        source_type="document_region",
        source_id=region.region_id,
        label=region.filename,
        snippet=match.snippet,
        route={"to": "/", "search": route_search},
        score=region.score,
        rank_source=region.rank_source,
        navigation_granularity="region",
        highlights=match.highlights,
        file_hash=region.file_hash,
        chunk_id=region.chunk_id,
        region_id=region.region_id,
        page_no=region.page_no,
        metadata={
            "annotation_engine": region.annotation_engine,
            "region_label": region.label or None,
        },
    )


def _page_markdown_result(
    query: str,
    page: PageMarkdownResultInput,
) -> GlobalSearchResult:
    match = snippet_match(page.markdown_text, query, field="snippet")
    route_search: dict[str, object] = {
        "file": page.file_hash,
        "page": page.page_no,
        "highlight": query,
        "view": "split",
    }
    return GlobalSearchResult(
        result_id=f"markdown:{page.file_hash}:{page.page_no}:{page.markdown_engine}",
        source_type="page_markdown",
        source_id=f"{page.file_hash}:{page.page_no}:{page.markdown_engine}",
        label=page.filename,
        snippet=match.snippet,
        route={"to": "/", "search": route_search},
        score=page.score,
        rank_source=page.rank_source,
        navigation_granularity="record",
        highlights=match.highlights,
        file_hash=page.file_hash,
        page_no=page.page_no,
        metadata={
            "markdown_engine": page.markdown_engine,
            "markdown_provider": page.markdown_provider,
            "markdown_model": page.markdown_model,
        },
    )


def _region_search_text(region: DocumentRegionResultInput) -> str:
    return "\n".join(
        part
        for part in (region.label, region.text, region.context_text)
        if part.strip()
    )
