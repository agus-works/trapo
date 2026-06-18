from __future__ import annotations

import os
import logging
import socket
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from types import TracebackType
from typing import Any, Literal
from urllib.parse import urlparse

from trapo.config import (
    DEFAULT_OTEL_CONSOLE,
    DEFAULT_OTEL_ENABLED,
    DEFAULT_OTEL_ENDPOINT,
    DEFAULT_OTEL_EXPORTER,
    DEFAULT_OTEL_SERVICE_NAME,
    RuntimeConfig,
    load_local_env,
)
from trapo.logging_filters import configure_third_party_logging


OtelExporter = Literal["off", "otlp", "console", "logfire"]
SendToLogfire = Literal["if-token-present"] | bool | None
OTEL_EXPORTER_ALIASES: dict[str, OtelExporter] = {
    "off": "off",
    "disabled": "off",
    "none": "off",
    "otlp": "otlp",
    "otel": "otlp",
    "lgtm": "otlp",
    "console": "console",
    "stdout": "console",
    "logfire": "logfire",
}
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "exception": logging.ERROR,
}


@dataclass(frozen=True)
class ObservabilitySettings:
    enabled: bool
    exporter: OtelExporter
    endpoint: str
    service_name: str
    console: bool

    @classmethod
    def from_env(cls) -> "ObservabilitySettings":
        load_local_env()
        return cls(
            enabled=_env_bool("TRAPO_OTEL_ENABLED", DEFAULT_OTEL_ENABLED),
            exporter=_otel_exporter(
                os.getenv("TRAPO_OTEL_EXPORTER", DEFAULT_OTEL_EXPORTER)
            ),
            endpoint=os.getenv("TRAPO_OTEL_ENDPOINT", DEFAULT_OTEL_ENDPOINT),
            service_name=os.getenv(
                "TRAPO_OTEL_SERVICE_NAME", DEFAULT_OTEL_SERVICE_NAME
            ),
            console=_env_bool("TRAPO_OTEL_CONSOLE", DEFAULT_OTEL_CONSOLE),
        )

    @classmethod
    def from_config(cls, config: RuntimeConfig) -> "ObservabilitySettings":
        return cls(
            enabled=config.otel_enabled,
            exporter=config.otel_exporter,
            endpoint=config.otel_endpoint,
            service_name=config.otel_service_name,
            console=config.otel_console,
        )


@dataclass(frozen=True)
class MetricInstruments:
    operation_events: Any
    provider_calls: Any
    provider_errors: Any
    command_runs: Any
    command_duration_ms: Any
    provider_duration_ms: Any
    provider_estimated_tokens: Any


@dataclass
class ObservabilityState:
    configured: bool = False
    configured_settings: ObservabilitySettings | None = None
    fastapi_app_ids: set[int] = field(default_factory=set)
    trace_configured: bool = False
    httpx_instrumented: bool = False
    otel_log_handler: logging.Handler | None = None
    metric_instruments: MetricInstruments | None = None


_STATE = ObservabilityState()


@dataclass
class TrapoSpanHandle:
    otel_span: Any | None = None
    diagnostic_span: Any | None = None

    @property
    def has_span(self) -> bool:
        return self.otel_span is not None or self.diagnostic_span is not None

    def set_attribute(self, key: str, value: object) -> None:
        if self.otel_span is not None:
            try:
                self.otel_span.set_attribute(key, value)
            except Exception:
                pass
        if self.diagnostic_span is not None:
            try:
                self.diagnostic_span.set_attributes({key: value})
            except Exception:
                pass

    def set_attributes(self, attributes: dict[str, object | None]) -> None:
        for key, value in attributes.items():
            if value is not None:
                self.set_attribute(key, value)

    def record_exception(self, exc: BaseException) -> None:
        if self.diagnostic_span is not None:
            try:
                self.diagnostic_span.record_exception(exc)
            except Exception:
                pass


