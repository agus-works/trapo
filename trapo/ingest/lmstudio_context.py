from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import quote

import httpx

from trapo.ingest.lmstudio_urls import lmstudio_native_base_url
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    DEFAULT_LMSTUDIO_MODEL,
)


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


class _HttpResponse(Protocol):
    def json(self) -> Any: ...

    def raise_for_status(self) -> None: ...


class _HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
    ) -> _HttpResponse: ...

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> _HttpResponse: ...

    def close(self) -> None: ...


def ensure_lmstudio_max_context(  # noqa: PLR0911, PLR0913
    *,
    base_url: str = DEFAULT_LMSTUDIO_BASE_URL,
    model: str = DEFAULT_LMSTUDIO_MODEL,
    timeout_seconds: float = 30.0,
    enabled: bool = True,
    log: Callable[[str], None] | None = None,
    http_client: _HttpClient | None = None,
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
    client: _HttpClient = http_client or cast(
        _HttpClient, httpx.Client(timeout=timeout_seconds)
    )
    try:
        models_payload = _read_models_payload(client, native_base_url)
        _unload_other_loaded_models(client, native_base_url, models_payload, model, log)
        model_info = _model_from_v1_list(models_payload, model)
        if model_info is None:
            model_info = _read_model_detail(client, native_base_url, model)
        max_context = _int_or_none(model_info.get("max_context_length"))
        loaded_context = _loaded_context_tokens(model_info)
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
        load_response = _load_model_at_context(
            client, native_base_url, model, max_context
        )
        applied_context = _loaded_context_tokens(load_response) or max_context
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


def _read_model_info(
    client: _HttpClient, native_base_url: str, model: str
) -> dict[str, Any]:
    data = _read_models_payload(client, native_base_url)
    match = _model_from_v1_list(data, model)
    if match is not None:
        return match
    return _read_model_detail(client, native_base_url, model)


def _read_models_payload(client: _HttpClient, native_base_url: str) -> object:
    response = client.get(
        f"{native_base_url}/api/v1/models",
        headers=_headers(),
    )
    response.raise_for_status()
    return response.json()


def _read_model_detail(
    client: _HttpClient, native_base_url: str, model: str
) -> dict[str, Any]:
    response = client.get(
        f"{native_base_url}/api/v0/models/{quote(model, safe='')}",
        headers=_headers(),
    )
    response.raise_for_status()
    fallback = response.json()
    return fallback if isinstance(fallback, dict) else {}


def _model_from_v1_list(data: object, model: str) -> dict[str, Any] | None:
    match: dict[str, Any] | None = None
    if not isinstance(data, dict):
        return match
    models = data.get("models")
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            keys = {item.get("key"), item.get("selected_variant")}
            variants = item.get("variants")
            if isinstance(variants, list):
                keys.update(variant for variant in variants if isinstance(variant, str))
            if model in keys:
                match = item
                break
    return match


def _load_model_at_context(
    client: _HttpClient,
    native_base_url: str,
    model: str,
    context_tokens: int,
) -> dict[str, Any]:
    response = client.post(
        f"{native_base_url}/api/v1/models/load",
        headers=_headers(),
        json={
            "model": model,
            "context_length": context_tokens,
            "echo_load_config": True,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _unload_other_loaded_models(
    client: _HttpClient,
    native_base_url: str,
    data: object,
    target_model: str,
    log: Callable[[str], None] | None,
) -> None:
    for loaded_model in _other_loaded_models(data, target_model):
        try:
            _unload_model(client, native_base_url, loaded_model)
        except Exception as exc:
            _log(
                log,
                "LM Studio other-model unload failed: "
                f"model={loaded_model} error={_error_detail(exc)}",
            )
        else:
            _log(log, f"LM Studio unloaded other active model: model={loaded_model}")


def _other_loaded_models(data: object, target_model: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    models = data.get("models")
    if not isinstance(models, list):
        return []
    loaded: list[str] = []
    for item in models:
        if not isinstance(item, dict) or not _is_loaded_model(item):
            continue
        keys = _model_keys(item)
        if target_model in keys:
            continue
        model_key = _model_key(item)
        if model_key is not None:
            loaded.append(model_key)
    return loaded


def _is_loaded_model(item: dict[str, Any]) -> bool:
    loaded_instances = item.get("loaded_instances")
    if isinstance(loaded_instances, list) and loaded_instances:
        return True
    state = item.get("state") or item.get("status")
    return isinstance(state, str) and state.casefold() == "loaded"


def _model_key(item: dict[str, Any]) -> str | None:
    key = item.get("key") or item.get("selected_variant")
    return key if isinstance(key, str) and key else None


def _model_keys(item: dict[str, Any]) -> set[str]:
    keys = {
        value
        for value in (item.get("key"), item.get("selected_variant"))
        if isinstance(value, str)
    }
    variants = item.get("variants")
    if isinstance(variants, list):
        keys.update(variant for variant in variants if isinstance(variant, str))
    return keys


def _unload_model(
    client: _HttpClient,
    native_base_url: str,
    model: str,
) -> dict[str, Any]:
    response = client.post(
        f"{native_base_url}/api/v1/models/unload",
        headers=_headers(),
        json={"model": model},
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _loaded_context_tokens(value: object) -> int | None:
    values = _loaded_context_values(value)
    return max(values) if values else None


def _loaded_context_values(value: object) -> list[int]:
    if isinstance(value, dict):
        values = []
        for key, child in value.items():
            if key in {"context_length", "n_ctx"}:
                candidate = _int_or_none(child)
                if candidate is not None:
                    values.append(candidate)
            values.extend(_loaded_context_values(child))
        return values
    if isinstance(value, list):
        return [item for child in value for item in _loaded_context_values(child)]
    return []


def _headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": "Bearer lm-studio"}


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, bool):
        result = None
    elif isinstance(value, int | float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            result = None
    return result


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
