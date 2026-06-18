from __future__ import annotations

from trapo.db import DuckConnection, table_exists
from trapo.search_models import GlobalSearchResult
from trapo.search_text import global_score, highlight_text, like_query


def search_files(
    connection: DuckConnection, query: str, limit: int
) -> list[GlobalSearchResult]:
    if not table_exists(connection, "files"):
        return []
    rows = connection.execute(
        """
        SELECT f.file_hash, f.filename, f.extension, l.path
        FROM files f
        LEFT JOIN file_locations l ON l.file_hash = f.file_hash
        WHERE lower(f.filename || ' ' || f.file_hash || ' ' || coalesce(l.path, '')) LIKE ?
        ORDER BY f.last_seen_at DESC, f.filename
        LIMIT ?
        """,
        [like_query(query), limit],
    ).fetchall()
    results: list[GlobalSearchResult] = []
    for row in rows:
        file_hash = str(row[0])
        filename = str(row[1])
        path = str(row[3]) if row[3] is not None else ""
        text = f"{filename} {path} {file_hash}"
        results.append(
            GlobalSearchResult(
                result_id=f"file:{file_hash}",
                source_type="file",
                source_id=file_hash,
                label=filename,
                snippet=path or file_hash,
                route={"to": "/", "search": {"file": file_hash}},
                score=global_score(query, filename, text, base=82.0),
                rank_source="files_scan",
                navigation_granularity="file",
                highlights=tuple(
                    highlight_text(query, filename, field="label")
                    or highlight_text(query, path, field="snippet")
                ),
                file_hash=file_hash,
                metadata={
                    "extension": str(row[2]) if row[2] is not None else None,
                    "path": path,
                },
            )
        )
    return results
