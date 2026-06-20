from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.db import DuckConnection
from trapo.document_markdown import (
    INFINITY_MARKDOWN_ENGINE,
    LMSTUDIO_MARKDOWN_ENGINE,
    MarkdownGeneratorRecord,
    PageMarkdown,
    is_usable_markdown_text,
    markdown_complete,
    record_markdown_generator,
    upsert_page_markdown,
)
from trapo.ingest.infinity_models import (
    INFINITY_PROVIDER,
    InfinityOptions,
)
from trapo.ingest.infinity_reader import read_page_markdown_with_infinity
from trapo.ingest.lmstudio_context import LmStudioContextInfo
from trapo.ingest.lmstudio_context import resolve_markdown_max_tokens
from trapo.ingest.lmstudio_lifecycle import lmstudio_model_lease
from trapo.ingest.lmstudio_models import LmStudioMarkdownOptions
from trapo.ingest.markdown_engines import requested_markdown_engines
from trapo.ingest.markdown_reader import read_markdown_with_lmstudio
from trapo.ingest.markitdown_markdown import (
    markitdown_identity,
    process_markitdown_markdown,
)
from trapo.ingest.options import IngestOptions
from trapo.ingest.page_markdown_images import (
    MarkdownRenderOptions,
    iter_markdown_page_images,
)
from trapo.ingest.target_pages import (
    image_rotation_degrees_by_page,
    target_pages_for_regions,
)
from trapo.observability import span_set_attributes, traced_span
from trapo.server.models import PageInfo


@dataclass(frozen=True)
class PageMarkdownSummary:
    page_count: int = 0
    error_count: int = 0
    errors: list[dict[str, Any]] | None = None


def process_page_markdown(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    context_info: LmStudioContextInfo | None = None,
) -> PageMarkdownSummary:
    engine_summaries: list[PageMarkdownSummary] = []
    for markdown_engine in requested_markdown_engines(options):
        engine_summary = _process_markdown_engine(
            connection,
            path,
            file_hash,
            run_id,
            options,
            log,
            markdown_engine,
            context_info,
        )
        engine_summaries.append(engine_summary)
    return _combine_page_markdown_summaries(engine_summaries)


def _combine_page_markdown_summaries(
    engine_summaries: list[PageMarkdownSummary],
) -> PageMarkdownSummary:
    page_count = sum(summary.page_count for summary in engine_summaries)
    errors = [error for summary in engine_summaries for error in (summary.errors or [])]
    has_complete_engine = any(
        summary.page_count > 0 and summary.error_count == 0
        for summary in engine_summaries
    )
    if has_complete_engine:
        return PageMarkdownSummary(page_count=page_count, errors=errors or None)
    return PageMarkdownSummary(
        page_count=page_count,
        error_count=sum(summary.error_count for summary in engine_summaries),
        errors=errors or None,
    )


def _process_markdown_engine(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    markdown_engine: str,
    context_info: LmStudioContextInfo | None = None,
) -> PageMarkdownSummary:
    pages = target_pages_for_regions(connection, path, file_hash) or []
    expected_pages = [page.page_no for page in pages]
    summary = PageMarkdownSummary()
    if (
        not options.reprocess
        and expected_pages
        and markdown_complete(
            connection,
            file_hash,
            markdown_engine=markdown_engine,
            page_numbers=expected_pages,
        )
    ):
        log(f"Page Markdown already complete: engine={markdown_engine} path={path}")
    else:
        summary = _generate_markdown_engine(
            connection,
            path,
            file_hash,
            run_id,
            options,
            log,
            markdown_engine,
            pages,
            expected_pages,
            context_info,
        )
    return summary


