from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from typer.testing import CliRunner
import trapo.server
import trapo.cli as trapo_cli
import uvicorn

from trapo.cli import app
from trapo.db import connect
from trapo.ingest.pipeline import _requested_engines
from trapo.migrations.versions import MIGRATIONS
from trapo.page_orientation import read_page_rotation_degrees
from trapo.skylos_check import SkylosCheckOptions, SkylosCheckResult

SERVE_TEST_PORT = 9876
CLI_ROTATION_DEGREES = 90


def test_init_and_status(tmp_path) -> None:
    runner = CliRunner()
    db_path = tmp_path / "trapo.duckdb"

    init_result = runner.invoke(app, ["init", "--db", str(db_path)])
    assert init_result.exit_code == 0, init_result.output
    assert "Database ready" in init_result.output

    status_result = runner.invoke(app, ["status", "--db", str(db_path)])
    assert status_result.exit_code == 0, status_result.output
    assert f"Schema version: {MIGRATIONS[-1].migration_id}" in status_result.output
    assert "Files: 0" in status_result.output
    assert "Regions: 0" in status_result.output


def test_status_requires_initialized_database(tmp_path) -> None:
    runner = CliRunner()
    db_path = tmp_path / "missing.duckdb"

    result = runner.invoke(app, ["status", "--db", str(db_path)])

    assert result.exit_code == 1, result.output
    assert "not initialized" in result.output


def test_migrate_reports_no_pending_after_init(tmp_path) -> None:
    runner = CliRunner()
    db_path = tmp_path / "trapo.duckdb"

    runner.invoke(app, ["init", "--db", str(db_path)])
    result = runner.invoke(app, ["migrate", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "No pending migrations" in result.output


def test_set_page_rotation_stores_override(tmp_path) -> None:
    runner = CliRunner()
    db_path = tmp_path / "trapo.duckdb"

    init_result = runner.invoke(app, ["init", "--db", str(db_path)])
    assert init_result.exit_code == 0, init_result.output

    result = runner.invoke(
        app,
        [
            "set-page-rotation",
            "abc123",
            str(CLI_ROTATION_DEGREES),
            "--page",
            "1",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"clockwise={CLI_ROTATION_DEGREES}" in result.output
    with connect(db_path) as connection:
        assert (
            read_page_rotation_degrees(connection, "abc123", page_no=1)
            == CLI_ROTATION_DEGREES
        )


def test_init_runs_inside_command_trace(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    db_path = tmp_path / "trapo.duckdb"
    spans: list[tuple[str, dict[str, object] | None]] = []

    @contextmanager
    def fake_traced_command(
        command_name: str,
        *,
        attributes: dict[str, object] | None = None,
        flush_on_exit: bool = True,
    ) -> Iterator[None]:
        _ = flush_on_exit
        spans.append((command_name, attributes))
        yield

    monkeypatch.setenv("TRAPO_SOURCE_ROOT", ".")
    monkeypatch.setenv("TRAPO_OTEL_EXPORTER", "otlp")
    monkeypatch.setattr(trapo_cli, "traced_command", fake_traced_command)
    monkeypatch.setattr(
        trapo_cli, "configure_observability", lambda *_args, **_kwargs: None
    )

    result = runner.invoke(app, ["init", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert spans == [
        ("init", {"db.path": str(db_path), "source.root": ".", "otel.exporter": "otlp"})
    ]


def test_ingest_defaults_to_docling_and_mineru(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_ingest(*, directory, command_name, command_options):
        captured["directory"] = directory
        captured["command_name"] = command_name
        captured["command_options"] = command_options

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setattr(trapo_cli, "_run_ingest", fake_run_ingest)

    result = runner.invoke(app, ["ingest", str(source_dir)])

    assert result.exit_code == 0, result.output
    assert captured["directory"] == source_dir
    assert captured["command_name"] == "ingest"
    options = captured["command_options"]
    assert isinstance(options, trapo_cli.IngestCommandOptions)
    assert options.annotation_engines == "docling,mineru"
    assert options.mineru_backend == "pipeline"
    assert options.page_markdown is True
    assert options.page_markdown_engines == "infinity_markdown"
    assert (
        options.page_markdown_render_dpi == trapo_cli.DEFAULT_PAGE_MARKDOWN_RENDER_DPI
    )
    assert (
        options.page_markdown_image_max_side
        == trapo_cli.DEFAULT_PAGE_MARKDOWN_IMAGE_MAX_SIDE
    )
    assert (
        options.page_markdown_image_format
        == trapo_cli.DEFAULT_PAGE_MARKDOWN_IMAGE_FORMAT
    )
    assert (
        options.page_markdown_jpeg_quality
        == trapo_cli.DEFAULT_PAGE_MARKDOWN_JPEG_QUALITY
    )
    assert options.page_markdown_cache is True
    assert (
        options.page_markdown_cache_root == trapo_cli.DEFAULT_PAGE_MARKDOWN_CACHE_ROOT
    )


def test_ingest_can_disable_page_markdown(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_ingest(*, directory, command_name, command_options):
        captured["directory"] = directory
        captured["command_name"] = command_name
        captured["command_options"] = command_options

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setattr(trapo_cli, "_run_ingest", fake_run_ingest)

    result = runner.invoke(app, ["ingest", str(source_dir), "--no-page-markdown"])

    assert result.exit_code == 0, result.output
    options = captured["command_options"]
    assert isinstance(options, trapo_cli.IngestCommandOptions)
    assert options.page_markdown is False


def test_skylos_check_cli_runs_report_only_by_default(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    captured: dict[str, SkylosCheckOptions] = {}

    def fake_run_skylos_check(options: SkylosCheckOptions) -> SkylosCheckResult:
        captured["options"] = options
        return SkylosCheckResult(
            command=("python", "-m", "skylos.cli"),
            output=options.output,
            sarif=options.sarif,
            returncode=0,
            counts={"danger": 0, "quality": 1},
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(trapo_cli, "run_skylos_check", fake_run_skylos_check)

    result = runner.invoke(app, ["skylos-check", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Skylos findings: 1" in result.output
    assert "quality: 1" in result.output
    options = captured["options"]
    assert options.path == tmp_path
    assert options.strict is False
    assert options.include_sca is True


def test_annotation_engines_all_includes_infinity() -> None:
    assert _requested_engines("all") == ["docling", "mineru", "infinity"]
    assert _requested_engines("lm-studio,local-docling") == ["docling"]


def test_annotation_engines_normalized_aliases() -> None:
    assert _requested_engines("normalized") == [
        "docling_normalized",
        "mineru_normalized",
    ]
    assert _requested_engines("docling-normalized,local-mineru-normalized") == [
        "docling_normalized",
        "mineru_normalized",
    ]


def test_serve_resolves_paths_and_runs_uvicorn(monkeypatch, tmp_path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_create_app(db_path, **kwargs):
        captured["db_path"] = db_path
        captured["source_root"] = kwargs.get("source_root")
        return object()

    def fake_run(app_instance, *, host, port):
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(trapo.server, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)

    source_dir = tmp_path / "source"
    source_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "serve",
            "--db",
            str(tmp_path / "trapo.duckdb"),
            "--src",
            str(source_dir),
            "--host",
            "127.0.0.1",
            "--port",
            str(SERVE_TEST_PORT),
            "--frontend-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == SERVE_TEST_PORT
    assert captured["source_root"] == str(source_dir.resolve())
