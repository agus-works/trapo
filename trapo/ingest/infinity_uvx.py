from __future__ import annotations

import json
import sys
import subprocess
from typing import Any

from trapo.ingest.infinity_models import InfinityOptions

_WINDOWS_TORCH_BACKEND = "cu130"
_DEFAULT_TORCH_BACKEND = "auto"


class UvxInfinityParser:
    def __init__(self, options: InfinityOptions) -> None:
        self._options = options

    def parse(self, source: object, **kwargs: Any) -> object:
        payload = {
            "source": source,
            "kwargs": kwargs,
            "options": {
                "model": self._options.model,
                "backend": self._options.backend,
                "device": self._options.device,
                "torch_dtype": self._options.torch_dtype,
            },
        }
        completed = subprocess.run(
            _uvx_command(),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Infinity Parser2 uvx call failed: {detail}")
        return json.loads(completed.stdout)


def _uvx_command() -> list[str]:
    return [
        "uvx",
        "--from",
        "infinity-parser2",
        "--with",
        "torch",
        "--with",
        "torchvision",
        "--with",
        "accelerate",
        "--torch-backend",
        _torch_backend(),
        "python",
        "-c",
        UVX_SCRIPT,
    ]


def _torch_backend() -> str:
    if sys.platform == "win32":
        return _WINDOWS_TORCH_BACKEND
    return _DEFAULT_TORCH_BACKEND


UVX_SCRIPT = r"""
import json
import sys
import types

if "vllm" not in sys.modules:
    vllm_module = types.ModuleType("vllm")

    class _UnavailableVllm:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "vLLM is unavailable in the isolated Infinity Parser2 fallback. "
                "Use the transformers backend or run a separate vLLM server."
            )

    vllm_module.LLM = _UnavailableVllm
    vllm_module.SamplingParams = _UnavailableVllm
    sys.modules["vllm"] = vllm_module

from infinity_parser2 import InfinityParser2

payload = json.loads(sys.stdin.read())
options = payload["options"]
kwargs = payload["kwargs"]
backend = options["backend"]
if backend == "vllm-engine":
    backend = "transformers"
parser_kwargs = {
    "model_name": options["model"],
    "backend": backend,
}
if backend == "transformers":
    parser_kwargs.update(
        {
            "device": options["device"],
            "torch_dtype": options["torch_dtype"],
        }
    )
parser = InfinityParser2(**parser_kwargs)
result = parser.parse(payload["source"], **kwargs)
print(json.dumps(result, ensure_ascii=False))
"""
