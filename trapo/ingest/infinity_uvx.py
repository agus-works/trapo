from __future__ import annotations

import json
import subprocess
from typing import Any

from trapo.ingest.infinity_models import InfinityOptions


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
            [
                "uvx",
                "--from",
                "infinity-parser2",
                "python",
                "-c",
                UVX_SCRIPT,
            ],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Infinity Parser2 uvx call failed: {detail}")
        return json.loads(completed.stdout)


UVX_SCRIPT = r"""
import json
import sys

from infinity_parser2 import InfinityParser2

payload = json.loads(sys.stdin.read())
options = payload["options"]
kwargs = payload["kwargs"]
parser_kwargs = {
    "model_name": options["model"],
    "backend": options["backend"],
}
if options["backend"] == "transformers":
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

