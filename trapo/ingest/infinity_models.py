from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INFINITY_ENGINE = "infinity"
INFINITY_MARKDOWN_ENGINE = "infinity_markdown"
INFINITY_PROVIDER = "local-infinity-parser2"
DEFAULT_INFINITY_MODEL = "infly/Infinity-Parser2-Flash"
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


@dataclass(frozen=True)
class InfinityParseResult:
    text: str
    data: dict[str, Any]
    model: str
    provider: str = INFINITY_PROVIDER

