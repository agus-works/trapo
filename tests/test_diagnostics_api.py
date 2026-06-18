from __future__ import annotations

import json

from fastapi.testclient import TestClient

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.migrations import apply_migrations
from trapo.server import create_app


def test_diagnostics_api_filters_file_page_and_errors(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_diagnostics(connection)

    client = TestClient(create_app(db_path))

    runs = client.get("/api/diagnostics/runs").json()
    assert runs[0]["ingest_run_id"] == 1
    assert runs[0]["error_count"] == 1

    trace = client.get(
        "/api/diagnostics/trace",
        params={
            "ingest_run_id": 1,
            "file_hash": "hash1",
            "page_no": 2,
            "status": "error",
        },
    ).json()
    assert trace["summary"]["span_count"] == 1
    assert trace["spans"][0]["span_id"] == "page"
    assert trace["spans"][0]["error_message"] == "boom"
    assert trace["events"][0]["message"] == "boom"


def _seed_diagnostics(connection) -> None:
    connection.execute(
        "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (1, '.', 'completed_with_errors')"
    )
    connection.execute(
        """
        INSERT INTO ingest_diagnostic_spans (
            span_id, trace_id, parent_span_id, ingest_run_id, file_hash, page_no,
            name, pipeline_step, category, annotation_engine, status,
            started_at, ended_at, duration_ms, attributes_json,
            error_type, error_message, error_stack
        )
        VALUES
            (
                'root', 'trace', NULL, 1, 'hash1', NULL,
                'trapo.ingest.file', 'file', 'pipeline', NULL, 'ok',
                TIMESTAMP '2026-01-01 00:00:00',
                TIMESTAMP '2026-01-01 00:00:02',
                2000.0, '{}'::JSON, NULL, NULL, NULL
            ),
            (
                'page', 'trace', 'root', 1, 'hash1', 2,
                'trapo.ingest.page_markdown.page', 'page_markdown_page',
                'markdown', 'lmstudio_markdown', 'error',
                TIMESTAMP '2026-01-01 00:00:01',
                TIMESTAMP '2026-01-01 00:00:02',
                1000.0, ?::JSON, 'RuntimeError', 'boom', 'stack'
            )
        """,
        [json.dumps({"page.no": 2})],
    )
    connection.execute(
        """
        INSERT INTO ingest_diagnostic_events (
            event_id, trace_id, span_id, ingest_run_id, file_hash, page_no,
            timestamp, event_type, name, severity, message, attributes_json
        )
        VALUES (
            nextval('diagnostic_event_id_seq'), 'trace', 'page', 1, 'hash1', 2,
            TIMESTAMP '2026-01-01 00:00:02', 'exception', 'exception',
            'error', 'boom', '{}'::JSON
        )
        """
    )
