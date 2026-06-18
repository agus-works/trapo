from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.document_markdown import (
    PageMarkdown,
    is_usable_markdown_text,
)
from trapo.ingest.lmstudio_client import (
    LmStudioClient,
    LmStudioStructuredOutputError,
    PageMarkdownClient,
)
from trapo.ingest.lmstudio_models import LmStudioMarkdownOptions
from trapo.ingest.lmstudio_prompts import page_markdown_prompt
from trapo.ingest.page_images import RenderedPageImage
from trapo.ingest.page_markdown_images import (
    MarkdownRenderOptions,
    iter_markdown_page_images,
)
from trapo.observability import span_set_attributes, traced_span


@dataclass(frozen=True)
class PageMarkdownReadResult:
    pages: list[PageMarkdown]
    errors: list[dict[str, Any]]


def read_markdown_with_lmstudio(  # noqa: PLR0913
    path: Path,
    *,
    file_hash: str,
    options: LmStudioMarkdownOptions,
    evidence_by_page: Mapping[int, list[dict[str, Any]]] | None = None,
    log: Callable[[str], None] | None = None,
    client: PageMarkdownClient | None = None,
    on_plain_page: Callable[[PageMarkdown], None] | None = None,
    on_page: Callable[[PageMarkdown], None] | None = None,
) -> PageMarkdownReadResult:
    """Generate faithful per-page Markdown through LM Studio."""
    pages: list[PageMarkdown] = []
    errors: list[dict[str, Any]] = []
    lmstudio = client or LmStudioClient(
        base_url=options.base_url,
        model=options.model,
        timeout_seconds=options.timeout_seconds,
    )
    close_client = client is None
    try:
        for page_image in iter_markdown_page_images(
            path,
            options=MarkdownRenderOptions(
                file_hash=file_hash,
                render_dpi=options.render_dpi,
                image_max_side=options.image_max_side,
                image_format=options.image_format,
                jpeg_quality=options.jpeg_quality,
                cache_enabled=options.cache_enabled,
                cache_root=options.cache_root,
                image_rotation_degrees_by_page=options.image_rotation_degrees_by_page,
            ),
            log=log,
        ):
            page = page_image.page
            page_evidence = list((evidence_by_page or {}).get(page.page_no, []))
            with traced_span(
                "trapo.ingest.page_markdown.page",
                attributes={
                    "file.hash": file_hash,
                    "page.no": page.page_no,
                    "markdown.engine": options.markdown_engine,
                    "lmstudio.model": options.model,
                    "render.cache_hit": bool(page_image.metadata.get("cache_hit")),
                },
            ) as page_span:
                try:
                    page_markdown = _read_page_markdown(
                        lmstudio,
                        page,
                        file_hash,
                        options,
                        page_evidence,
                        log,
                        on_plain_page,
                        page_image.metadata,
                    )
                except Exception as exc:
                    error = _page_error(page, exc)
                    errors.append(error)
                    span_set_attributes(
                        page_span,
                        {
                            "markdown.error": True,
                            "markdown.error_type": error["error_type"],
                        },
                    )
                    _log(
                        log,
                        "Page Markdown generation failed: "
                        f"page={page.page_no} error={error['error']}",
                    )
                    continue
                span_set_attributes(
                    page_span,
                    {
                        "markdown.char_count": len(page_markdown.markdown_text),
                        "markdown.render_sha256": page_markdown.render_sha256,
                    },
                )
                pages.append(page_markdown)
                if on_page is not None:
                    on_page(page_markdown)
    finally:
        if close_client:
            lmstudio.close()
    return PageMarkdownReadResult(pages=pages, errors=errors)


def _read_page_markdown(  # noqa: PLR0913
    lmstudio: PageMarkdownClient,
    page: RenderedPageImage,
    file_hash: str,
    options: LmStudioMarkdownOptions,
    evidence: list[dict[str, Any]],
    log: Callable[[str], None] | None,
    on_plain_page: Callable[[PageMarkdown], None] | None,
    render_metadata: dict[str, Any],
) -> PageMarkdown:
    _log(
        log,
        "Generating page Markdown: "
        f"page={page.page_no} evidence={len(evidence)} render={page.render_width}x{page.render_height} "
        f"mime={page.mime_type} bytes={len(page.image_bytes)} cache_hit={render_metadata.get('cache_hit')}",
    )
    started_at = time.perf_counter()
    markdown_response, markdown_raw_response = lmstudio.generate_page_markdown(
        page,
        prompt=page_markdown_prompt(page),
        max_tokens=options.markdown_max_tokens,
        temperature=options.temperature,
    )
    markdown_elapsed = time.perf_counter() - started_at
    if not is_usable_markdown_text(markdown_response.markdown):
        raise LmStudioStructuredOutputError(
            stage="page_markdown",
            model=options.model,
            raw_content=markdown_response.markdown,
            response_metadata=markdown_raw_response,
            reason=f"LM Studio returned unusable page Markdown: {markdown_response.markdown!r}",
        )
    page_markdown = PageMarkdown(
        file_hash=file_hash,
        page_no=page.page_no,
        markdown_engine=options.markdown_engine,
        markdown_model=options.model,
        markdown_text=markdown_response.markdown,
        page_width=page.width,
        page_height=page.height,
        render_sha256=page.image_sha256,
        metadata={
            "source": "lmstudio_page_markdown",
            "model": options.model,
            "render_width": page.render_width,
            "render_height": page.render_height,
            "render_mime_type": page.mime_type,
            "evidence_count": len(evidence),
            "markdown_elapsed_seconds": markdown_elapsed,
            "markdown_warnings": markdown_response.warnings,
            "markdown_raw_response": markdown_raw_response,
            "render_cache": render_metadata,
        },
        mappings=[],
    )
    if on_plain_page is not None:
        on_plain_page(page_markdown)

    raw_stats = (
        markdown_raw_response.get("stats")
        if isinstance(markdown_raw_response, dict)
        else None
    )
    _log(
        log,
        "Stored page Markdown: "
        f"page={page.page_no} chars={len(markdown_response.markdown)} "
        f"elapsed={markdown_elapsed:.2f}s",
    )
    if log is not None:
        _log_stats(log, "page Markdown", page.page_no, raw_stats)
    return page_markdown


def _log_stats(
    log: Callable[[str], None],
    stage: str,
    page_no: int,
    stats: object,
) -> None:
    if not isinstance(stats, dict) or not stats:
        return
    log(f"LM Studio {stage} stats: page={page_no} {stats}")


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)


def _page_error(page: RenderedPageImage, exc: Exception) -> dict[str, Any]:
    return {
        "page_no": page.page_no,
        "render_width": page.render_width,
        "render_height": page.render_height,
        "render_sha256": page.image_sha256,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
