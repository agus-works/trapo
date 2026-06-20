from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INFINITY_ENGINE = "infinity"
INFINITY_MARKDOWN_ENGINE = "infinity_markdown"
INFINITY_PROVIDER = "local-infinity-parser2"
DEFAULT_INFINITY_MODEL = "infly/Infinity-Parser2-Flash"
DEFAULT_INFINITY_LMSTUDIO_MODEL = "infinity-parser2-flash"
DEFAULT_INFINITY_BACKEND = "vllm-engine"
DEFAULT_INFINITY_BATCH_SIZE = 1
DEFAULT_INFINITY_DEVICE = "cuda"
DEFAULT_INFINITY_TORCH_DTYPE = "bfloat16"


@dataclass(frozen=True)
class InfinityOptions:
    model: str = DEFAULT_INFINITY_MODEL
    backend: str = DEFAULT_INFINITY_BACKEND
    batch_size: int = DEFAULT_INFINITY_BATCH_SIZE
    device: str = DEFAULT_INFINITY_DEVICE
    torch_dtype: str = DEFAULT_INFINITY_TORCH_DTYPE

    def __post_init__(self) -> None:
        backend = normalize_infinity_backend(self.backend)
        object.__setattr__(self, "backend", backend)
        object.__setattr__(
            self,
            "model",
            normalize_infinity_model(self.model, backend=backend),
        )


@dataclass(frozen=True)
class InfinityParseResult:
    text: str
    data: dict[str, Any]
    model: str
    provider: str = INFINITY_PROVIDER


def normalize_infinity_backend(value: str) -> str:
    backend = value.strip().lower()
    aliases = {
        "lm-studio": "lmstudio",
        "local-lmstudio": "lmstudio",
        "local-lm-studio": "lmstudio",
    }
    return aliases.get(backend, backend or DEFAULT_INFINITY_BACKEND)


def normalize_infinity_model(
    value: str, *, backend: str = DEFAULT_INFINITY_BACKEND
) -> str:
    model = value.strip()
    if normalize_infinity_backend(backend) == "lmstudio":
        aliases = {
            "infly/infinity-parser2-flash": DEFAULT_INFINITY_LMSTUDIO_MODEL,
            "infly/Infinity-Parser2-Flash": DEFAULT_INFINITY_LMSTUDIO_MODEL,
        }
        return aliases.get(model, model or DEFAULT_INFINITY_LMSTUDIO_MODEL)
    aliases = {
        "infinity-parser2-flash": DEFAULT_INFINITY_MODEL,
        "infly/infinity-parser2-flash": DEFAULT_INFINITY_MODEL,
    }
    return aliases.get(model.lower(), model or DEFAULT_INFINITY_MODEL)
