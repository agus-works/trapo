from __future__ import annotations

import json
from typing import Any

from trapo.db import DuckConnection, next_table_id, table_exists


def start_model_lease(  # noqa: PLR0913
    connection: DuckConnection,
    *,
    ingest_run_id: int,
    execution_key: str,
    provider: str,
    model: str,
    requested_context_tokens: int | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if not table_exists(connection, "ingest_model_leases"):
        return 0
    lease_id = next_table_id(
        connection,
        table_name="ingest_model_leases",
        column_name="lease_id",
        sequence_name="ingest_model_lease_id_seq",
    )
    connection.execute(
        """
        INSERT INTO ingest_model_leases (
            lease_id, ingest_run_id, execution_key, provider, model,
            requested_context_tokens, status, started_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, 'running', now(), ?::JSON)
        """,
        [
            lease_id,
            ingest_run_id,
            execution_key,
            provider,
            model,
            requested_context_tokens,
            json.dumps(metadata or {}),
        ],
    )
    return lease_id


def finish_model_lease(  # noqa: PLR0913
    connection: DuckConnection,
    lease_id: int,
    *,
    status: str,
    verified_context_tokens: int | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if lease_id <= 0 or not table_exists(connection, "ingest_model_leases"):
        return
    connection.execute(
        """
        UPDATE ingest_model_leases
        SET status = ?, finished_at = now(),
            duration_ms = date_diff('millisecond', started_at, now()),
            verified_context_tokens = ?,
            error = ?,
            metadata_json = ?::JSON
        WHERE lease_id = ?
        """,
        [
            status,
            verified_context_tokens,
            error,
            json.dumps(metadata or {}),
            lease_id,
        ],
    )
