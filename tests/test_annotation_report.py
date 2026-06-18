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


LMSTUDIO_ELAPSED_SECONDS = 1.5


def test_read_annotation_comparison_report_summarizes_profiles_and_fusion(
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
    assert by_engine["lmstudio"].status == "ok"
    assert by_engine["lmstudio"].profile_name == "balanced"
    assert by_engine["lmstudio"].page_count == 1
    assert by_engine["lmstudio"].elapsed_seconds == LMSTUDIO_ELAPSED_SECONDS
    assert by_engine["lmstudio_strict"].region_count == 1
    assert by_engine["fusion"].agreement_summary["single_engine_region_count"] == 1

    formatted = format_annotation_comparison_report(report)
    assert "Annotation report: file_hash=file-1 filename=sample.pdf" in formatted
    assert "lmstudio_strict\tok\t1\t1" in formatted
    assert "fusion\tok\t1\t1" in formatted
    assert "all=0,multi=1,single=1" in formatted


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
    assert "lmstudio\tok\t2\t1" in result.output
    assert "lmstudio_strict\tok\t1\t1" in result.output
    assert "fusion\tok\t1\t1" in result.output


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
        "lmstudio",
        text="one two",
        output_json={
            "prompt_profile": "balanced",
            "pages": [{"page_no": 1, "elapsed_seconds": LMSTUDIO_ELAPSED_SECONDS}],
        },
    )
    _insert_ocr(
        connection,
        "lmstudio_strict",
        text="one",
        output_json={
            "prompt_profile": "strict",
            "pages": [{"page_no": 1, "elapsed_seconds": 2.0}],
        },
    )
    _insert_ocr(
        connection,
        "fusion",
        text="one",
        output_json={
            "profile": {"name": "balanced"},
            "agreement_summary": {
                "all_source_engines_region_count": 0,
                "multi_engine_region_count": 1,
                "single_engine_region_count": 1,
            },
        },
    )
    _insert_region(connection, "lmstudio-a", "lmstudio")
    _insert_region(connection, "lmstudio-b", "lmstudio")
    _insert_region(connection, "lmstudio-strict-a", "lmstudio_strict")
    _insert_region(connection, "fusion-a", "fusion")


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
