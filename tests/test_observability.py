from __future__ import annotations

import logging
import sys
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from trapo import observability
from trapo.config import RuntimeConfig
from trapo.logging_filters import (
    PdfFontBBoxFilter,
    TransformersLambdaAliasFilter,
    configure_third_party_logging,
    suppress_noisy_pdf_stderr,
)
from trapo.observability import ObservabilitySettings


def reset_observability() -> None:
    observability._STATE.configured = False
    observability._STATE.configured_settings = None
    observability._STATE.fastapi_app_ids.clear()
    observability._STATE.trace_configured = False
    observability._STATE.httpx_instrumented = False
    observability._STATE.otel_log_handler = None
    observability._STATE.metric_instruments = None


@pytest.fixture(autouse=True)
def observability_state() -> Iterator[None]:
    reset_observability()
    yield
    reset_observability()


def test_runtime_config_otel_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TRAPO_OTEL_ENABLED", raising=False)
    monkeypatch.delenv("TRAPO_OTEL_EXPORTER", raising=False)
    monkeypatch.delenv("TRAPO_OTEL_ENDPOINT", raising=False)
    monkeypatch.delenv("TRAPO_OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("TRAPO_OTEL_CONSOLE", raising=False)

    config = RuntimeConfig.from_env(db_path="test.duckdb")

    assert config.otel_enabled is True
    assert config.otel_exporter == "otlp"
    assert config.otel_endpoint == "http://localhost:4318"
    assert config.otel_service_name == "trapo"
    assert config.otel_console is False


def test_runtime_config_otel_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("TRAPO_OTEL_ENABLED", "false")
    monkeypatch.setenv("TRAPO_OTEL_EXPORTER", "console")
    monkeypatch.setenv("TRAPO_OTEL_ENDPOINT", "http://collector.local:4318")
    monkeypatch.setenv("TRAPO_OTEL_SERVICE_NAME", "trapo-test")
    monkeypatch.setenv("TRAPO_OTEL_CONSOLE", "true")

    config = RuntimeConfig.from_env(db_path="test.duckdb")

    assert config.otel_enabled is False
    assert config.otel_exporter == "console"
    assert config.otel_endpoint == "http://collector.local:4318"
    assert config.otel_service_name == "trapo-test"
    assert config.otel_console is True


def test_configure_observability_uses_otlp_http_defaults(monkeypatch) -> None:
    reset_observability()
    signal_calls: list[str] = []
    monkeypatch.setattr(
        observability, "_otlp_endpoint_available", lambda _endpoint: True
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_traces",
        lambda _settings, *, warning_sink: signal_calls.append("traces"),
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_logs",
        lambda _settings, *, warning_sink: signal_calls.append("logs"),
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_metrics",
        lambda _settings, *, warning_sink: signal_calls.append("metrics"),
    )
    monkeypatch.setattr(
        observability,
        "_instrument_httpx",
        lambda *, warning_sink: signal_calls.append("httpx"),
    )
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)

    settings = ObservabilitySettings(
        enabled=True,
        exporter="otlp",
        endpoint="http://localhost:4318",
        service_name="trapo-test",
        console=False,
    )
    observability.configure_observability(settings)
    observability.configure_observability(settings)

    assert signal_calls == ["traces", "logs", "metrics", "httpx"]
    assert (
        __import__("os").environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
        == "http://localhost:4318"
    )
    assert __import__("os").environ["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"
    assert (
        __import__("os").environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]
        == "http://localhost:4318/v1/traces"
    )
    assert (
        __import__("os").environ["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"]
        == "http://localhost:4318/v1/logs"
    )
    assert (
        __import__("os").environ["OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"]
        == "http://localhost:4318/v1/metrics"
    )


def test_console_exporter_uses_direct_otel(monkeypatch) -> None:
    reset_observability()
    calls: list[str] = []
    monkeypatch.setattr(
        observability,
        "_configure_otel_traces",
        lambda _settings, *, warning_sink: calls.append("traces"),
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_logs",
        lambda _settings, *, warning_sink: calls.append("logs"),
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_metrics",
        lambda _settings, *, warning_sink: calls.append("metrics"),
    )
    monkeypatch.setattr(
        observability,
        "_instrument_httpx",
        lambda *, warning_sink: calls.append("httpx"),
    )

    observability.configure_observability(
        ObservabilitySettings(
            enabled=True,
            exporter="console",
            endpoint="http://localhost:4318",
            service_name="trapo-test",
            console=False,
        )
    )

    assert calls == ["traces", "logs", "metrics", "httpx"]


def test_logfire_proxy_providers_are_replaceable() -> None:
    LogfireProxyTracerProvider = type(
        "ProxyTracerProvider",
        (),
        {"__module__": "opentelemetry.trace"},
    )
    LogfireProxyMeterProvider = type(
        "ProxyMeterProvider",
        (),
        {"__module__": "logfire._internal.metrics"},
    )
    LogfireProxyLoggerProvider = type(
        "ProxyLoggerProvider",
        (),
        {"__module__": "logfire._internal.logs"},
    )

    assert observability._is_proxy_provider(LogfireProxyTracerProvider())
    assert observability._is_proxy_provider(LogfireProxyMeterProvider())
    assert observability._is_proxy_provider(LogfireProxyLoggerProvider())


