from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class InfinityParserProtocol(Protocol):
    def parse(self, source: object, **kwargs: Any) -> object: ...


ParseBatch = Callable[
    [InfinityParserProtocol, list[Path], str, str | None, int],
    object,
]
BatchOutputs = Callable[
    [list[Path], object, float, str],
    list[dict[str, Any]],
]


def retry_batch_as_pages(  # noqa: PLR0913
    parser: InfinityParserProtocol,
    batch: list[Path],
    *,
    task_type: str,
    output_format: str | None,
    batch_size: int,
    log: Callable[[str], None] | None,
    batch_error: Exception,
    batch_elapsed_seconds: float,
    parse_batch: ParseBatch,
    batch_outputs: BatchOutputs,
) -> list[dict[str, Any]]:
    _log(
        log,
        "Infinity Parser2 batch failed; retrying pages individually: "
        f"task={task_type} pages={len(batch)} elapsed={batch_elapsed_seconds:.2f}s "
        f"error={batch_error}",
    )
    if len(batch) == 1:
        return [_page_error(batch[0], task_type, batch_elapsed_seconds, batch_error)]

    outputs: list[dict[str, Any]] = []
    for path in batch:
        started_at = time.perf_counter()
        try:
            raw = parse_batch(parser, [path], task_type, output_format, batch_size)
            elapsed = time.perf_counter() - started_at
            outputs.extend(batch_outputs([path], raw, elapsed, task_type))
            _log(
                log,
                "Infinity Parser2 page retry complete: "
                f"task={task_type} path={path} elapsed={elapsed:.2f}s",
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started_at
            outputs.append(_page_error(path, task_type, elapsed, exc))
            _log(
                log,
                "Infinity Parser2 page retry failed: "
                f"task={task_type} path={path} elapsed={elapsed:.2f}s error={exc}",
            )
    return outputs


def _page_error(
    path: Path,
    task_type: str,
    elapsed_seconds: float,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "status": "error",
        "task_type": task_type,
        "path": str(path),
        "elapsed_seconds": elapsed_seconds,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)