def configure_observability(
    config: RuntimeConfig | ObservabilitySettings | None = None,
    *,
    warning_sink: Callable[[str], None] | None = None,
) -> ObservabilitySettings:
    settings = _settings(config)
    configure_third_party_logging()
    if _STATE.configured:
        return _STATE.configured_settings or settings
    _STATE.configured = True
    if not settings.enabled or settings.exporter == "off":
        _STATE.configured_settings = settings
        return settings

    configured_settings = settings
    if settings.exporter == "otlp" and not _otlp_endpoint_available(settings.endpoint):
        configured_settings = _disabled_settings(settings)
        _warn_once(
            warning_sink,
            "OpenTelemetry collector is not reachable at "
            f"{settings.endpoint}; continuing without OTLP export.",
        )

    if configured_settings.enabled:
        try:
            if settings.exporter in {"otlp", "console"}:
                _configure_direct_otel(settings, warning_sink=warning_sink)
            elif settings.exporter == "logfire":
                _configure_logfire(settings, warning_sink=warning_sink)
        except Exception as exc:
            configured_settings = _disabled_settings(settings)
            _warn_once(
                warning_sink,
                f"OpenTelemetry instrumentation is disabled for this process: {exc}",
            )
    _STATE.configured_settings = configured_settings
    return configured_settings


def instrument_fastapi_app(
    app: Any,
    config: RuntimeConfig | ObservabilitySettings | None = None,
    *,
    warning_sink: Callable[[str], None] | None = None,
) -> None:
    settings = configure_observability(config, warning_sink=warning_sink)
    if not settings.enabled or settings.exporter == "off":
        return
    app_id = id(app)
    if app_id in _STATE.fastapi_app_ids:
        return
    _STATE.fastapi_app_ids.add(app_id)
    try:
        if settings.exporter == "logfire":
            # Logfire is optional and only needed for the explicit Logfire exporter.
            import logfire  # noqa: PLC0415

            logfire.instrument_fastapi(app, capture_headers=False)
        else:
            from opentelemetry.instrumentation.fastapi import (  # noqa: PLC0415
                FastAPIInstrumentor,
            )

            FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        _warn_once(
            warning_sink,
            f"FastAPI OpenTelemetry instrumentation is disabled for this app: {exc}",
        )


def timestamped(message: str) -> str:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    return f"{timestamp} {message}"


def log_progress(message: str, *, verbosity: int) -> None:
    if verbosity > 0:
        print(timestamped(message), flush=True)
    log_structured(message, phase="progress")


def log_structured(message: str, *, level: str = "info", **attributes: object) -> None:
    logger = logging.getLogger("trapo")
    level_number = _log_level(level)
    try:
        logger.log(level_number, message, extra=_log_extra(attributes))
    except Exception:
        pass
    try:
        from trapo.diagnostics import record_diagnostic_event  # noqa: PLC0415

        record_diagnostic_event(
            "log",
            message=message,
            severity=level,
            attributes=attributes,
        )
    except Exception:
        return


@contextmanager
def traced_span(
    name: str,
    *,
    attributes: dict[str, object] | None = None,
) -> Any:
    """Start an OpenTelemetry span if tracing is available, otherwise no-op."""
    span_attributes = attributes or {}
    span_context = None
    span = None
    try:
        from opentelemetry import trace  # noqa: PLC0415

        tracer = trace.get_tracer("trapo")
        span_context = tracer.start_as_current_span(
            name,
            attributes=_safe_attributes(span_attributes),
        )
        span = span_context.__enter__()
    except Exception:
        span_context = None
        span = None

    diagnostic_span = None
    try:
        from trapo.diagnostics import start_diagnostic_span  # noqa: PLC0415

        trace_id, span_id = _span_context_ids(span)
        diagnostic_span = start_diagnostic_span(
            name,
            attributes=span_attributes,
            trace_id=trace_id,
            span_id=span_id,
        )
    except Exception:
        diagnostic_span = None

    handle = TrapoSpanHandle(otel_span=span, diagnostic_span=diagnostic_span)

    exc_info: tuple[
        type[BaseException] | None, BaseException | None, TracebackType | None
    ] = (
        None,
        None,
        None,
    )
    try:
        yield handle if handle.has_span else None
    except BaseException as exc:
        exc_info = sys.exc_info()
        mark_span_error(handle if handle.has_span else None, exc)
        raise
    finally:
        try:
            from trapo.diagnostics import finish_diagnostic_span  # noqa: PLC0415

            finish_diagnostic_span(diagnostic_span)
        except Exception:
            pass
        try:
            if span_context is not None:
                span_context.__exit__(*exc_info)
        except Exception:
            pass


