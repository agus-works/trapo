from __future__ import annotations

import json

from typer.testing import CliRunner

from trapo.annotation_report import (
    format_annotation_comparison_report,
    read_annotation_comparison_report,
)
from trapo.cli import app
from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.migrations import apply_migrations


INFINITY_ELAPSED_SECONDS = 1.5


def test_read_annotation_comparison_report_summarizes_active_engines(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_report_rows(connection)

        report = read_annotation_comparison_report(connection, "file-1")

    assert report.filename == "sample.pdf"
    by_engine = {engine.annotation_engine: engine for engine in report.engines}
    assert sorted(by_engine) == ["docling", "infinity", "mineru"]
    assert by_engine["infinity"].status == "ok"
    assert by_engine["infinity"].page_count == 1
    assert by_engine["infinity"].elapsed_seconds == INFINITY_ELAPSED_SECONDS
    assert by_engine["mineru"].region_count == 1

    formatted = format_annotation_comparison_report(report)
    assert "Annotation report: file_hash=file-1 filename=sample.pdf" in formatted
    assert "infinity\tok\t2\t1" in formatted
    assert "mineru\tok\t1\t1" in formatted


def test_annotation_report_cli_prints_comparison(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    runner = CliRunner()

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _seed_report_rows(connection)

    result = runner.invoke(app, ["annotation-report", "file-1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "engine\tstatus\tregions\tpages" in result.output
    assert "docling\tok\t1\t1" in result.output
    assert "infinity\tok\t2\t1" in result.output
    assert "mineru\tok\t1\t1" in result.output


def _seed_report_rows(connection) -> None:
    connection.execute(
        "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (1, '.', 'ok')"
    )
    connection.execute(
        """
        INSERT INTO files (file_hash, filename, extension, size_bytes)
        VALUES ('file-1', 'sample.pdf', '.pdf', 123)
        """
    )
    _insert_ocr(
        connection,
        "infinity",
        text="one two",
        output_json={
            "pages": [{"page_no": 1, "elapsed_seconds": INFINITY_ELAPSED_SECONDS}],
        },
    )
    _insert_ocr(
        connection,
        "mineru",
        text="one",
        output_json={
            "pages": [{"page_no": 1, "elapsed_seconds": 2.0}],
        },
    )
    _insert_ocr(
        connection,
        "docling",
        text="one",
        output_json={"pages": [{"page_no": 1}]},
    )
    _insert_region(connection, "infinity-a", "infinity")
    _insert_region(connection, "infinity-b", "infinity")
    _insert_region(connection, "mineru-a", "mineru")
    _insert_region(connection, "docling-a", "docling")


def _insert_ocr(
    connection, annotation_engine: str, *, text: str, output_json: dict[str, object]
) -> None:
    connection.execute(
        """
        INSERT INTO ocr_documents (
            file_hash, annotation_engine, ingest_run_id, text, output_json, status,
            reader_provider, reader_model, metadata_json
        )
        VALUES ('file-1', ?, 1, ?, ?::JSON, 'ok', 'provider', 'model', '{}'::JSON)
        """,
        [annotation_engine, text, json.dumps(output_json)],
    )


def _insert_region(connection, region_id: str, annotation_engine: str) -> None:
    connection.execute(
        """
        INSERT INTO document_regions (
            region_id, file_hash, annotation_engine, annotation_provider,
            annotation_model, page_no, source_ref, label, text, context_text,
            raw_bbox_json, region_kind, metadata_json
        )
        VALUES (
            ?, 'file-1', ?, 'provider', 'model', 1, ?, 'text', 'one', 'one',
            '{"left":0,"top":0,"right":10,"bottom":10,"coord_origin":"TOPLEFT"}'::JSON,
            'text', '{}'::JSON
        )
        """,
        [region_id, annotation_engine, region_id],
    )
