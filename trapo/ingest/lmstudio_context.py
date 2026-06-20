from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import httpx

from trapo.ingest.lmstudio_urls import lmstudio_native_base_url
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    DEFAULT_LMSTUDIO_MODEL,
)
from trapo.ingest.lmstudio_native_models import (
    LmStudioNativeClient,
    load_lmstudio_model_at_context,
    loaded_context_tokens,
    read_lmstudio_model_detail,
    read_lmstudio_models_payload,
    model_from_lmstudio_list,
    resolved_lmstudio_max_context_tokens,
    unload_other_lmstudio_models,
)
from trapo.ingest.lmstudio_unload import unload_lmstudio_model


@dataclass(frozen=True)
class LmStudioContextInfo:
    model: str
    base_url: str
    native_base_url: str
    max_context_tokens: int | None = None
    loaded_context_tokens: int | None = None
    applied_context_tokens: int | None = None
    load_attempted: bool = False
    load_status: str = "not_attempted"
    error: str | None = None

    @property
    def effective_context_tokens(self) -> int | None:
        return (
            self.applied_context_tokens
            or self.loaded_context_tokens
            or self.max_context_tokens
        )


def resolve_markdown_max_tokens(
    *,
    requested_tokens: int,
    context_info: LmStudioContextInfo | None,
    context_reserve_tokens: int = 1024,
    minimum_output_tokens: int = 256,
    auto_requested_tokens: int = DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
) -> int:
    """Resolve a safe markdown max token budget from discovered LM Studio context."""
    context_tokens = context_info.effective_context_tokens if context_info else None
    resolved_tokens = requested_tokens
    if requested_tokens <= 0:
        resolved_tokens = 0
    elif context_tokens is not None and context_tokens > 0:
        if context_tokens <= context_reserve_tokens:
            context_budget = max(minimum_output_tokens, context_tokens)
        else:
            context_budget = max(
                minimum_output_tokens, context_tokens - context_reserve_tokens
            )
        if requested_tokens == auto_requested_tokens:
            resolved_tokens = context_budget
        else:
            resolved_tokens = min(requested_tokens, context_budget)
    return resolved_tokens


def ensure_lmstudio_max_context(  # noqa: PLR0911, PLR0913
    *,
    base_url: str = DEFAULT_LMSTUDIO_BASE_URL,
    model: str = DEFAULT_LMSTUDIO_MODEL,
    timeout_seconds: float = 30.0,
    enabled: bool = True,
    log: Callable[[str], None] | None = None,
    http_client: LmStudioNativeClient | None = None,
) -> LmStudioContextInfo:
    """Best-effort LM Studio native REST preflight for maximum model context."""
    native_base_url = lmstudio_native_base_url(base_url)
    if not enabled:
        return LmStudioContextInfo(
            model=model,
            base_url=base_url,
            native_base_url=native_base_url,
            load_status="disabled",
        )
    owns_client = http_client is None
    client: LmStudioNativeClient = http_client or cast(
        LmStudioNativeClient, httpx.Client(timeout=timeout_seconds)
    )
    try:
        models_payload = read_lmstudio_models_payload(client, native_base_url)
        unload_other_lmstudio_models(
            client, native_base_url, models_payload, model, log
        )
        model_info = model_from_lmstudio_list(models_payload, model)
        if model_info is None:
            model_info = read_lmstudio_model_detail(client, native_base_url, model)
        max_context = resolved_lmstudio_max_context_tokens(model, model_info)
        loaded_context = loaded_context_tokens(model_info)
        if max_context is None:
            info = LmStudioContextInfo(
                model=model,
                base_url=base_url,
                native_base_url=native_base_url,
                loaded_context_tokens=loaded_context,
                load_status="max_context_unknown",
            )
            _log(log, _summary(info))
            return info
        if loaded_context is not None and loaded_context >= max_context:
            info = LmStudioContextInfo(
                model=model,
                base_url=base_url,
                native_base_url=native_base_url,
                max_context_tokens=max_context,
                loaded_context_tokens=loaded_context,
                load_status="already_max",
            )
            _log(log, _summary(info))
            return info
        if loaded_context is not None:
            unload_lmstudio_model(client, native_base_url, model, log)
        load_response = load_lmstudio_model_at_context(
            client, native_base_url, model, max_context
        )
        applied_context = loaded_context_tokens(load_response) or max_context
        info = LmStudioContextInfo(
            model=model,
            base_url=base_url,
            native_base_url=native_base_url,
            max_context_tokens=max_context,
            loaded_context_tokens=loaded_context,
            applied_context_tokens=applied_context,
            load_attempted=True,
            load_status="loaded_max",
        )
        _log(log, _summary(info))
        return info
    except Exception as exc:
        info = LmStudioContextInfo(
            model=model,
            base_url=base_url,
            native_base_url=native_base_url,
            load_status="unavailable",
            error=_error_detail(exc),
        )
        _log(log, _summary(info))
        return info
    finally:
        if owns_client:
            client.close()


def _error_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return f"{exc}; response={text[:1000]}"
    return str(exc)


def _summary(info: LmStudioContextInfo) -> str:
    parts = [
        "LM Studio context preflight:",
        f"model={info.model}",
        f"status={info.load_status}",
        f"max_context={info.max_context_tokens or 'unknown'}",
        f"loaded_context={info.loaded_context_tokens or 'unknown'}",
        f"applied_context={info.applied_context_tokens or 'unknown'}",
    ]
    if info.error:
        parts.append(f"error={info.error}")
    return " ".join(parts)


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)
