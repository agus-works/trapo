from __future__ import annotations

from trapo.document_markdown import (
    INFINITY_MARKDOWN_ENGINE,
    LMSTUDIO_MARKDOWN_ENGINE,
    MARKITDOWN_CU_MARKDOWN_ENGINE,
    MARKITDOWN_MARKDOWN_ENGINE,
)
from trapo.ingest.options import IngestOptions


def requested_markdown_engines(options: IngestOptions) -> list[str]:
    if not options.page_markdown:
        return []
    raw_engines = [
        part.strip().lower() for part in options.page_markdown_engines.split(",")
    ]
    engines: list[str] = []
    for engine in raw_engines:
        normalized = _normalize_markdown_engine(engine)
        if normalized == "all":
            _append_all_markdown_engines(engines)
            continue
        if normalized and normalized not in engines:
            engines.append(normalized)
    return engines or [LMSTUDIO_MARKDOWN_ENGINE, MARKITDOWN_MARKDOWN_ENGINE]


def _append_all_markdown_engines(engines: list[str]) -> None:
    for engine in (
        LMSTUDIO_MARKDOWN_ENGINE,
        INFINITY_MARKDOWN_ENGINE,
        MARKITDOWN_MARKDOWN_ENGINE,
        MARKITDOWN_CU_MARKDOWN_ENGINE,
    ):
        if engine not in engines:
            engines.append(engine)


def _normalize_markdown_engine(value: str) -> str:
    aliases = {
        "lmstudio": LMSTUDIO_MARKDOWN_ENGINE,
        "lm-studio": LMSTUDIO_MARKDOWN_ENGINE,
        "local-lmstudio": LMSTUDIO_MARKDOWN_ENGINE,
        LMSTUDIO_MARKDOWN_ENGINE: LMSTUDIO_MARKDOWN_ENGINE,
        "infinity": INFINITY_MARKDOWN_ENGINE,
        "infinity-parser2": INFINITY_MARKDOWN_ENGINE,
        "local-infinity": INFINITY_MARKDOWN_ENGINE,
        "local-infinity-parser2": INFINITY_MARKDOWN_ENGINE,
        INFINITY_MARKDOWN_ENGINE: INFINITY_MARKDOWN_ENGINE,
        "markitdown": MARKITDOWN_MARKDOWN_ENGINE,
        "mark-it-down": MARKITDOWN_MARKDOWN_ENGINE,
        MARKITDOWN_MARKDOWN_ENGINE: MARKITDOWN_MARKDOWN_ENGINE,
        "cu": MARKITDOWN_CU_MARKDOWN_ENGINE,
        "content-understanding": MARKITDOWN_CU_MARKDOWN_ENGINE,
        "markitdown-cu": MARKITDOWN_CU_MARKDOWN_ENGINE,
        MARKITDOWN_CU_MARKDOWN_ENGINE: MARKITDOWN_CU_MARKDOWN_ENGINE,
        "all": "all",
    }
    return aliases.get(value, "")
