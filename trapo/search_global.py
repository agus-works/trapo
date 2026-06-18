from __future__ import annotations

from trapo.db import DuckConnection
from trapo.search_annotations import (
    search_document_regions_scan,
    search_page_markdown_scan,
)
from trapo.search_chunks import (
    search_document_chunks_fts,
    search_document_chunks_scan,
)
from trapo.search_files import search_files
from trapo.search_models import MAX_SEARCH_LIMIT, GlobalSearchResult
from trapo.search_text import clean_query


def search_global(
    connection: DuckConnection, query: str | None, *, limit: int = 30
) -> list[GlobalSearchResult]:
    normalized_query = clean_query(query)
    if not normalized_query:
        return []
    max_limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    results: list[GlobalSearchResult] = []
    seen: set[tuple[str, str]] = set()
    for collector in (
        search_document_chunks_fts,
        search_document_chunks_scan,
        search_document_regions_scan,
        search_page_markdown_scan,
        search_files,
    ):
        for result in collector(connection, normalized_query, max_limit):
            key = (result.source_type, result.source_id)
            if key in seen:
                continue
            seen.add(key)
            results.append(result)
            if len(results) >= max_limit * 3:
                break
        if len(results) >= max_limit * 3:
            break
    results.sort(key=lambda item: (-item.score, item.source_type, item.label))
    return results[:max_limit]
