from __future__ import annotations

import json

from fastapi.testclient import TestClient

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.migrations import apply_migrations
from trapo.server import create_app


EXPECTED_PROGRESS_UNITS = 2
LMSTUDIO_MAX_CONTEXT = 262_144
EXPECTED_REPEAT_PENALTY = 1.2


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


def test_diagnostics_progress_api_returns_work_units_and_batches(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        connection.execute(
            "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (1, '.', 'running')"
        )
        connection.execute(
            """
            INSERT INTO ingest_work_units (
                work_unit_id, ingest_run_id, work_key, file_hash, page_no, phase,
                engine, provider, model, execution_key, status, attempt_count,
                duration_ms, result_json, metadata_json
            )
            VALUES
                (
                    1, 1, 'annotation:infinity:hash1', 'hash1', 1,
                    'annotation', 'infinity', 'local-infinity-parser2',
                    'infinity-parser2-flash',
                    'lmstudio:http://localhost:1234/v1:infinity-parser2-flash',
                    'ok', 1, 1200.0, '{"regions": 3}'::JSON,
                    '{"source_path": "sample.pdf"}'::JSON
                ),
                (
                    2, 1, 'markdown:infinity_markdown:hash1', 'hash1', 1,
                    'markdown', 'infinity_markdown', 'local-infinity-parser2',
                    'infinity-parser2-flash',
                    'lmstudio:http://localhost:1234/v1:infinity-parser2-flash',
                    'planned', 0, NULL, '{}'::JSON, '{}'::JSON
                )
            """
        )
        connection.execute(
            """
            INSERT INTO ingest_model_leases (
                lease_id, ingest_run_id, execution_key, provider, model,
                requested_context_tokens, verified_context_tokens, status,
                started_at, finished_at, duration_ms, metadata_json
            )
            VALUES (
                1, 1,
                'lmstudio:http://localhost:1234/v1:infinity-parser2-flash',
                'lmstudio', 'infinity-parser2-flash',
                262144, 262144, 'ok',
                TIMESTAMP '2026-01-01 00:00:00',
                TIMESTAMP '2026-01-01 00:00:02',
                2000.0,
                '{"load_status": "loaded_max"}'::JSON
            )
            """
        )

    client = TestClient(create_app(db_path))
    progress = client.get(
        "/api/diagnostics/progress", params={"ingest_run_id": 1}
    ).json()

    assert progress["summary"]["total_units"] == EXPECTED_PROGRESS_UNITS
    assert progress["summary"]["completed_units"] == 1
    assert progress["summary"]["planned_units"] == 1
    assert progress["work_units"][0]["engine"] == "infinity"
    assert progress["work_units"][0]["source_path"] == "sample.pdf"
    assert progress["batches"][0]["verified_context_tokens"] == LMSTUDIO_MAX_CONTEXT

    analytics = client.get(
        "/api/diagnostics/analytics", params={"ingest_run_id": 1}
    ).json()
    assert analytics["summary"]["work_unit_count"] == EXPECTED_PROGRESS_UNITS
    assert analytics["phase_breakdown"][0]["id"] == "annotation"
    assert analytics["model_breakdown"][0]["metadata"] == {}

    models = client.get("/api/diagnostics/models", params={"ingest_run_id": 1}).json()
    assert (
        models["leases"][0]["requested_parameters"]["repeat_penalty"]
        == EXPECTED_REPEAT_PENALTY
    )


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
                'markdown', 'infinity_markdown', 'error',
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