def _generate_markdown_engine(  # noqa: PLR0911, PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    markdown_engine: str,
    pages: list[PageInfo],
    expected_pages: list[int],
    context_info: LmStudioContextInfo | None = None,
) -> PageMarkdownSummary:
    try:
        if markdown_engine == LMSTUDIO_MARKDOWN_ENGINE:
            markdown_summary = _process_lmstudio_markdown(
                connection,
                path,
                file_hash,
                options,
                log,
                pages,
                context_info,
            )
            error_count = markdown_summary.error_count
            record_markdown_generator(
                connection,
                MarkdownGeneratorRecord(
                    file_hash=file_hash,
                    ingest_run_id=run_id,
                    markdown_engine=markdown_engine,
                    markdown_provider="local-lmstudio",
                    markdown_model=options.lmstudio_model,
                    status="ok" if error_count == 0 else "partial",
                    page_count=markdown_summary.page_count,
                    error=f"{error_count} page(s) failed" if error_count else None,
                    metadata={
                        "expected_pages": expected_pages,
                        "error_count": error_count,
                        "errors": markdown_summary.errors or [],
                    },
                ),
            )
            return markdown_summary
        if markdown_engine == INFINITY_MARKDOWN_ENGINE:
            infinity_options = InfinityOptions(
                model=options.infinity_model,
                backend=options.infinity_backend,
                batch_size=options.infinity_batch_size,
                device=options.infinity_device,
                torch_dtype=options.infinity_torch_dtype,
            )
            markdown_summary = _process_infinity_markdown(
                connection,
                path,
                file_hash,
                options,
                log,
            )
            error_count = markdown_summary.error_count
            record_markdown_generator(
                connection,
                MarkdownGeneratorRecord(
                    file_hash=file_hash,
                    ingest_run_id=run_id,
                    markdown_engine=markdown_engine,
                    markdown_provider=INFINITY_PROVIDER,
                    markdown_model=infinity_options.model,
                    status="ok" if error_count == 0 else "partial",
                    page_count=markdown_summary.page_count,
                    error=f"{error_count} page(s) failed" if error_count else None,
                    metadata={
                        "expected_pages": expected_pages,
                        "error_count": error_count,
                        "errors": markdown_summary.errors or [],
                        "backend": options.infinity_backend,
                        "batch_size": options.infinity_batch_size,
                        "requested_model": options.infinity_model,
                    },
                ),
            )
            return markdown_summary
        return _generate_markitdown_engine(
            connection,
            path,
            file_hash,
            run_id,
            options,
            log,
            markdown_engine,
            expected_pages,
        )
    except Exception as exc:
        provider, model = _markdown_identity(markdown_engine, options)
        record_markdown_generator(
            connection,
            MarkdownGeneratorRecord(
                file_hash=file_hash,
                ingest_run_id=run_id,
                markdown_engine=markdown_engine,
                markdown_provider=provider,
                markdown_model=model,
                status="error",
                error=str(exc),
                metadata={"expected_pages": expected_pages},
            ),
        )
        log(
            f"Page Markdown generation failed: engine={markdown_engine} path={path}: {exc}"
        )
        return PageMarkdownSummary(error_count=1)


def _generate_markitdown_engine(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    markdown_engine: str,
    expected_pages: list[int],
) -> PageMarkdownSummary:
    provider, model = markitdown_identity(markdown_engine)
    page_count = process_markitdown_markdown(
        connection,
        path,
        file_hash,
        options,
        log,
        markdown_engine=markdown_engine,
    )
    record_markdown_generator(
        connection,
        MarkdownGeneratorRecord(
            file_hash=file_hash,
            ingest_run_id=run_id,
            markdown_engine=markdown_engine,
            markdown_provider=provider,
            markdown_model=model,
            status="ok",
            page_count=page_count,
            metadata={"expected_pages": expected_pages},
        ),
    )
    return PageMarkdownSummary(page_count=page_count)


