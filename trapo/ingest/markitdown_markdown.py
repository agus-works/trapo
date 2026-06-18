from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trapo.db import DuckConnection
from trapo.document_markdown import (
    MARKITDOWN_CU_MARKDOWN_ENGINE,
    MARKITDOWN_MARKDOWN_ENGINE,
    PageMarkdown,
    is_usable_markdown_text,
    upsert_page_markdown,
)
from trapo.ingest.options import IngestOptions
from trapo.ingest.markitdown_inputs import (
    MarkItDownInput,
    markitdown_inputs_for_path,
)
from trapo.ingest.target_pages import (
    image_rotation_degrees_by_page,
    target_pages_for_regions,
)
from trapo.observability import span_set_attributes, traced_span
from trapo.server.models import PageInfo


MARKITDOWN_PROVIDER = "local-markitdown"
MARKITDOWN_MODEL = "markitdown-ocr"
MARKITDOWN_CU_PROVIDER = "azure-content-understanding"
MARKITDOWN_CU_MODEL = "markitdown-content-understanding"
_PAGE_MARKER_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*Page\s+(\d+)|<!--\s*page\s+(\d+)\s*-->)\s*$"
)
_MARKITDOWN_OCR_PROMPT = (
    "Extract only the readable text from this document image. Preserve reading "
    "order, tables, headings, and lists where clear. Do not add commentary."
)


def process_markitdown_markdown(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    options: IngestOptions,
    log: Callable[[str], None],
    *,
    markdown_engine: str = MARKITDOWN_MARKDOWN_ENGINE,
) -> int:
    """Generate per-page Markdown with MarkItDown."""
    use_cu = markdown_engine == MARKITDOWN_CU_MARKDOWN_ENGINE
    provider = MARKITDOWN_CU_PROVIDER if use_cu else MARKITDOWN_PROVIDER
    model = MARKITDOWN_CU_MODEL if use_cu else MARKITDOWN_MODEL
    log(f"Generating page Markdown with MarkItDown: {path} engine={markdown_engine}")
    pages_info = target_pages_for_regions(connection, path, file_hash) or []
    with traced_span(
        "trapo.ingest.markitdown_markdown",
        attributes={
            "file.hash": file_hash,
            "markdown.engine": markdown_engine,
            "markdown.provider": provider,
            "markdown.model": model,
            "markitdown.content_understanding": use_cu,
            "markitdown.lmstudio_ocr": options.markitdown_lmstudio_ocr,
        },
    ) as span:
        started_at = time.perf_counter()
        markdown, raw_metadata = _convert_with_markitdown(
            path,
            file_hash=file_hash,
            options=options,
            use_cu=use_cu,
            image_rotation_degrees_by_page=image_rotation_degrees_by_page(pages_info),
            log=log,
        )
        elapsed = time.perf_counter() - started_at
        pages = _page_markdown_records(
            file_hash,
            markdown_engine,
            provider,
            model,
            markdown,
            pages_info,
            {
                **raw_metadata,
                "conversion_elapsed_seconds": elapsed,
                "source": "markitdown_page_markdown",
            },
        )
        for page in pages:
            upsert_page_markdown(connection, page)
        span_set_attributes(
            span,
            {
                "markdown.page_count": len(pages),
                "markdown.char_count": sum(len(page.markdown_text) for page in pages),
            },
        )
    log(f"Stored MarkItDown page Markdown: pages={len(pages)}")
    return len(pages)


def markitdown_identity(
    markdown_engine: str = MARKITDOWN_MARKDOWN_ENGINE,
) -> tuple[str, str]:
    if markdown_engine == MARKITDOWN_CU_MARKDOWN_ENGINE:
        return MARKITDOWN_CU_PROVIDER, MARKITDOWN_CU_MODEL
    return MARKITDOWN_PROVIDER, MARKITDOWN_MODEL


def _convert_with_markitdown(  # noqa: PLR0913
    path: Path,
    *,
    file_hash: str,
    options: IngestOptions,
    use_cu: bool,
    image_rotation_degrees_by_page: dict[int, int] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, object]]:
    markitdown, metadata = _create_markitdown_converter(options, use_cu=use_cu)
    conversion_inputs = markitdown_inputs_for_path(
        path,
        file_hash=file_hash,
        options=options,
        image_rotation_degrees_by_page=image_rotation_degrees_by_page or {},
        log=log,
    )
    if len(conversion_inputs) == 1 and conversion_inputs[0].page_no is None:
        result = markitdown.convert(conversion_inputs[0].path)
        return str(result.markdown), {
            **metadata,
            "markitdown_inputs": [conversion_inputs[0].metadata],
        }
    return _convert_page_images_with_markitdown(markitdown, metadata, conversion_inputs)