def test_configure_observability_fails_open_when_collector_is_down(monkeypatch) -> None:
    reset_observability()
    warnings: list[str] = []
    monkeypatch.setattr(
        observability, "_otlp_endpoint_available", lambda _endpoint: False
    )

    observability.configure_observability(
        ObservabilitySettings(
            enabled=True,
            exporter="otlp",
            endpoint="http://localhost:4318",
            service_name="trapo-test",
            console=False,
        ),
        warning_sink=warnings.append,
    )

    assert warnings == [
        "OpenTelemetry collector is not reachable at http://localhost:4318; "
        "continuing without OTLP export."
    ]


def test_httpx_instrumentation_failure_keeps_exporter_enabled(monkeypatch) -> None:
    reset_observability()
    calls: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        observability, "_otlp_endpoint_available", lambda _endpoint: True
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_traces",
        lambda _settings, *, warning_sink: calls.append("traces"),
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_logs",
        lambda _settings, *, warning_sink: calls.append("logs"),
    )
    monkeypatch.setattr(
        observability,
        "_configure_otel_metrics",
        lambda _settings, *, warning_sink: calls.append("metrics"),
    )
    monkeypatch.setattr(
        observability,
        "_instrument_httpx",
        lambda *, warning_sink: warning_sink(
            "HTTPX OpenTelemetry instrumentation is disabled: missing httpx"
        ),
    )

    settings = observability.configure_observability(
        ObservabilitySettings(
            enabled=True,
            exporter="otlp",
            endpoint="http://localhost:4318",
            service_name="trapo-test",
            console=False,
        ),
        warning_sink=warnings.append,
    )

    assert settings.enabled is True
    assert settings.exporter == "otlp"
    assert calls == ["traces", "logs", "metrics"]
    assert warnings == [
        "HTTPX OpenTelemetry instrumentation is disabled: missing httpx"
    ]


def test_fastapi_instrumentation_is_fail_open(monkeypatch) -> None:
    reset_observability()
    warnings: list[str] = []
    settings = ObservabilitySettings(
        enabled=True,
        exporter="console",
        endpoint="http://localhost:4318",
        service_name="trapo-test",
        console=False,
    )
    monkeypatch.setattr(
        observability,
        "configure_observability",
        lambda _config=None, *, warning_sink=None: settings,
    )
    monkeypatch.setattr(
        FastAPIInstrumentor,
        "instrument_app",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    app = FastAPI()

    observability.instrument_fastapi_app(
        app,
        settings,
        warning_sink=warnings.append,
    )

    assert warnings == [
        "FastAPI OpenTelemetry instrumentation is disabled for this app: missing"
    ]


def test_log_progress_adds_timestamp(capsys) -> None:
    observability.log_progress("Reading with Docling", verbosity=1)

    captured = capsys.readouterr()
    assert captured.out.endswith(" Reading with Docling\n")
    assert "T" in captured.out.split(" ", 1)[0]


def test_transformers_lambda_runtime_alias_warning_is_filtered() -> None:
    configure_third_party_logging()
    logger = logging.getLogger("transformers")
    log_filter = TransformersLambdaAliasFilter()
    alias_record = logger.makeRecord(
        logger.name,
        logging.WARNING,
        __file__,
        1,
        "Accessing `%s` from `%s`. Returning `%s` instead. Behavior may be "
        "different and this alias will be removed in future versions.",
        (
            "LambdaRuntimeClient",
            ".models.auto.image_processing_auto",
            "LambdaRuntimeClient",
        ),
        None,
    )
    warning_record = logger.makeRecord(
        logger.name,
        logging.WARNING,
        __file__,
        1,
        "A real Transformers warning",
        (),
        None,
    )

    assert any(
        isinstance(item, TransformersLambdaAliasFilter) for item in logger.filters
    )
    assert log_filter.filter(alias_record) is False
    assert log_filter.filter(warning_record) is True


def test_pdf_fontbbox_warning_filter_is_narrow(capsys) -> None:
    log_filter = PdfFontBBoxFilter()
    logger = logging.getLogger("pdf-test")
    noisy_record = logger.makeRecord(
        logger.name,
        logging.WARNING,
        __file__,
        1,
        "Could not get FontBBox from font descriptor because None cannot be parsed as 4 floats",
        (),
        None,
    )
    useful_record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        __file__,
        1,
        "Stage ocr failed for run 4: bad allocation",
        (),
        None,
    )

    assert log_filter.filter(noisy_record) is False
    assert log_filter.filter(useful_record) is True

    with suppress_noisy_pdf_stderr():
        print(noisy_record.getMessage(), file=sys.stderr)
        print(useful_record.getMessage(), file=sys.stderr)

    captured = capsys.readouterr()
    assert noisy_record.getMessage() not in captured.err
    assert useful_record.getMessage() in captured.err
