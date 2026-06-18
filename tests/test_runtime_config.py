from __future__ import annotations

from trapo.config import (
    DEFAULT_DB_PATH,
    DEFAULT_OCR_PROVIDER,
    DEFAULT_SOURCE_ROOT,
    RuntimeConfig,
)
from trapo.server.runtime import resolve_launch_path, resolve_source_root


def test_runtime_config_defaults_to_local_docling(monkeypatch) -> None:
    monkeypatch.delenv("TRAPO_SOURCE_ROOT", raising=False)
    config = RuntimeConfig.from_env()

    assert config.db_path == DEFAULT_DB_PATH
    assert config.source_root == DEFAULT_SOURCE_ROOT
    assert config.ocr_provider == DEFAULT_OCR_PROVIDER
    assert config.ocr_model == "docling"


def test_runtime_config_reads_source_root_and_otel_env(monkeypatch) -> None:
    monkeypatch.setenv("TRAPO_SOURCE_ROOT", "/data/source")
    monkeypatch.setenv("TRAPO_OTEL_EXPORTER", "console")
    monkeypatch.setenv("TRAPO_OTEL_ENABLED", "false")

    config = RuntimeConfig.from_env(db_path="custom.duckdb")

    assert config.db_path == "custom.duckdb"
    assert config.source_root == "/data/source"
    assert config.otel_exporter == "console"
    assert config.otel_enabled is False


def test_launch_path_and_source_root_resolution(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    assert resolve_launch_path("trapo.duckdb", launch_dir=tmp_path) == (
        tmp_path / "trapo.duckdb"
    ).resolve(strict=False)
    assert resolve_source_root("source", launch_dir=tmp_path) == source.resolve(
        strict=False
    )