def _create_markitdown_converter(
    options: IngestOptions,
    *,
    use_cu: bool,
) -> tuple[Any, dict[str, object]]:
    from markitdown import MarkItDown  # noqa: PLC0415

    kwargs: dict[str, Any] = {}
    metadata: dict[str, object] = {"mode": "local"}
    if use_cu:
        endpoint = _content_understanding_endpoint(options)
        if not endpoint:
            raise ValueError(
                "MarkItDown Content Understanding requested but no endpoint is configured."
            )
        kwargs["cu_endpoint"] = endpoint
        analyzer = options.markitdown_cu_analyzer.strip()
        if analyzer:
            kwargs["cu_analyzer_id"] = analyzer
        metadata = {"mode": "content_understanding", "cu_analyzer": analyzer}
        return MarkItDown(enable_plugins=False, **kwargs), metadata

    client = (
        _lmstudio_openai_client(options) if options.markitdown_lmstudio_ocr else None
    )
    if client is not None:
        kwargs.update(
            {
                "llm_client": client,
                "llm_model": options.lmstudio_model,
                "llm_prompt": _MARKITDOWN_OCR_PROMPT,
            }
        )
        metadata = {
            "mode": "local_lmstudio_ocr",
            "lmstudio_model": options.lmstudio_model,
            "lmstudio_base_url": options.lmstudio_base_url,
        }
    markitdown = MarkItDown(enable_plugins=False, **kwargs)
    _register_ocr_plugin(markitdown, kwargs)
    return markitdown, metadata


def _convert_page_images_with_markitdown(
    markitdown: Any,
    metadata: dict[str, object],
    conversion_inputs: list[MarkItDownInput],
) -> tuple[str, dict[str, object]]:
    sections: list[str] = []
    for conversion_input in conversion_inputs:
        result = markitdown.convert(conversion_input.path)
        page_no = conversion_input.page_no
        if page_no is None:
            raise RuntimeError("Normalized MarkItDown image input is missing page_no.")
        sections.append(f"<!-- page {page_no} -->\n\n{str(result.markdown).strip()}")
    return "\n\n".join(sections), {
        **metadata,
        "normalized_image_input": True,
        "markitdown_inputs": [item.metadata for item in conversion_inputs],
    }


def _lmstudio_openai_client(options: IngestOptions) -> Any:
    from openai import OpenAI  # noqa: PLC0415

    return OpenAI(
        api_key=os.environ.get("LMSTUDIO_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "lm-studio",
        base_url=options.lmstudio_base_url,
        timeout=options.lmstudio_timeout_seconds,
    )


def _register_ocr_plugin(markitdown: Any, kwargs: dict[str, Any]) -> None:
    from markitdown_ocr import register_converters  # noqa: PLC0415

    register_converters(markitdown, **kwargs)


def _content_understanding_endpoint(options: IngestOptions) -> str:
    return (
        options.markitdown_cu_endpoint.strip()
        or os.environ.get("TRAPO_MARKITDOWN_CU_ENDPOINT", "").strip()
        or os.environ.get("AZURE_CONTENT_UNDERSTANDING_ENDPOINT", "").strip()
    )


def _page_markdown_records(  # noqa: PLR0913
    file_hash: str,
    markdown_engine: str,
    provider: str,
    model: str,
    markdown: str,
    pages_info: list[PageInfo],
    metadata: dict[str, object],
) -> list[PageMarkdown]:
    sections = _split_page_sections(markdown)
    if not sections and len(pages_info) == 1 and is_usable_markdown_text(markdown):
        sections = {pages_info[0].page_no: markdown.strip()}

    dimensions = {page.page_no: page for page in pages_info}
    expected_pages = sorted(dimensions)
    missing_pages = [
        page_no
        for page_no in expected_pages
        if not is_usable_markdown_text(sections.get(page_no, ""))
    ]
    records: list[PageMarkdown] = []
    for page_no, text in sorted(sections.items()):
        if not is_usable_markdown_text(text):
            continue
        page_info = dimensions.get(page_no)
        records.append(
            PageMarkdown(
                file_hash=file_hash,
                page_no=page_no,
                markdown_engine=markdown_engine,
                markdown_provider=provider,
                markdown_model=model,
                markdown_text=text.strip(),
                page_width=page_info.width if page_info else None,
                page_height=page_info.height if page_info else None,
                metadata={
                    **metadata,
                    "expected_page_count": len(expected_pages),
                    "missing_pages": missing_pages,
                },
            )
        )
    return records


def _split_page_sections(markdown: str) -> dict[int, str]:
    matches = list(_PAGE_MARKER_RE.finditer(markdown))
    if not matches:
        return {}
    sections: dict[int, list[str]] = {}
    for index, match in enumerate(matches):
        page_value = match.group(1) or match.group(2)
        if page_value is None:
            continue
        page_no = int(page_value)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        content = markdown[match.end() : end].strip()
        sections.setdefault(page_no, []).append(content)
    return {
        page_no: "\n\n".join(part for part in parts if part).strip()
        for page_no, parts in sections.items()
    }
