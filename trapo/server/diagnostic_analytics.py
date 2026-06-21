from __future__ import annotations

from datetime import datetime
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.ingest.lmstudio_models import DEFAULT_LMSTUDIO_REPEAT_PENALTY
from trapo.server.diagnostic_analytics_models import (
    DiagnosticAnalyticsPayload,
    DiagnosticAnalyticsSummary,
    DiagnosticModelLeaseRecord,
    DiagnosticModelsPayload,
)
from trapo.server.diagnostic_analytics_rows import (
    analytics_recommendations,
    file_metadata,
    page_metadata,
    slow_spans,
    span_error_breakdown,
    unit_duration,
    unit_file_label,
    unit_page_label,
    work_unit_breakdown,
)
from trapo.server.diagnostic_models import DiagnosticWorkUnitRecord
from trapo.server.diagnostic_progress import diagnostic_progress
from trapo.server.diagnostic_records import span_record


MAX_ANALYTICS_LIMIT = 50
MAX_SPAN_SCAN_LIMIT = 20000


def diagnostic_analytics(
    con: DuckConnection,
    *,
    ingest_run_id: int | None = None,
    limit: int = MAX_ANALYTICS_LIMIT,
) -> DiagnosticAnalyticsPayload:
    run_id = ingest_run_id or _latest_ingest_run_id(con)
    if run_id is None:
        return DiagnosticAnalyticsPayload(summary=DiagnosticAnalyticsSummary())
    safe_limit = max(1, min(limit, MAX_ANALYTICS_LIMIT))
    progress = diagnostic_progress(con, ingest_run_id=run_id, limit=10000)
    spans = _diagnostic_spans(con, ingest_run_id=run_id)
    summary = _analytics_summary(con, run_id, progress.work_units, spans)
    return DiagnosticAnalyticsPayload(
        summary=summary,
        phase_breakdown=work_unit_breakdown(
            progress.work_units, lambda unit: unit.phase, safe_limit
        ),
        engine_breakdown=work_unit_breakdown(
            progress.work_units,
            lambda unit: f"{unit.phase}:{unit.engine}",
            safe_limit,
            label=lambda unit: f"{unit.phase} / {unit.engine}",
        ),
        model_breakdown=work_unit_breakdown(
            progress.work_units,
            lambda unit: f"{unit.provider}:{unit.model}",
            safe_limit,
            label=lambda unit: f"{unit.provider} / {unit.model}",
        ),
        file_breakdown=work_unit_breakdown(
            [unit for unit in progress.work_units if unit.file_hash],
            lambda unit: str(unit.file_hash),
            safe_limit,
            label=unit_file_label,
            metadata=file_metadata,
        ),
        page_breakdown=work_unit_breakdown(
            [unit for unit in progress.work_units if unit.file_hash and unit.page_no],
            lambda unit: f"{unit.file_hash}:{unit.page_no}",
            safe_limit,
            label=unit_page_label,
            metadata=page_metadata,
        ),
        error_breakdown=span_error_breakdown(spans, summary.duration_ms, safe_limit),
        slow_work_units=_slow_work_units(progress.work_units, safe_limit),
        slow_spans=slow_spans(spans, safe_limit),
        recommendations=analytics_recommendations(summary, progress.work_units),
    )


def diagnostic_models(
    con: DuckConnection,
    *,
    ingest_run_id: int | None = None,
) -> DiagnosticModelsPayload:
    run_id = ingest_run_id or _latest_ingest_run_id(con)
    if run_id is None or not table_exists(con, "ingest_model_leases"):
        return DiagnosticModelsPayload(ingest_run_id=run_id)
    progress = diagnostic_progress(con, ingest_run_id=run_id, limit=10000)
    leases = [
        DiagnosticModelLeaseRecord(
            lease_id=batch.lease_id,
            ingest_run_id=batch.ingest_run_id,
            execution_key=batch.execution_key,
            provider=batch.provider,
            model=batch.model,
            requested_context_tokens=batch.requested_context_tokens,
            verified_context_tokens=batch.verified_context_tokens,
            status=batch.status,
            started_at=batch.started_at,
            finished_at=batch.finished_at,
            duration_ms=batch.duration_ms,
            error=batch.error,
            load_status=_string_metadata(batch.metadata, "load_status"),
            requested_parameters=_requested_parameters(batch.metadata),
            metadata=batch.metadata,
            switch_index=index + 1,
        )
        for index, batch in enumerate(progress.batches)
    ]
    return DiagnosticModelsPayload(ingest_run_id=run_id, leases=leases)


