from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None


DEFAULT_DB_PATH = "trapo.duckdb"
DEFAULT_SERVE_DB_PATH = "trapo.duckdb"
DEFAULT_SERVE_HOST = "0.0.0.0"
DEFAULT_SERVE_PORT = 8765
DEFAULT_SOURCE_ROOT = "."
DEFAULT_OCR_PROVIDER = "local-docling"
DEFAULT_OCR_MODEL = "docling"
DEFAULT_OTEL_ENABLED = True
DEFAULT_OTEL_EXPORTER = "otlp"
DEFAULT_OTEL_ENDPOINT = "http://localhost:4318"
DEFAULT_OTEL_SERVICE_NAME = "trapo"
DEFAULT_OTEL_CONSOLE = False

OtelExporterName = Literal["off", "otlp", "console", "logfire"]
OTEL_EXPORTER_ALIASES: dict[str, OtelExporterName] = {
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


def load_local_env() -> None:
    """Load repo-local config without overriding real environment values."""
    if _load_dotenv is None:
        return
    env_path = Path.cwd() / ".env.local"
    if env_path.exists():
        _load_dotenv(env_path, override=False)


@dataclass(frozen=True)
class RuntimeConfig:
    db_path: str = DEFAULT_DB_PATH
    source_root: str = DEFAULT_SOURCE_ROOT
    ocr_provider: str = DEFAULT_OCR_PROVIDER
    ocr_model: str = DEFAULT_OCR_MODEL
    otel_enabled: bool = DEFAULT_OTEL_ENABLED
    otel_exporter: OtelExporterName = DEFAULT_OTEL_EXPORTER
    otel_endpoint: str = DEFAULT_OTEL_ENDPOINT
    otel_service_name: str = DEFAULT_OTEL_SERVICE_NAME
    otel_console: bool = DEFAULT_OTEL_CONSOLE

    @classmethod
    def from_env(
        cls,
        *,
        db_path: str = DEFAULT_DB_PATH,
        source_root: str | None = None,
    ) -> "RuntimeConfig":
        load_local_env()
        return cls(
            db_path=db_path,
            source_root=source_root
            or os.getenv("TRAPO_SOURCE_ROOT", DEFAULT_SOURCE_ROOT),
            otel_enabled=_env_bool("TRAPO_OTEL_ENABLED", DEFAULT_OTEL_ENABLED),
            otel_exporter=_otel_exporter_name(
                os.getenv("TRAPO_OTEL_EXPORTER", DEFAULT_OTEL_EXPORTER)
            ),
            otel_endpoint=os.getenv("TRAPO_OTEL_ENDPOINT", DEFAULT_OTEL_ENDPOINT),
            otel_service_name=os.getenv(
                "TRAPO_OTEL_SERVICE_NAME", DEFAULT_OTEL_SERVICE_NAME
            ),
            otel_console=_env_bool("TRAPO_OTEL_CONSOLE", DEFAULT_OTEL_CONSOLE),
        )


def _otel_exporter_name(value: str) -> OtelExporterName:
    normalized = value.strip().lower()
    try:
        return OTEL_EXPORTER_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(
            "OTel exporter must be off, otlp, console, or logfire."
        ) from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
