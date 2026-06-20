from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_LMSTUDIO_ANNOTATION_ENGINES = (
    "lmstudio",
    "lmstudio_strict",
    "lmstudio_recall",
)
SUPPORTED_LMSTUDIO_MARKDOWN_ENGINES = (
    "lmstudio_markdown",
    "markitdown:lmstudio_ocr",
    "infinity_markdown:lmstudio",
)


@dataclass(frozen=True)
class LmStudioSupportedModel:
    model: str
    max_context_tokens: int
    vision: bool = True
    notes: str = ""


SUPPORTED_LMSTUDIO_VISION_MODELS: tuple[LmStudioSupportedModel, ...] = (
    LmStudioSupportedModel("google/gemma-4-26b-a4b-qat", 262_144),
    LmStudioSupportedModel("qwen/qwen3.5-27b", 262_144),
    LmStudioSupportedModel("qwen/qwen3.5-35b-a3b", 262_144),
    LmStudioSupportedModel("nvidia/nemotron-3-nano-omni", 262_144),
    LmStudioSupportedModel("qwen/qwen3-vl-8b", 262_144),
    LmStudioSupportedModel("infinity-parser2-flash", 262_144),
    LmStudioSupportedModel("qwen/qwen3-vl-30b", 262_144),
    LmStudioSupportedModel("allenai/olmocr-2-7b", 128_000),
)


def supported_lmstudio_model_max_context(model: str) -> int | None:
    normalized = _normalize_model_id(model)
    for supported_model in SUPPORTED_LMSTUDIO_VISION_MODELS:
        if _normalize_model_id(supported_model.model) == normalized:
            return supported_model.max_context_tokens
    return None


def supported_lmstudio_vision_model_ids() -> list[str]:
    return [model.model for model in SUPPORTED_LMSTUDIO_VISION_MODELS]


def _normalize_model_id(model: str) -> str:
    return model.strip().split("@", 1)[0].casefold()