@contextmanager
def traced_command(
    command_name: str,
    *,
    attributes: dict[str, object] | None = None,
    flush_on_exit: bool = True,
) -> Any:
    """Create a root span and command metrics for a Typer command body."""
    status = "ok"
    started_at = perf_counter()
    span_attributes: dict[str, object] = {"command.name": command_name}
    if attributes:
        span_attributes.update(attributes)
    try:
        with traced_span(
            f"trapo.command.{command_name}",
            attributes=span_attributes,
        ) as span:
            try:
                yield span
            except BaseException:
                status = "error"
                raise
            finally:
                duration_ms = (perf_counter() - started_at) * 1000
                span_set_attributes(
                    span,
                    {
                        "command.status": status,
                        "command.duration_ms": duration_ms,
                    },
                )
                record_command_telemetry(
                    command_name=command_name,
                    status=status,
                    duration_ms=duration_ms,
                    attributes=attributes,
                )
    finally:
        if flush_on_exit:
            flush_observability()


def flush_observability(*, timeout_millis: int = 3000) -> bool:
    """Flush batched telemetry for short-lived CLI commands."""
    flushed = False
    try:
        import logfire  # noqa: PLC0415

        flushed = bool(logfire.force_flush(timeout_millis=timeout_millis)) or flushed
    except Exception:
        pass
    try:
        from opentelemetry import metrics, trace  # noqa: PLC0415

        flushed = (
            _force_flush_provider(
                trace.get_tracer_provider(),
                timeout_millis=timeout_millis,
            )
            or flushed
        )
        flushed = (
            _force_flush_provider(
                metrics.get_meter_provider(),
                timeout_millis=timeout_millis,
            )
            or flushed
        )
    except Exception:
        pass
    try:
        from opentelemetry import _logs  # noqa: PLC0415

        flushed = (
            _force_flush_provider(
                _logs.get_logger_provider(),
                timeout_millis=timeout_millis,
            )
            or flushed
        )
    except Exception:
        pass
    return flushed


def _force_flush_provider(provider: object, *, timeout_millis: int) -> bool:
    force_flush = getattr(provider, "force_flush", None)
    if not callable(force_flush):
        return False
    try:
        return bool(force_flush(timeout_millis=timeout_millis))
    except TypeError:
        return bool(force_flush())


def _span_context_ids(span: Any) -> tuple[str | None, str | None]:
    if span is None:
        return None, None
    try:
        context = span.get_span_context()
        trace_id = int(getattr(context, "trace_id", 0))
        span_id = int(getattr(context, "span_id", 0))
    except Exception:
        return None, None
    return (
        f"{trace_id:032x}" if trace_id else None,
        f"{span_id:016x}" if span_id else None,
    )


def span_set_attributes(span: Any, attributes: dict[str, object | None]) -> None:
    if span is None:
        return
    if isinstance(span, TrapoSpanHandle):
        span.set_attributes(attributes)
        return
    safe_attributes = _safe_attributes(
        {key: value for key, value in attributes.items() if value is not None}
    )
    for key, value in safe_attributes.items():
        try:
            span.set_attribute(key, value)
        except Exception:
            continue


def mark_span_error(span: Any, exc: BaseException) -> None:
    if span is None:
        return
    if isinstance(span, TrapoSpanHandle):
        span.record_exception(exc)
        span = span.otel_span
        if span is None:
            return
    try:
        span.record_exception(exc)
    except Exception:
        pass
    try:
        from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:
        pass