def _analytics_summary(
    con: DuckConnection,
    run_id: int,
    units: list[DiagnosticWorkUnitRecord],
    spans: list[Any],
) -> DiagnosticAnalyticsSummary:
    run_row = _run_row(con, run_id)
    started = _datetime(run_row.get("started_at"))
    finished = _datetime(run_row.get("finished_at"))
    duration_ms = _run_duration_ms(started, finished, units, spans)
    failed_llm_ms = sum(
        span.duration_ms
        for span in spans
        if span.pipeline_step == "lmstudio_chat_completion" and span.status == "error"
    )
    return DiagnosticAnalyticsSummary(
        ingest_run_id=run_id,
        status=str(run_row.get("status") or "unknown"),
        source_directory=str(run_row.get("source_directory") or ""),
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        work_unit_count=len(units),
        failed_work_unit_count=sum(1 for unit in units if unit.status == "error"),
        span_count=len(spans),
        failed_span_count=sum(1 for span in spans if span.status == "error"),
        model_lease_count=_model_lease_count(con, run_id),
        failed_llm_duration_ms=failed_llm_ms,
    )


def _diagnostic_spans(con: DuckConnection, *, ingest_run_id: int) -> list[Any]:
    if not table_exists(con, "ingest_diagnostic_spans"):
        return []
    rows = con.execute(
        """
        SELECT
            span_id, trace_id, parent_span_id, ingest_run_id, file_hash, page_no,
            name, pipeline_step, category, annotation_engine, status,
            started_at, ended_at, duration_ms, attributes_json,
            error_type, error_message, error_stack
        FROM ingest_diagnostic_spans
        WHERE ingest_run_id = ?
        ORDER BY duration_ms DESC
        LIMIT ?
        """,
        [ingest_run_id, MAX_SPAN_SCAN_LIMIT],
    ).fetchall()
    return [span_record(row) for row in rows]


def _run_row(con: DuckConnection, run_id: int) -> dict[str, object]:
    if not table_exists(con, "ingest_runs"):
        return {}
    row = con.execute(
        """
        SELECT ingest_run_id, source_directory, status, started_at, finished_at
        FROM ingest_runs
        WHERE ingest_run_id = ?
        """,
        [run_id],
    ).fetchone()
    if not row:
        return {}
    return {
        "ingest_run_id": row[0],
        "source_directory": row[1],
        "status": row[2],
        "started_at": row[3],
        "finished_at": row[4],
    }


def _latest_ingest_run_id(con: DuckConnection) -> int | None:
    if not table_exists(con, "ingest_runs"):
        return None
    row = con.execute(
        """
        SELECT ingest_run_id
        FROM ingest_runs
        ORDER BY started_at DESC, ingest_run_id DESC
        LIMIT 1
        """
    ).fetchone()
    return int(row[0]) if row else None


def _model_lease_count(con: DuckConnection, run_id: int) -> int:
    if not table_exists(con, "ingest_model_leases"):
        return 0
    row = con.execute(
        "SELECT count(*) FROM ingest_model_leases WHERE ingest_run_id = ?",
        [run_id],
    ).fetchone()
    return int(row[0]) if row else 0


def _run_duration_ms(
    started: datetime | None,
    finished: datetime | None,
    units: list[DiagnosticWorkUnitRecord],
    spans: list[Any],
) -> float:
    if started and finished:
        return max(0.0, (finished - started).total_seconds() * 1000)
    duration = sum(unit_duration(unit) for unit in units)
    if duration:
        return duration
    return sum(float(span.duration_ms) for span in spans)


def _slow_work_units(
    units: list[DiagnosticWorkUnitRecord], limit: int
) -> list[DiagnosticWorkUnitRecord]:
    return sorted(units, key=unit_duration, reverse=True)[:limit]


def _requested_parameters(metadata: dict[str, object]) -> dict[str, object]:
    value = metadata.get("generation_parameters")
    if isinstance(value, dict):
        return value
    value = metadata.get("load_parameters")
    if isinstance(value, dict):
        return value
    return {"repeat_penalty": DEFAULT_LMSTUDIO_REPEAT_PENALTY}


def _string_metadata(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None
