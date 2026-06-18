from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from trapo.ingest.infinity_models import (
    INFINITY_ENGINE,
    INFINITY_MARKDOWN_ENGINE,
    INFINITY_PROVIDER,
    InfinityOptions,
    InfinityParseResult,
)
from trapo.ingest.normalized_pages import NormalizedPreviewPage
from trapo.ingest.page_markdown_types import MarkdownPageImage
from trapo.ingest.infinity_uvx import UvxInfinityParser
from trapo.server.provenance import parse_json_value


class InfinityParserProtocol(Protocol):
    def parse(self, source: object, **kwargs: Any) -> object: ...


def read_regions_with_infinity(
    pages: list[NormalizedPreviewPage],
    *,
    source_path: Path,
    options: InfinityOptions,
    log: Callable[[str], None] | None = None,
    parser: InfinityParserProtocol | None = None,
) -> InfinityParseResult:
    """Read normalized preview pages through Infinity Parser2 JSON layout mode."""
    page_outputs = _parse_pages(
        [page.image_path for page in pages],
        options=options,
        task_type="doc2json",
        output_format="json",
        log=log,
        parser=parser,
    )
    text_parts: list[str] = []
    for page in page_outputs:
        text_parts.extend(_text_values(page.get("result")))
    return InfinityParseResult(
        text="\n".join(text_parts),
        model=options.model,
        data={
            "engine": INFINITY_ENGINE,
            "provider": INFINITY_PROVIDER,
            "model": options.model,
            "backend": options.backend,
            "source": str(source_path),
            "input": "normalized_preview_jpg",
            "page_error_count": sum(
                1 for page in page_outputs if page.get("status") == "error"
            ),
            "pages": [
                {
                    **page_output,
                    "page_no": page.page_no,
                    "width": page.page.width,
                    "height": page.page.height,
                    "render_sha256": page.image_sha256,
                    "image_path": str(page.image_path),
                }
                for page, page_output in zip(pages, page_outputs, strict=True)
            ],
        },
    )


def read_page_markdown_with_infinity(
    pages: Iterable[MarkdownPageImage],
    *,
    source_path: Path,
    options: InfinityOptions,
    log: Callable[[str], None] | None = None,
    parser: InfinityParserProtocol | None = None,
) -> list[dict[str, Any]]:
    """Read page images through Infinity Parser2 Markdown mode."""
    page_list = list(pages)
    page_outputs = _parse_pages(
        [_markdown_image_path(page) for page in page_list],
        options=options,
        task_type="doc2md",
        output_format=None,
        log=log,
        parser=parser,
    )
    return [
        {
            **page_output,
            "engine": INFINITY_MARKDOWN_ENGINE,
            "provider": INFINITY_PROVIDER,
            "model": options.model,
            "source": str(source_path),
            "page_no": page_image.page.page_no,
            "width": page_image.page.width,
            "height": page_image.page.height,
            "render_width": page_image.page.render_width,
            "render_height": page_image.page.render_height,
            "render_mime_type": page_image.page.mime_type,
            "render_sha256": page_image.page.image_sha256,
            "render_cache": page_image.metadata,
            "image_path": str(_markdown_image_path(page_image)),
        }
        for page_image, page_output in zip(page_list, page_outputs, strict=True)
    ]


def _parse_pages(  # noqa: PLR0913
    paths: list[Path],
    *,
    options: InfinityOptions,
    task_type: str,
    output_format: str | None,
    log: Callable[[str], None] | None,
    parser: InfinityParserProtocol | None,
) -> list[dict[str, Any]]:
    if not paths:
        return []
    infinity = parser or _new_parser(options)
    outputs: list[dict[str, Any]] = []
    batch_size = max(int(options.batch_size), 1)
    for offset in range(0, len(paths), batch_size):
        batch = paths[offset : offset + batch_size]
        started_at = time.perf_counter()
        try:
            raw = _parse_batch(
                infinity,
                batch,
                task_type=task_type,
                output_format=output_format,
                batch_size=batch_size,
            )
            elapsed = time.perf_counter() - started_at
            outputs.extend(_batch_outputs(batch, raw, elapsed, task_type))
            _log(
                log,
                "Infinity Parser2 batch complete: "
                f"task={task_type} pages={len(batch)} elapsed={elapsed:.2f}s",
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started_at
            for path in batch:
                outputs.append(
                    {
                        "status": "error",
                        "task_type": task_type,
                        "path": str(path),
                        "elapsed_seconds": elapsed,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
            _log(
                log,
                "Infinity Parser2 batch failed: "
                f"task={task_type} pages={len(batch)} elapsed={elapsed:.2f}s error={exc}",
            )
    return outputs


def _new_parser(options: InfinityOptions) -> InfinityParserProtocol:
    try:
        module = importlib.import_module("infinity_parser2")
    except Exception:
        return UvxInfinityParser(options)
    parser_cls = getattr(module, "InfinityParser2", None)
    if parser_cls is None:
        raise RuntimeError("infinity_parser2 does not expose InfinityParser2.")
    kwargs: dict[str, object] = {
        "model_name": options.model,
        "backend": options.backend,
    }
    if options.backend == "transformers":
        kwargs.update({"device": options.device, "torch_dtype": options.torch_dtype})
    return parser_cls(**kwargs)


def _parse_batch(
    parser: InfinityParserProtocol,
    batch: list[Path],
    *,
    task_type: str,
    output_format: str | None,
    batch_size: int,
) -> object:
    source: str | list[str] = (
        str(batch[0]) if len(batch) == 1 else [str(path) for path in batch]
    )
    kwargs: dict[str, object] = {"task_type": task_type, "batch_size": batch_size}
    if output_format is not None:
        kwargs["output_format"] = output_format
    return parser.parse(source, **kwargs)


def _batch_outputs(
    batch: list[Path],
    raw: object,
    elapsed_seconds: float,
    task_type: str,
) -> list[dict[str, Any]]:
    values = _raw_values(raw, expected_count=len(batch))
    return [
        {
            "status": "ok",
            "task_type": task_type,
            "path": str(path),
            "elapsed_seconds": elapsed_seconds,
            "result": result,
        }
        for path, result in zip(batch, values, strict=True)
    ]


def _raw_values(raw: object, *, expected_count: int) -> list[object]:  # noqa: PLR0911
    if expected_count == 1:
        return [raw]
    if isinstance(raw, dict):
        values = list(raw.values())
        if len(values) == expected_count:
            return values
    if isinstance(raw, list) and len(raw) == expected_count:
        return raw
    return [raw for _ in range(expected_count)]


def _markdown_image_path(page: MarkdownPageImage) -> Path:
    if page.image_path is None:
        raise RuntimeError("Infinity page Markdown requires cached page image paths.")
    return page.image_path


def _text_values(value: object) -> list[str]:
    data = parse_json_value(value)
    values: list[str] = []
    if isinstance(data, str):
        values.append(data)
    elif isinstance(data, dict):
        for key in ("text", "content", "markdown", "html"):
            child = data.get(key)
            if isinstance(child, str) and child.strip():
                values.append(child)
        for child in data.values():
            if isinstance(child, list | dict):
                values.extend(_text_values(child))
    elif isinstance(data, list):
        for child in data:
            values.extend(_text_values(child))
    return [" ".join(value.split()) for value in values if value.strip()]


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)