# Telemetry dimensions are explicit keyword-only fields for readable call sites.
def record_operation_event_telemetry(  # noqa: PLR0913
    *,
    phase: str,
    severity: str,
    message: str,
    file_hash: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    event_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    attrs: dict[str, object] = {
        "phase": phase,
        "severity": severity,
    }
    if file_hash:
        attrs["file_hash"] = file_hash
    if provider:
        attrs["provider"] = provider
    if model:
        attrs["model"] = model
    if event_id is not None:
        attrs["operation_event_id"] = event_id
    for key in (
        "agent_id",
        "agent_role",
        "endpoint",
        "status",
        "status_text",
        "duration_ms",
        "chunk_id",
        "analysis_run_id",
    ):
        if details and key in details and details[key] is not None:
            attrs[key] = details[key]
    log_structured(message, level=severity, **attrs)
    instruments = _STATE.metric_instruments
    if instruments is not None:
        instruments.operation_events.add(1, attributes=_metric_attributes(attrs))


def record_command_telemetry(
    *,
    command_name: str,
    status: str,
    duration_ms: float,
    attributes: dict[str, object] | None = None,
) -> None:
    log_attrs: dict[str, object] = {
        "phase": "command",
        "command": command_name,
        "status": status,
        "duration_ms": duration_ms,
    }
    if attributes:
        log_attrs.update(attributes)
    log_structured(
        f"Command {status}: {command_name}",
        level="error" if status == "error" else "info",
        **log_attrs,
    )
    instruments = _STATE.metric_instruments
    if instruments is None:
        return
    metric_attrs = _metric_attributes(
        {
            "command": command_name,
            "status": status,
        }
    )
    instruments.command_runs.add(1, attributes=metric_attrs)
    instruments.command_duration_ms.record(duration_ms, attributes=metric_attrs)


# Telemetry dimensions are explicit keyword-only fields for readable call sites.
def record_provider_call_telemetry(  # noqa: PLR0913
    *,
    endpoint: str,
    provider: str | None,
    model: str | None,
    status: str,
    duration_ms: float | None,
    details: dict[str, Any] | None = None,
) -> None:
    attrs: dict[str, object] = {
        "endpoint": endpoint,
        "status": status,
    }
    if provider:
        attrs["provider"] = provider
    if model:
        attrs["model"] = model
    if details:
        for key in ("phase", "agent_role"):
            if key in details and details[key] is not None:
                attrs[key] = details[key]
    log_structured(
        f"Provider call {status}: {endpoint}",
        level="error" if status == "error" else "info",
        **attrs,
    )
    instruments = _STATE.metric_instruments
    if instruments is None:
        return
    metric_attrs = _metric_attributes(attrs)
    instruments.provider_calls.add(1, attributes=metric_attrs)
    if status == "error":
        instruments.provider_errors.add(1, attributes=metric_attrs)
    if duration_ms is not None:
        instruments.provider_duration_ms.record(duration_ms, attributes=metric_attrs)
    estimated_tokens = _estimated_tokens(details)
    if estimated_tokens is not None:
        instruments.provider_estimated_tokens.record(
            estimated_tokens, attributes=metric_attrs
        )


def _settings(
    config: RuntimeConfig | ObservabilitySettings | None,
) -> ObservabilitySettings:
    if isinstance(config, ObservabilitySettings):
        return config
    if config is not None:
        return ObservabilitySettings.from_config(config)
    return ObservabilitySettings.from_env()


def _disabled_settings(settings: ObservabilitySettings) -> ObservabilitySettings:
    return ObservabilitySettings(
        enabled=False,
        exporter="off",
        endpoint=settings.endpoint,
        service_name=settings.service_name,
        console=settings.console,
    )


def _warn_once(warning_sink: Callable[[str], None] | None, message: str) -> None:
    if warning_sink is not None:
        warning_sink(message)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _otel_exporter(value: str) -> OtelExporter:
    normalized = value.strip().lower()
    return OTEL_EXPORTER_ALIASES.get(normalized, DEFAULT_OTEL_EXPORTER)


def _configure_direct_otel(
    settings: ObservabilitySettings,
    *,
    warning_sink: Callable[[str], None] | None,
) -> None:
    if settings.exporter == "otlp":
        os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.endpoint)
        os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            _signal_endpoint(settings.endpoint, "traces"),
        )
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
            _signal_endpoint(settings.endpoint, "logs"),
        )
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
            _signal_endpoint(settings.endpoint, "metrics"),
        )
    _configure_otel_traces(settings, warning_sink=warning_sink)
    _configure_otel_logs(settings, warning_sink=warning_sink)
    _configure_otel_metrics(settings, warning_sink=warning_sink)
    _instrument_httpx(warning_sink=warning_sink)


