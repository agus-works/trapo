from __future__ import annotations

from trapo.db import DuckConnection, table_exists
from trapo.server.diagnostic_models import (
    DiagnosticEventRecord,
    DiagnosticRunRecord,
    DiagnosticTracePayload,
    DiagnosticTraceSummary,
)
from trapo.server.diagnostic_records import (
    event_record,
    run_record,
    span_record,
    trace_summary,
)


MAX_TRACE_LIMIT = 10000


def diagnostic_runs(
    con: DuckConnection, *, limit: int = 50
) -> list[DiagnosticRunRecord]:
    if not table_exists(con, "ingest_runs"):
        return []
    safe_limit = max(1, min(limit, 200))
    rows = con.execute(
        """
        SELECT
            r.ingest_run_id,
            r.source_directory,
            r.status,
            r.started_at,
            r.finished_at,
            count(s.span_id) AS span_count,
            count(CASE WHEN s.status = 'error' THEN 1 END) AS error_count,
            count(DISTINCT s.file_hash)
                FILTER (WHERE s.file_hash IS NOT NULL) AS file_count,
            count(DISTINCT s.file_hash || ':' || CAST(s.page_no AS TEXT))
                FILTER (WHERE s.file_hash IS NOT NULL AND s.page_no IS NOT NULL) AS page_count,
            min(s.started_at) AS trace_started_at,
            max(s.ended_at) AS trace_ended_at
        FROM ingest_runs r
        LEFT JOIN ingest_diagnostic_spans s ON s.ingest_run_id = r.ingest_run_id
        GROUP BY r.ingest_run_id, r.source_directory, r.status, r.started_at, r.finished_at
        ORDER BY r.started_at DESC, r.ingest_run_id DESC
        LIMIT ?
        """,
        [safe_limit],
    ).fetchall()
    return [run_record(row) for row in rows]


def diagnostic_trace(  # noqa: PLR0913
    con: DuckConnection,
    *,
    ingest_run_id: int | None = None,
    file_hash: str | None = None,
    page_no: int | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 5000,
) -> DiagnosticTracePayload:
    if not table_exists(con, "ingest_diagnostic_spans"):
        return DiagnosticTracePayload(summary=DiagnosticTraceSummary())
    safe_limit = max(1, min(limit, MAX_TRACE_LIMIT))
    where_sql, parameters = _where_clause(
        ingest_run_id=ingest_run_id,
        file_hash=file_hash,
        page_no=page_no,
        status=status,
        q=q,
    )
    rows = con.execute(
        f"""
        SELECT
            span_id, trace_id, parent_span_id, ingest_run_id, file_hash, page_no,
            name, pipeline_step, category, annotation_engine, status,
            started_at, ended_at, duration_ms, attributes_json,
            error_type, error_message, error_stack
        FROM ingest_diagnostic_spans
        {where_sql}
        ORDER BY started_at ASC, duration_ms DESC
        LIMIT ?
        """,
        [*parameters, safe_limit],
    ).fetchall()
    spans = [span_record(row) for row in rows]
    events = _diagnostic_events(
        con,
        ingest_run_id=ingest_run_id,
        file_hash=file_hash,
        page_no=page_no,
        q=q,
        limit=safe_limit,
    )
    return DiagnosticTracePayload(
        summary=trace_summary(spans, ingest_run_id=ingest_run_id),
        spans=spans,
        events=events,
    )


def _where_clause(
    *,
    ingest_run_id: int | None,
    file_hash: str | None,
    page_no: int | None,
    status: str | None,
    q: str | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    parameters: list[object] = []
    if ingest_run_id is not None:
        clauses.append("ingest_run_id = ?")
        parameters.append(ingest_run_id)
    if file_hash:
        clauses.append("file_hash = ?")
        parameters.append(file_hash)
    if page_no is not None:
        clauses.append("page_no = ?")
        parameters.append(page_no)
    if status and status != "all":
        clauses.append("status = ?")
        parameters.append(status)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        clauses.append(
            """
            (
                name ILIKE ?
                OR pipeline_step ILIKE ?
                OR category ILIKE ?
                OR coalesce(annotation_engine, '') ILIKE ?
                OR coalesce(error_message, '') ILIKE ?
            )
            """
        )
        parameters.extend([needle, needle, needle, needle, needle])
    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", parameters)


def _diagnostic_events(  # noqa: PLR0913
    con: DuckConnection,
    *,
    ingest_run_id: int | None,
    file_hash: str | None,
    page_no: int | None,
    q: str | None,
    limit: int,
) -> list[DiagnosticEventRecord]:
    if not table_exists(con, "ingest_diagnostic_events"):
        return []
    clauses: list[str] = []
    parameters: list[object] = []
    if ingest_run_id is not None:
        clauses.append("ingest_run_id = ?")
        parameters.append(ingest_run_id)
    if file_hash:
        clauses.append("file_hash = ?")
        parameters.append(file_hash)
    if page_no is not None:
        clauses.append("page_no = ?")
        parameters.append(page_no)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        clauses.append("(name ILIKE ? OR coalesce(message, '') ILIKE ?)")
        parameters.extend([needle, needle])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = con.execute(
        f"""
        SELECT
            event_id, trace_id, span_id, ingest_run_id, file_hash, page_no,
            timestamp, event_type, name, severity, message, attributes_json
        FROM ingest_diagnostic_events
        {where_sql}
        ORDER BY timestamp ASC, event_id ASC
        LIMIT ?
        """,
        [*parameters, limit],
    ).fetchall()
    return [event_record(row) for row in rows]
