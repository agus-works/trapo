from __future__ import annotations

from datetime import datetime
from typing import cast

from trapo.db import DuckConnection, table_exists
from trapo.server.diagnostic_models import (
    DiagnosticBatchRecord,
    DiagnosticProgressPayload,
    DiagnosticProgressSummary,
    DiagnosticWorkUnitRecord,
)
from trapo.server.provenance import parse_json_value


MAX_PROGRESS_LIMIT = 10000


def diagnostic_progress(
    con: DuckConnection,
    *,
    ingest_run_id: int | None = None,
    limit: int = MAX_PROGRESS_LIMIT,
) -> DiagnosticProgressPayload:
    if not table_exists(con, "ingest_work_units"):
        return DiagnosticProgressPayload(summary=DiagnosticProgressSummary())
    run_id = ingest_run_id or _latest_ingest_run_id(con)
    if run_id is None:
        return DiagnosticProgressPayload(summary=DiagnosticProgressSummary())
    safe_limit = max(1, min(limit, MAX_PROGRESS_LIMIT))
    work_units = _diagnostic_work_units(con, ingest_run_id=run_id, limit=safe_limit)
    return DiagnosticProgressPayload(
        summary=_progress_summary(run_id, work_units),
        work_units=work_units,
        batches=_diagnostic_batches(con, ingest_run_id=run_id, limit=safe_limit),
    )


def _diagnostic_work_units(
    con: DuckConnection, *, ingest_run_id: int, limit: int
) -> list[DiagnosticWorkUnitRecord]:
    rows = con.execute(
        """
        SELECT
            wu.work_unit_id, wu.ingest_run_id, wu.work_key, wu.file_hash,
            f.filename,
            coalesce(l.path, json_extract_string(wu.metadata_json, '$.source_path')) AS source_path,
            wu.page_no, wu.phase,
            engine, provider, model, profile, execution_key, artifact_variant,
            wu.status, wu.attempt_count, wu.started_at, wu.finished_at,
            wu.duration_ms, wu.error, wu.result_json, wu.metadata_json
        FROM ingest_work_units wu
        LEFT JOIN files f ON f.file_hash = wu.file_hash
        LEFT JOIN (
            SELECT file_hash, any_value(path) AS path
            FROM file_locations
            GROUP BY file_hash
        ) l ON l.file_hash = wu.file_hash
        WHERE wu.ingest_run_id = ?
        ORDER BY
            CASE phase
                WHEN 'orientation' THEN 1
                WHEN 'artifact' THEN 2
                WHEN 'annotation' THEN 3
                WHEN 'markdown' THEN 4
                ELSE 9
            END,
            execution_key,
            file_hash,
            page_no NULLS FIRST,
            work_unit_id
        LIMIT ?
        """,
        [ingest_run_id, limit],
    ).fetchall()
    return [_work_unit_record(row) for row in rows]


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


def _diagnostic_batches(
    con: DuckConnection, *, ingest_run_id: int, limit: int
) -> list[DiagnosticBatchRecord]:
    if not table_exists(con, "ingest_model_leases"):
        return []
    rows = con.execute(
        """
        SELECT
            lease_id, ingest_run_id, execution_key, provider, model,
            requested_context_tokens, verified_context_tokens, status,
            started_at, finished_at, duration_ms, error, metadata_json
        FROM ingest_model_leases
        WHERE ingest_run_id = ?
        ORDER BY started_at ASC, lease_id ASC
        LIMIT ?
        """,
        [ingest_run_id, limit],
    ).fetchall()
    return [_batch_record(row) for row in rows]


def _progress_summary(
    ingest_run_id: int,
    work_units: list[DiagnosticWorkUnitRecord],
) -> DiagnosticProgressSummary:
    total = len(work_units)
    completed = sum(1 for unit in work_units if unit.status == "ok")
    failed = sum(1 for unit in work_units if unit.status == "error")
    skipped = sum(1 for unit in work_units if unit.status == "skipped")
    running = sum(1 for unit in work_units if unit.status == "running")
    planned = sum(1 for unit in work_units if unit.status == "planned")
    terminal = completed + failed + skipped
    durations = [
        unit.duration_ms
        for unit in work_units
        if unit.status in {"ok", "error", "skipped"} and unit.duration_ms is not None
    ]
    remaining = total - terminal
    average_duration = sum(durations) / len(durations) if durations else None
    return DiagnosticProgressSummary(
        ingest_run_id=ingest_run_id,
        total_units=total,
        planned_units=planned,
        running_units=running,
        completed_units=completed,
        failed_units=failed,
        skipped_units=skipped,
        percent_complete=(terminal / total * 100.0) if total else 0.0,
        estimated_remaining_ms=(
            average_duration * remaining if average_duration is not None else None
        ),
    )


def _work_unit_record(row: tuple[object, ...]) -> DiagnosticWorkUnitRecord:
    return DiagnosticWorkUnitRecord(
        work_unit_id=_int(row[0]),
        ingest_run_id=_int(row[1]),
        work_key=str(row[2]),
        file_hash=str(row[3]) if row[3] is not None else None,
        filename=str(row[4]) if row[4] is not None else None,
        source_path=str(row[5]) if row[5] is not None else None,
        page_no=_optional_int(row[6]),
        phase=str(row[7]),
        engine=str(row[8]),
        provider=str(row[9]),
        model=str(row[10]),
        profile=str(row[11]) if row[11] is not None else None,
        execution_key=str(row[12]),
        artifact_variant=str(row[13]) if row[13] is not None else None,
        status=str(row[14]),
        attempt_count=_int(row[15]),
        started_at=_optional_datetime(row[16]),
        finished_at=_optional_datetime(row[17]),
        duration_ms=_optional_float(row[18]),
        error=str(row[19]) if row[19] is not None else None,
        result=_dict_value(row[20]),
        metadata=_dict_value(row[21]),
    )


def _batch_record(row: tuple[object, ...]) -> DiagnosticBatchRecord:
    return DiagnosticBatchRecord(
        lease_id=_int(row[0]),
        ingest_run_id=_int(row[1]),
        execution_key=str(row[2]),
        provider=str(row[3]),
        model=str(row[4]),
        requested_context_tokens=_optional_int(row[5]),
        verified_context_tokens=_optional_int(row[6]),
        status=str(row[7]),
        started_at=_datetime(row[8]),
        finished_at=_optional_datetime(row[9]),
        duration_ms=_optional_float(row[10]),
        error=str(row[11]) if row[11] is not None else None,
        metadata=_dict_value(row[12]),
    )


def _dict_value(value: object) -> dict[str, object]:
    parsed = parse_json_value(value)
    return parsed if isinstance(parsed, dict) else {}


def _int(value: object) -> int:
    return int(str(value)) if value is not None else 0


def _optional_int(value: object) -> int | None:
    return int(str(value)) if value is not None else None


def _optional_float(value: object) -> float | None:
    return float(str(value)) if value is not None else None


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return cast(datetime, value)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)