def _configure_logfire(
    settings: ObservabilitySettings,
    *,
    warning_sink: Callable[[str], None] | None,
) -> None:
    # Logfire is optional and only needed for the explicit Logfire exporter.
    import logfire  # noqa: PLC0415

    send_to_logfire: SendToLogfire = "if-token-present"
    logfire.configure(
        local=False,
        send_to_logfire=send_to_logfire,
        service_name=settings.service_name,
        console=None if settings.console else False,
        metrics=False,
    )
    _instrument_logfire_httpx(logfire, warning_sink=warning_sink)


def _instrument_httpx(*, warning_sink: Callable[[str], None] | None) -> None:
    if _STATE.httpx_instrumented:
        return
    try:
        from opentelemetry.instrumentation.httpx import (  # noqa: PLC0415
            HTTPXClientInstrumentor,
        )

        HTTPXClientInstrumentor().instrument()
        _STATE.httpx_instrumented = True
    except Exception as exc:
        _warn_once(
            warning_sink, f"HTTPX OpenTelemetry instrumentation is disabled: {exc}"
        )


def _instrument_logfire_httpx(
    logfire_module: Any,
    *,
    warning_sink: Callable[[str], None] | None,
) -> None:
    try:
        logfire_module.instrument_httpx(
            capture_all=False,
            capture_headers=False,
            capture_request_body=False,
            capture_response_body=False,
        )
    except Exception as exc:
        _warn_once(
            warning_sink, f"HTTPX OpenTelemetry instrumentation is disabled: {exc}"
        )


