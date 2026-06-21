from __future__ import annotations

import json

from trapo.db import DuckConnection, table_exists
from trapo.document_markdown_helpers import int_value
from trapo.document_markdown_models import (
    BEST_AVAILABLE_MARKDOWN_ENGINE,
    MARKDOWN_ENGINE_LABELS,
    MARKDOWN_ENGINE_PRIORITY,
    MarkdownEngineStatus,
    MarkdownGeneratorRecord,
)
from trapo.server.provenance import parse_json_value


def read_document_markdown_engines(
    connection: DuckConnection, file_hash: str
) -> list[MarkdownEngineStatus]:
    page_counts = _stored_markdown_page_counts(connection, file_hash)
    status_rows = _stored_markdown_engine_statuses(connection, file_hash)
    statuses = [_best_available_status(page_counts)]
    for engine in MARKDOWN_ENGINE_PRIORITY:
        row = status_rows.get(engine)
        statuses.append(
            MarkdownEngineStatus(
                markdown_engine=engine,
                label=MARKDOWN_ENGINE_LABELS.get(engine, engine),
                markdown_provider=row.markdown_provider if row else "",
                markdown_model=row.markdown_model if row else "",
                status=row.status if row else None,
                error=row.error if row else None,
                page_count=row.page_count if row else page_counts.get(engine, 0),
                metadata=row.metadata if row else {},
            )
        )
    return statuses


def record_markdown_generator(
    connection: DuckConnection, record: MarkdownGeneratorRecord
) -> None:
    if not table_exists(connection, "document_markdown_generators"):
        return
    connection.execute(
        """
        INSERT INTO document_markdown_generators (
            file_hash, markdown_engine, ingest_run_id, markdown_provider,
            markdown_model, status, error, page_count, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
        ON CONFLICT (file_hash, markdown_engine) DO UPDATE SET
            ingest_run_id = excluded.ingest_run_id,
            markdown_provider = excluded.markdown_provider,
            markdown_model = excluded.markdown_model,
            status = excluded.status,
            error = excluded.error,
            page_count = excluded.page_count,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            record.file_hash,
            record.markdown_engine,
            record.ingest_run_id,
            record.markdown_provider,
            record.markdown_model,
            record.status,
            record.error,
            record.page_count,
            json.dumps(record.metadata),
        ],
    )


def _best_available_status(
    page_counts: dict[str, int],
) -> MarkdownEngineStatus:
    return MarkdownEngineStatus(
        markdown_engine=BEST_AVAILABLE_MARKDOWN_ENGINE,
        label=MARKDOWN_ENGINE_LABELS[BEST_AVAILABLE_MARKDOWN_ENGINE],
        page_count=max(page_counts.values(), default=0),
        status="ok" if page_counts else None,
        is_virtual=True,
    )


def _stored_markdown_page_counts(
    connection: DuckConnection,
    file_hash: str,
) -> dict[str, int]:
    if not table_exists(connection, "document_page_markdown"):
        return {}
    active_engines = ", ".join(f"'{engine}'" for engine in MARKDOWN_ENGINE_PRIORITY)
    rows = connection.execute(
        f"""
        SELECT markdown_engine, count(*)
        FROM document_page_markdown
        WHERE file_hash = ?
          AND markdown_engine IN ({active_engines})
        GROUP BY markdown_engine
        """,
        [file_hash],
    ).fetchall()
    return {str(row[0]): int_value(row[1]) for row in rows}


def _stored_markdown_engine_statuses(
    connection: DuckConnection,
    file_hash: str,
) -> dict[str, MarkdownEngineStatus]:
    if not table_exists(connection, "document_markdown_generators"):
        return {}
    active_engines = ", ".join(f"'{engine}'" for engine in MARKDOWN_ENGINE_PRIORITY)
    rows = connection.execute(
        f"""
        SELECT
            markdown_engine, markdown_provider, markdown_model, status, error,
            page_count, metadata_json
        FROM document_markdown_generators
        WHERE file_hash = ?
          AND markdown_engine IN ({active_engines})
        """,
        [file_hash],
    ).fetchall()
    return {str(row[0]): _engine_status_from_row(row) for row in rows}


def _engine_status_from_row(row: tuple[object, ...]) -> MarkdownEngineStatus:
    engine = str(row[0])
    return MarkdownEngineStatus(
        markdown_engine=engine,
        label=MARKDOWN_ENGINE_LABELS.get(engine, engine),
        markdown_provider=str(row[1] or ""),
        markdown_model=str(row[2] or ""),
        status=str(row[3]) if row[3] is not None else None,
        error=str(row[4]) if row[4] is not None else None,
        page_count=int_value(row[5]),
        metadata=parse_json_value(row[6]),
    )
