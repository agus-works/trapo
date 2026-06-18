from __future__ import annotations

from trapo.db import DuckConnection, table_exists
from trapo.search_models import (
    DocumentChunkResultInput,
    GlobalSearchResult,
    NavigationGranularity,
    SearchHighlight,
)
from trapo.search_text import (
    json_dict,
    global_score,
    like_query,
    optional_int,
    overlay_id,
    query_tokens,
    snippet_match,
)


def search_document_chunks_fts(
    connection: DuckConnection, query: str, limit: int
) -> list[GlobalSearchResult]:
    if not table_exists(connection, "document_chunks"):
        return []
    try:
        connection.execute("INSTALL fts")
        connection.execute("LOAD fts")
        connection.execute(
            "PRAGMA create_fts_index('document_chunks', 'chunk_id', 'text', overwrite=0)"
        )
        rows = connection.execute(
            """
            SELECT c.chunk_id, c.file_hash, c.text,
                   f.filename,
                   r.region_id,
                   r.page_no,
                   fts_main_document_chunks.match_bm25(c.chunk_id, ?) AS score
            FROM document_chunks c
            LEFT JOIN files f ON f.file_hash = c.file_hash
            LEFT JOIN document_regions r ON r.chunk_id = c.chunk_id
            WHERE score IS NOT NULL
            ORDER BY score DESC
            LIMIT ?
            """,
            [query, limit],
        ).fetchall()
    except Exception:
        return []
    return [
        _document_chunk_result(
            connection,
            query,
            DocumentChunkResultInput(
                chunk_id=int(row[0]),
                file_hash=str(row[1]),
                text=str(row[2]),
                filename=str(row[3]) if row[3] is not None else str(row[1]),
                region_id=str(row[4]) if row[4] is not None else None,
                page_no=int(row[5]) if row[5] is not None else None,
                score=100.0 + float(row[6] or 0.0),
                rank_source="duckdb_fts",
            ),
        )
        for row in rows
    ]


def search_document_chunks_scan(
    connection: DuckConnection, query: str, limit: int
) -> list[GlobalSearchResult]:
    if not table_exists(connection, "document_chunks"):
        return []
    rows = connection.execute(
        """
        SELECT c.chunk_id, c.file_hash, c.text, f.filename, r.region_id, r.page_no
        FROM document_chunks c
        LEFT JOIN files f ON f.file_hash = c.file_hash
        LEFT JOIN document_regions r ON r.chunk_id = c.chunk_id
        WHERE lower(c.text) LIKE ?
        ORDER BY c.created_at DESC, c.chunk_id DESC
        LIMIT ?
        """,
        [like_query(query), limit],
    ).fetchall()
    return [
        _document_chunk_result(
            connection,
            query,
            DocumentChunkResultInput(
                chunk_id=int(row[0]),
                file_hash=str(row[1]),
                text=str(row[2]),
                filename=str(row[3]) if row[3] is not None else str(row[1]),
                region_id=str(row[4]) if row[4] is not None else None,
                page_no=int(row[5]) if row[5] is not None else None,
                score=global_score(
                    query,
                    str(row[3]) if row[3] is not None else str(row[1]),
                    str(row[2]),
                    base=62.0,
                ),
                rank_source="document_chunks_scan",
            ),
        )
        for row in rows
    ]


def _document_chunk_result(
    connection: DuckConnection,
    query: str,
    chunk: DocumentChunkResultInput,
) -> GlobalSearchResult:
    term = _matching_document_term(connection, query, chunk_id=chunk.chunk_id)
    selected_region = (
        term["region_id"] if term and term.get("region_id") else chunk.region_id
    )
    selected_page = optional_int(term.get("page_no")) if term else chunk.page_no
    route_search: dict[str, object] = {"file": chunk.file_hash}
    if selected_page is not None:
        route_search["page"] = selected_page
    if selected_region:
        route_search["overlay"] = overlay_id(str(selected_region))
        route_search["overlays"] = "selected"
    if term and term.get("document_term_id"):
        route_search["term"] = str(term["document_term_id"])
    route_search["highlight"] = query
    navigation_granularity: NavigationGranularity = (
        "word" if term else "region" if selected_region else "chunk"
    )
    match = snippet_match(chunk.text, query, field="snippet")
    highlights = match.highlights
    if chunk.rank_source == "duckdb_fts" and highlights:
        highlights = tuple(
            SearchHighlight(
                field=item.field,
                start=item.start,
                end=item.end,
                match_kind=item.match_kind,
                source="fts_term"
                if item.source in {"exact_phrase", "exact_token"}
                else item.source,
                score_contribution=item.score_contribution,
            )
            for item in highlights
        )
    return GlobalSearchResult(
        result_id=f"chunk:{chunk.chunk_id}",
        source_type="document_chunk",
        source_id=str(chunk.chunk_id),
        label=chunk.filename,
        snippet=match.snippet,
        route={"to": "/", "search": route_search},
        score=chunk.score,
        rank_source=chunk.rank_source,
        navigation_granularity=navigation_granularity,
        highlights=highlights,
        file_hash=chunk.file_hash,
        chunk_id=chunk.chunk_id,
        region_id=str(selected_region) if selected_region else None,
        page_no=selected_page,
        word_id=str(term["document_term_id"])
        if term and term.get("document_term_id")
        else None,
        char_start=optional_int(term.get("char_start")) if term else None,
        char_end=optional_int(term.get("char_end")) if term else None,
        metadata={"word_bbox": term.get("bbox") if term else None},
    )


def _matching_document_term(
    connection: DuckConnection, query: str, *, chunk_id: int
) -> dict[str, object] | None:
    match: dict[str, object] | None = None
    tokens = query_tokens(query)
    if table_exists(connection, "document_terms") and tokens:
        placeholders = ", ".join(["?"] * len(tokens))
        rows = connection.execute(
            f"""
            SELECT document_term_id, file_hash, page_no, region_id, chunk_id,
                   char_start, char_end, bbox_json
            FROM document_terms
            WHERE chunk_id = ? AND normalized_text IN ({placeholders})
            ORDER BY char_start, document_term_id
            LIMIT 1
            """,
            [chunk_id, *tokens],
        ).fetchall()
        if rows:
            row = rows[0]
            match = {
                "document_term_id": str(row[0]),
                "file_hash": str(row[1]),
                "page_no": int(row[2]) if row[2] is not None else None,
                "region_id": str(row[3]) if row[3] is not None else None,
                "chunk_id": int(row[4]) if row[4] is not None else None,
                "char_start": int(row[5]) if row[5] is not None else None,
                "char_end": int(row[6]) if row[6] is not None else None,
                "bbox": json_dict(row[7]),
            }
    return match
