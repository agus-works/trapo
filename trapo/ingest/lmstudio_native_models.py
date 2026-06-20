from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

from trapo.ingest.lmstudio_supported_models import (
    supported_lmstudio_model_max_context,
)


class LmStudioNativeResponse(Protocol):
    def json(self) -> Any: ...

    def raise_for_status(self) -> None: ...


class LmStudioNativeClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
    ) -> LmStudioNativeResponse: ...

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> LmStudioNativeResponse: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class LoadedLmStudioModel:
    model: str
    instance_id: str | None = None


def read_lmstudio_models_payload(
    client: LmStudioNativeClient, native_base_url: str
) -> object:
    response = client.get(
        f"{native_base_url}/api/v1/models",
        headers=lmstudio_native_headers(),
    )
    response.raise_for_status()
    return response.json()


def read_lmstudio_model_detail(
    client: LmStudioNativeClient, native_base_url: str, model: str
) -> dict[str, Any]:
    response = client.get(
        f"{native_base_url}/api/v0/models/{quote(model, safe='')}",
        headers=lmstudio_native_headers(),
    )
    response.raise_for_status()
    fallback = response.json()
    return fallback if isinstance(fallback, dict) else {}


def model_from_lmstudio_list(data: object, model: str) -> dict[str, Any] | None:
    match: dict[str, Any] | None = None
    if not isinstance(data, dict):
        return match
    models = _models_from_payload(data)
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, dict):
                continue
            keys = {item.get("key"), item.get("id"), item.get("selected_variant")}
            variants = item.get("variants")
            if isinstance(variants, list):
                keys.update(variant for variant in variants if isinstance(variant, str))
            if model in keys:
                match = item
                break
    return match


def resolved_lmstudio_max_context_tokens(
    model: str,
    model_info: dict[str, Any],
) -> int | None:
    advertised = int_or_none(model_info.get("max_context_length"))
    supported = supported_lmstudio_model_max_context(model)
    candidates = [value for value in (advertised, supported) if value is not None]
    return max(candidates) if candidates else None


def load_lmstudio_model_at_context(
    client: LmStudioNativeClient,
    native_base_url: str,
    model: str,
    context_tokens: int,
) -> dict[str, Any]:
    response = client.post(
        f"{native_base_url}/api/v1/models/load",
        headers=lmstudio_native_headers(),
        json={
            "model": model,
            "context_length": context_tokens,
            "echo_load_config": True,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def unload_other_lmstudio_models(
    client: LmStudioNativeClient,
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
                f"model={loaded_model.model} error={_error_detail(exc)}",
            )
        else:
            _log(
                log,
                f"LM Studio unloaded other active model: model={loaded_model.model}",
            )


def loaded_context_tokens(value: object) -> int | None:
    values = _loaded_context_values(value)
    return max(values) if values else None


def int_or_none(value: object) -> int | None:
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


def lmstudio_native_headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "Authorization": "Bearer lm-studio"}


def _models_from_payload(data: dict[str, Any]) -> object:
    models = data.get("models")
    if isinstance(models, list):
        return models
    return data.get("data")


def _other_loaded_models(data: object, target_model: str) -> list[LoadedLmStudioModel]:
    if not isinstance(data, dict):
        return []
    models = _models_from_payload(data)
    if not isinstance(models, list):
        return []
    loaded: list[LoadedLmStudioModel] = []
    for item in models:
        if not isinstance(item, dict) or not _is_loaded_model(item):
            continue
        keys = _model_keys(item)
        if target_model in keys:
            continue
        model_key = _model_key(item)
        if model_key is not None:
            loaded.extend(_loaded_model_instances(item, model_key))
    return loaded


def _loaded_model_instances(
    item: dict[str, Any], model_key: str
) -> list[LoadedLmStudioModel]:
    instances = item.get("loaded_instances")
    loaded: list[LoadedLmStudioModel] = []
    if isinstance(instances, list):
        for instance in instances:
            instance_id = _instance_id(instance)
            loaded.append(LoadedLmStudioModel(model=model_key, instance_id=instance_id))
    return loaded or [LoadedLmStudioModel(model=model_key)]


def _instance_id(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("instance_id", "id", "identifier"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _is_loaded_model(item: dict[str, Any]) -> bool:
    loaded_instances = item.get("loaded_instances")
    if isinstance(loaded_instances, list) and loaded_instances:
        return True
    state = item.get("state") or item.get("status")
    return isinstance(state, str) and state.casefold() == "loaded"


def _model_key(item: dict[str, Any]) -> str | None:
    key = item.get("key") or item.get("id") or item.get("selected_variant")
    return key if isinstance(key, str) and key else None


def _model_keys(item: dict[str, Any]) -> set[str]:
    keys = {
        value
        for value in (item.get("key"), item.get("id"), item.get("selected_variant"))
        if isinstance(value, str)
    }
    variants = item.get("variants")
    if isinstance(variants, list):
        keys.update(variant for variant in variants if isinstance(variant, str))
    return keys


def _unload_model(
    client: LmStudioNativeClient,
    native_base_url: str,
    loaded_model: LoadedLmStudioModel,
) -> dict[str, Any]:
    payload = (
        {"instance_id": loaded_model.instance_id}
        if loaded_model.instance_id
        else {"model": loaded_model.model}
    )
    response = client.post(
        f"{native_base_url}/api/v1/models/unload",
        headers=lmstudio_native_headers(),
        json=payload,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _loaded_context_values(value: object) -> list[int]:
    if isinstance(value, dict):
        values = []
        for key, child in value.items():
            if key in {"context_length", "n_ctx"}:
                candidate = int_or_none(child)
                if candidate is not None:
                    values.append(candidate)
            values.extend(_loaded_context_values(child))
        return values
    if isinstance(value, list):
        return [item for child in value for item in _loaded_context_values(child)]
    return []


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)


def _error_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return f"{exc}; response={text[:1000]}"
    return str(exc)