def _process_infinity_markdown(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    options: IngestOptions,
    log: Callable[[str], None],
) -> PageMarkdownSummary:
    log(
        "Generating page Markdown with Infinity Parser2: "
        f"{path} model={options.infinity_model} backend={options.infinity_backend}"
    )
    render_options = MarkdownRenderOptions(
        file_hash=file_hash,
        render_dpi=options.page_markdown_render_dpi,
        image_max_side=options.page_markdown_image_max_side,
        image_format=options.page_markdown_image_format,
        jpeg_quality=options.page_markdown_jpeg_quality,
        cache_enabled=True,
        cache_root=options.page_markdown_cache_root,
        image_rotation_degrees_by_page=image_rotation_degrees_by_page(
            target_pages_for_regions(connection, path, file_hash) or []
        ),
    )
    infinity_options = InfinityOptions(
        model=options.infinity_model,
        backend=options.infinity_backend,
        batch_size=options.infinity_batch_size,
        device=options.infinity_device,
        torch_dtype=options.infinity_torch_dtype,
    )
    resolved_model = infinity_options.model
    with traced_span(
        "trapo.ingest.page_markdown",
        attributes={
            "file.hash": file_hash,
            "markdown.engine": INFINITY_MARKDOWN_ENGINE,
            "infinity.model": resolved_model,
            "infinity.backend": options.infinity_backend,
            "markdown.render_dpi": options.page_markdown_render_dpi,
            "markdown.image_max_side": options.page_markdown_image_max_side,
        },
    ) as markdown_span:
        page_images = list(
            iter_markdown_page_images(path, options=render_options, log=log)
        )
        if infinity_options.backend == "lmstudio":
            with lmstudio_model_lease(
                model=resolved_model,
                timeout_seconds=min(options.lmstudio_timeout_seconds, 60.0),
                enabled=options.lmstudio_maximize_context,
                log=log,
            ):
                outputs = read_page_markdown_with_infinity(
                    page_images,
                    source_path=path,
                    options=infinity_options,
                    log=log,
                )
        else:
            outputs = read_page_markdown_with_infinity(
                page_images,
                source_path=path,
                options=infinity_options,
                log=log,
            )
        pages: list[PageMarkdown] = []
        errors: list[dict[str, Any]] = []
        for output in outputs:
            if output.get("status") == "error":
                errors.append(_infinity_page_error(output))
                continue
            markdown_text = _infinity_markdown_text(output.get("result"))
            if not is_usable_markdown_text(markdown_text):
                errors.append(
                    {
                        "page_no": output.get("page_no"),
                        "render_sha256": output.get("render_sha256"),
                        "error_type": "UnusableMarkdown",
                        "error": "Infinity Parser2 returned unusable page Markdown.",
                    }
                )
                continue
            page = PageMarkdown(
                file_hash=file_hash,
                page_no=int(output["page_no"]),
                markdown_engine=INFINITY_MARKDOWN_ENGINE,
                markdown_provider=INFINITY_PROVIDER,
                markdown_model=resolved_model,
                markdown_text=markdown_text,
                page_width=_float_or_none(output.get("width")),
                page_height=_float_or_none(output.get("height")),
                render_sha256=str(output.get("render_sha256") or ""),
                metadata={
                    "source": "infinity_parser2_page_markdown",
                    "model": resolved_model,
                    "requested_model": options.infinity_model,
                    "backend": options.infinity_backend,
                    "render_width": output.get("render_width"),
                    "render_height": output.get("render_height"),
                    "render_mime_type": output.get("render_mime_type"),
                    "elapsed_seconds": output.get("elapsed_seconds"),
                    "raw_result": output.get("result"),
                    "render_cache": output.get("render_cache"),
                    "cache_forced": not options.page_markdown_cache,
                },
            )
            upsert_page_markdown(connection, page)
            pages.append(page)
        span_set_attributes(
            markdown_span,
            {
                "markdown.page_count": len(pages),
                "markdown.error_count": len(errors),
            },
        )
    log(
        "Stored Infinity Parser2 page Markdown: "
        f"pages={len(pages)} page_errors={len(errors)}"
    )
    return PageMarkdownSummary(
        page_count=len(pages),
        error_count=len(errors),
        errors=errors or None,
    )


