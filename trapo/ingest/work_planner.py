from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trapo.db import DuckConnection, next_table_id, table_exists


WORK_STATUS_PLANNED = "planned"
WORK_STATUS_RUNNING = "running"
WORK_STATUS_OK = "ok"
WORK_STATUS_ERROR = "error"
WORK_STATUS_SKIPPED = "skipped"


@dataclass(frozen=True)
class WorkUnit:
    ingest_run_id: int
    work_key: str
    phase: str
    engine: str
    provider: str
    model: str
    execution_key: str
    file_hash: str | None = None
    page_no: int | None = None
    profile: str | None = None
    artifact_variant: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageArtifact:
    ingest_run_id: int
    file_hash: str
    page_no: int
    variant: str
    page_width: float | None
    page_height: float | None
    render_width: int
    render_height: int
    mime_type: str
    image_sha256: str
    cache_path: Path | None
    source_variant: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def upsert_work_unit(connection: DuckConnection, unit: WorkUnit) -> int:
    if not table_exists(connection, "ingest_work_units"):
        return 0
    existing = connection.execute(
        """
        SELECT work_unit_id
        FROM ingest_work_units
        WHERE ingest_run_id = ? AND work_key = ?
        """,
        [unit.ingest_run_id, unit.work_key],
    ).fetchone()
    work_unit_id = (
        int(existing[0])
        if existing
        else next_table_id(
            connection,
            table_name="ingest_work_units",
            column_name="work_unit_id",
            sequence_name="ingest_work_unit_id_seq",
        )
    )
    connection.execute(
        """
        INSERT INTO ingest_work_units (
            work_unit_id, ingest_run_id, work_key, file_hash, page_no, phase,
            engine, provider, model, profile, execution_key, artifact_variant,
            status, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
        ON CONFLICT (ingest_run_id, work_key) DO UPDATE SET
            file_hash = excluded.file_hash,
            page_no = excluded.page_no,
            phase = excluded.phase,
            engine = excluded.engine,
            provider = excluded.provider,
            model = excluded.model,
            profile = excluded.profile,
            execution_key = excluded.execution_key,
            artifact_variant = excluded.artifact_variant,
            metadata_json = excluded.metadata_json,
            status = CASE
                WHEN ingest_work_units.status IN ('ok', 'error', 'skipped')
                    THEN ingest_work_units.status
                ELSE excluded.status
            END
        """,
        [
            work_unit_id,
            unit.ingest_run_id,
            unit.work_key,
            unit.file_hash,
            unit.page_no,
            unit.phase,
            unit.engine,
            unit.provider,
            unit.model,
            unit.profile,
            unit.execution_key,
            unit.artifact_variant,
            WORK_STATUS_PLANNED,
            json.dumps(unit.metadata),
        ],
    )
    return work_unit_id


def start_work_unit(
    connection: DuckConnection, ingest_run_id: int, work_key: str
) -> None:
    if not table_exists(connection, "ingest_work_units"):
        return
    connection.execute(
        """
        UPDATE ingest_work_units
        SET status = ?, attempt_count = attempt_count + 1, started_at = now(),
            finished_at = NULL, duration_ms = NULL, error = NULL
        WHERE ingest_run_id = ? AND work_key = ?
        """,
        [WORK_STATUS_RUNNING, ingest_run_id, work_key],
    )


def finish_work_unit(
    connection: DuckConnection,
    ingest_run_id: int,
    work_key: str,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    _finish_work_unit(
        connection,
        ingest_run_id,
        work_key,
        status=WORK_STATUS_OK,
        result=result,
        error=None,
    )


def fail_work_unit(
    connection: DuckConnection,
    ingest_run_id: int,
    work_key: str,
    error: str,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    _finish_work_unit(
        connection,
        ingest_run_id,
        work_key,
        status=WORK_STATUS_ERROR,
        result=result,
        error=error,
    )


def skip_work_unit(
    connection: DuckConnection,
    ingest_run_id: int,
    work_key: str,
    *,
    reason: str,
) -> None:
    _finish_work_unit(
        connection,
        ingest_run_id,
        work_key,
        status=WORK_STATUS_SKIPPED,
        result={"reason": reason},
        error=None,
    )


def upsert_page_artifact(connection: DuckConnection, artifact: PageArtifact) -> None:
    if not table_exists(connection, "ingest_page_artifacts"):
        return
    connection.execute(
        """
        INSERT INTO ingest_page_artifacts (
            ingest_run_id, file_hash, page_no, variant, page_width, page_height,
            render_width, render_height, mime_type, image_sha256, cache_path,
            source_variant, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
        ON CONFLICT (ingest_run_id, file_hash, page_no, variant) DO UPDATE SET
            page_width = excluded.page_width,
            page_height = excluded.page_height,
            render_width = excluded.render_width,
            render_height = excluded.render_height,
            mime_type = excluded.mime_type,
            image_sha256 = excluded.image_sha256,
            cache_path = excluded.cache_path,
            source_variant = excluded.source_variant,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            artifact.ingest_run_id,
            artifact.file_hash,
            artifact.page_no,
            artifact.variant,
            artifact.page_width,
            artifact.page_height,
            artifact.render_width,
            artifact.render_height,
            artifact.mime_type,
            artifact.image_sha256,
            str(artifact.cache_path) if artifact.cache_path else None,
            artifact.source_variant,
            json.dumps(artifact.metadata),
        ],
    )


def _finish_work_unit(  # noqa: PLR0913
    connection: DuckConnection,
    ingest_run_id: int,
    work_key: str,
    *,
    status: str,
    result: dict[str, Any] | None,
    error: str | None,
) -> None:
    if not table_exists(connection, "ingest_work_units"):
        return
    connection.execute(
        """
        UPDATE ingest_work_units
        SET status = ?, finished_at = now(),
            duration_ms = CASE
                WHEN started_at IS NULL THEN NULL
                ELSE date_diff('millisecond', started_at, now())
            END,
            result_json = ?::JSON,
            error = ?
        WHERE ingest_run_id = ? AND work_key = ?
        """,
        [
            status,
            json.dumps(result or {}),
            error,
            ingest_run_id,
            work_key,
        ],
    )