def _configure_otel_traces(
    settings: ObservabilitySettings,
    *,
    warning_sink: Callable[[str], None] | None,
) -> None:
    if _STATE.trace_configured:
        return
    try:
        # OpenTelemetry SDK imports are optional and only used when telemetry is enabled.
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import (  # noqa: PLC0415
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        provider = trace.get_tracer_provider()
        if _is_proxy_provider(provider):
            exporter = (
                ConsoleSpanExporter()
                if settings.exporter == "console"
                else OTLPSpanExporter(
                    endpoint=_signal_endpoint(settings.endpoint, "traces"),
                    timeout=2.0,
                )
            )
            provider = TracerProvider(resource=_otel_resource(settings, Resource))
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
        _STATE.trace_configured = True
    except Exception as exc:
        _warn_once(warning_sink, f"OpenTelemetry trace export is disabled: {exc}")


def _configure_otel_logs(
    settings: ObservabilitySettings,
    *,
    warning_sink: Callable[[str], None] | None,
) -> None:
    if _STATE.otel_log_handler is not None:
        return
    try:
        # OpenTelemetry SDK imports are optional and only used for OTLP export.
        from opentelemetry import _logs  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (  # noqa: PLC0415
            OTLPLogExporter,
        )
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler  # noqa: PLC0415
        from opentelemetry.sdk._logs.export import (  # noqa: PLC0415
            BatchLogRecordProcessor,
            ConsoleLogExporter,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415

        provider = _logs.get_logger_provider()
        if _is_proxy_provider(provider):
            exporter = (
                ConsoleLogExporter()
                if settings.exporter == "console"
                else OTLPLogExporter(
                    endpoint=_signal_endpoint(settings.endpoint, "logs"),
                    timeout=2.0,
                )
            )
            provider = LoggerProvider(resource=_otel_resource(settings, Resource))
            provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
            _logs.set_logger_provider(provider)
        handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
        logger = logging.getLogger("trapo")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        _STATE.otel_log_handler = handler
    except Exception as exc:
        _warn_once(warning_sink, f"OpenTelemetry log export is disabled: {exc}")


def _configure_otel_metrics(
    settings: ObservabilitySettings,
    *,
    warning_sink: Callable[[str], None] | None,
) -> None:
    if _STATE.metric_instruments is not None:
        return
    try:
        # OpenTelemetry SDK imports are optional and only used for OTLP export.
        from opentelemetry import metrics  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415
        from opentelemetry.sdk.metrics.export import (  # noqa: PLC0415
            ConsoleMetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415

        provider = metrics.get_meter_provider()
        if _is_proxy_provider(provider):
            exporter = (
                ConsoleMetricExporter()
                if settings.exporter == "console"
                else OTLPMetricExporter(
                    endpoint=_signal_endpoint(settings.endpoint, "metrics"),
                    timeout=2.0,
                )
            )
            reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=5000,
                export_timeout_millis=2000,
            )
            provider = MeterProvider(
                metric_readers=[reader],
                resource=_otel_resource(settings, Resource),
            )
            metrics.set_meter_provider(provider)
        meter = metrics.get_meter("trapo")
        _STATE.metric_instruments = MetricInstruments(
            operation_events=meter.create_counter(
                "trapo_operation_events_total",
                unit="1",
                description="Operation events recorded by Trapo.",
            ),
            provider_calls=meter.create_counter(
                "trapo_provider_calls_total",
                unit="1",
                description="Outgoing provider calls made by Trapo.",
            ),
            provider_errors=meter.create_counter(
                "trapo_provider_errors_total",
                unit="1",
                description="Outgoing provider calls that failed.",
            ),
            command_runs=meter.create_counter(
                "trapo_command_runs_total",
                unit="1",
                description="CLI command executions by command and status.",
            ),
            command_duration_ms=meter.create_histogram(
                "trapo_command_duration_ms",
                unit="ms",
                description="CLI command execution duration.",
            ),
            provider_duration_ms=meter.create_histogram(
                "trapo_provider_call_duration_ms",
                unit="ms",
                description="Outgoing provider call duration.",
            ),
            provider_estimated_tokens=meter.create_histogram(
                "trapo_provider_estimated_tokens",
                unit="tokens",
                description="Estimated tokens for outgoing provider calls.",
            ),
        )
    except Exception as exc:
        _warn_once(warning_sink, f"OpenTelemetry metric export is disabled: {exc}")


def _is_proxy_provider(provider: object) -> bool:
    module = provider.__class__.__module__
    name = provider.__class__.__name__
    if module.startswith("logfire._internal."):
        return name in {"ProxyLoggerProvider", "ProxyMeterProvider"}
    if not module.startswith("opentelemetry."):
        return False
    return name in {
        "ProxyTracerProvider",
        "_ProxyTracerProvider",
        "ProxyLoggerProvider",
        "_ProxyLoggerProvider",
        "ProxyMeterProvider",
        "_ProxyMeterProvider",
    }


def _otlp_endpoint_available(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    host = parsed.hostname
    if host is None:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _signal_endpoint(
    endpoint: str, signal: Literal["traces", "logs", "metrics"]
) -> str:
    base = endpoint.rstrip("/")
    if base.endswith(f"/v1/{signal}"):
        return base
    if base.endswith("/v1"):
        return f"{base}/{signal}"
    return f"{base}/v1/{signal}"


def _otel_resource(settings: ObservabilitySettings, resource_type: Any) -> Any:
    return resource_type.create({"service.name": settings.service_name})


def _log_extra(attributes: dict[str, object]) -> dict[str, object]:
    return {
        f"trapo.{key}": value for key, value in _safe_attributes(attributes).items()
    }


def _metric_attributes(
    attributes: dict[str, object],
) -> dict[str, str | bool | int | float]:
    return _safe_attributes(attributes)


def _safe_attributes(
    attributes: dict[str, object],
) -> dict[str, str | bool | int | float]:
    safe: dict[str, str | bool | int | float] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        normalized_key = key.replace("_", ".")
        if isinstance(value, str | bool | int | float):
            safe[normalized_key] = value
        else:
            safe[normalized_key] = str(value)
    return safe


def _log_level(level: str) -> int:
    normalized = level.strip().lower()
    return LOG_LEVELS.get(normalized, logging.INFO)


def _estimated_tokens(details: dict[str, Any] | None) -> int | None:
    if not details:
        return None
    for key in ("estimated_tokens", "estimated_input_tokens"):
        value = details.get(key)
        if isinstance(value, int | float):
            return int(value)
    return None