def _process_lmstudio_markdown(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    options: IngestOptions,
    log: Callable[[str], None],
    target_pages: list[PageInfo],
    context_info: LmStudioContextInfo | None = None,
) -> PageMarkdownSummary:
    markdown_max_tokens = resolve_markdown_max_tokens(
        requested_tokens=options.page_markdown_max_tokens,
        context_info=context_info,
    )
    if markdown_max_tokens != options.page_markdown_max_tokens:
        context_tokens = context_info.effective_context_tokens if context_info else None
        log(
            "Resolved LM Studio markdown max tokens from context: "
            f"requested={options.page_markdown_max_tokens} resolved={markdown_max_tokens} "
            f"context_tokens={context_tokens}"
        )
    log(
        f"Generating page Markdown with LM Studio: {path} model={options.lmstudio_model}"
    )
    markdown_options = LmStudioMarkdownOptions(
        base_url=options.lmstudio_base_url,
        model=options.lmstudio_model,
        timeout_seconds=options.lmstudio_timeout_seconds,
        render_dpi=options.page_markdown_render_dpi,
        image_max_side=options.page_markdown_image_max_side,
        image_format=options.page_markdown_image_format,
        jpeg_quality=options.page_markdown_jpeg_quality,
        cache_enabled=options.page_markdown_cache,
        cache_root=options.page_markdown_cache_root,
        markdown_max_tokens=markdown_max_tokens,
        image_rotation_degrees_by_page=image_rotation_degrees_by_page(target_pages),
        markdown_engine=LMSTUDIO_MARKDOWN_ENGINE,
    )
    with traced_span(
        "trapo.ingest.page_markdown",
        attributes={
            "file.hash": file_hash,
            "lmstudio.model": options.lmstudio_model,
            "lmstudio.base_url": options.lmstudio_base_url,
            "markdown.render_dpi": options.page_markdown_render_dpi,
            "markdown.image_max_side": options.page_markdown_image_max_side,
            "markdown.image_format": options.page_markdown_image_format,
            "markdown.jpeg_quality": options.page_markdown_jpeg_quality,
            "markdown.cache_enabled": options.page_markdown_cache,
            "markdown.engine": LMSTUDIO_MARKDOWN_ENGINE,
        },
    ) as markdown_span:

        def persist_page(page: PageMarkdown) -> None:
            upsert_page_markdown(connection, page)

        with lmstudio_model_lease(
            base_url=options.lmstudio_base_url,
            model=options.lmstudio_model,
            timeout_seconds=min(options.lmstudio_timeout_seconds, 60.0),
            enabled=options.lmstudio_maximize_context,
            log=log,
        ):
            result = read_markdown_with_lmstudio(
                path,
                file_hash=file_hash,
                options=markdown_options,
                evidence_by_page={},
                log=log,
                on_plain_page=persist_page,
                on_page=persist_page,
            )
        span_set_attributes(
            markdown_span,
            {
                "markdown.page_count": len(result.pages),
                "markdown.error_count": len(result.errors),
            },
        )
    log(
        "Stored page Markdown: "
        f"pages={len(result.pages)} page_errors={len(result.errors)}"
    )
    return PageMarkdownSummary(
        page_count=len(result.pages),
        error_count=len(result.errors),
        errors=result.errors,
    )


def pending_page_markdown(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    *,
    pending_engines: list[str],
    fusion_pending: bool,
    options: IngestOptions,
) -> bool:
    if not options.page_markdown:
        return False
    target_pages = target_pages_for_regions(connection, path, file_hash) or []
    expected_pages = [page.page_no for page in target_pages]
    requested = requested_markdown_engines(options)
    return (
        options.reprocess
        or bool(pending_engines)
        or fusion_pending
        or any(
            not markdown_complete(
                connection,
                file_hash,
                markdown_engine=markdown_engine,
                page_numbers=expected_pages or None,
            )
            for markdown_engine in requested
        )
    )


def _markdown_identity(markdown_engine: str, options: IngestOptions) -> tuple[str, str]:
    if markdown_engine == LMSTUDIO_MARKDOWN_ENGINE:
        return "local-lmstudio", options.lmstudio_model
    if markdown_engine == INFINITY_MARKDOWN_ENGINE:
        return INFINITY_PROVIDER, options.infinity_model
    return markitdown_identity(markdown_engine)


def _infinity_markdown_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("markdown", "text", "content"):
            child = value.get(key)
            if isinstance(child, str) and child.strip():
                return child.strip()
    return str(value or "").strip()


def _infinity_page_error(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_no": output.get("page_no"),
        "render_sha256": output.get("render_sha256"),
        "error_type": output.get("error_type") or "InfinityParserError",
        "error": output.get("error") or "Infinity Parser2 page failed.",
    }


def _float_or_none(value: object) -> float | None:
    result: float | None = None
    if isinstance(value, int | float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            result = None
    return result
