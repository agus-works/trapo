from __future__ import annotations

from collections.abc import Callable

from trapo.ingest.lmstudio_native_models import (
    LoadedLmStudioModel,
    LmStudioNativeClient,
    _error_detail,
    _is_loaded_model,
    _loaded_model_instances,
    _log,
    _model_key,
    _model_keys,
    _models_from_payload,
    _unload_model,
    read_lmstudio_models_payload,
)


def unload_lmstudio_model(
    client: LmStudioNativeClient,
    native_base_url: str,
    model: str,
    log: Callable[[str], None] | None = None,
) -> None:
    data = read_lmstudio_models_payload(client, native_base_url)
    for loaded_model in _target_loaded_models(data, model):
        try:
            _unload_model(client, native_base_url, loaded_model)
        except Exception as exc:
            _log(
                log,
                "LM Studio target unload failed: "
                f"model={loaded_model.model} error={_error_detail(exc)}",
            )
        else:
            _log(log, f"LM Studio unloaded active model: model={loaded_model.model}")


def _target_loaded_models(data: object, target_model: str) -> list[LoadedLmStudioModel]:
    if not isinstance(data, dict):
        return []
    models = _models_from_payload(data)
    if not isinstance(models, list):
        return []
    loaded: list[LoadedLmStudioModel] = []
    for item in models:
        if not isinstance(item, dict) or not _is_loaded_model(item):
            continue
        if target_model not in _model_keys(item):
            continue
        model_key = _model_key(item)
        if model_key is not None:
            loaded.extend(_loaded_model_instances(item, model_key))
    return loaded
