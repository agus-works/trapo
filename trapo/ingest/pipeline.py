from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.assets import PREVIEW_EXTENSIONS
from trapo.annotation.docling.regions import rebuild_document_regions
from trapo.config import RuntimeConfig
from trapo.db import DuckConnection, next_table_id, table_exists
from trapo.diagnostics import activate_diagnostic_run, deactivate_diagnostic_run
from trapo.document_markdown import (
    INFINITY_MARKDOWN_ENGINE,
    MARKITDOWN_CU_MARKDOWN_ENGINE,
    MARKITDOWN_MARKDOWN_ENGINE,
)
from trapo.hash import sha256_file
from trapo.ingest.chunking import chunk_docling_document, chunk_text
from trapo.ingest.docling_reader import DoclingReaderOptions, DoclingReadResult
from trapo.ingest.engine_steps import (
    process_infinity,
    process_mineru,
)
from trapo.ingest.infinity_models import INFINITY_ENGINE
from trapo.ingest.infinity_models import InfinityOptions
from trapo.ingest.lmstudio_context import LmStudioContextInfo
from trapo.ingest.lmstudio_lifecycle import lmstudio_model_lease
from trapo.ingest.lmstudio_models import DEFAULT_LMSTUDIO_REPEAT_PENALTY
from trapo.ingest.lmstudio_supported_models import supported_lmstudio_model_max_context
from trapo.ingest.markdown_engines import requested_markdown_engines
from trapo.ingest.model_leases import finish_model_lease, start_model_lease
from trapo.ingest.normalized_pipelines import (
    DOCLING_NORMALIZED_ENGINE,
    MINERU_NORMALIZED_ENGINE,
    process_docling_normalized,
    process_mineru_normalized,
)
from trapo.ingest.ocr_storage import (
    record_docling_error,
    record_ocr_error,
    record_ocr_success,
)
from trapo.ingest.orientation_steps import (
    process_docling_orientation_heuristic,
)
from trapo.ingest.options import IngestOptions, IngestSummary
from trapo.ingest.page_markdown_step import (
    pending_page_markdown,
    process_page_markdown,
)
from trapo.ingest.reader import read_document
from trapo.observability import (
    log_progress,
    mark_span_error,
    span_set_attributes,
    traced_span,
)
from trapo.page_orientation import read_page_orientation_overrides
from trapo.preview_cache import (
    PreviewCacheOptions,
    build_document_preview_cache,
    read_document_preview_images,
)
from trapo.ingest.work_planner import (
    PageArtifact,
    WorkUnit,
    fail_work_unit,
    finish_work_unit,
    start_work_unit,
    upsert_page_artifact,
    upsert_work_unit,
)


@dataclass
class FileExecutionPlan:
    path: Path
    file_hash: str
    index: int
    file_count: int
    engines: list[str]
    pending_engines: list[str]
    markdown_pending: bool
    preview_cache_pending: bool
    chunk_count: int = 0
    region_count: int = 0
    engine_errors: int = 0
    preview_image_count: int = 0
    processed: bool = False
    skipped: bool = False


def discover_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def ingest_directory(  # noqa: PLR0912
    connection: DuckConnection,
    directory: Path,
    config: RuntimeConfig,
    options: IngestOptions,
) -> IngestSummary:
    """Hash files, read them with local annotation engines, and store regions."""
    if not directory.exists() or not directory.is_dir():
        raise ValueError(
            f"Source directory does not exist or is not a directory: {directory}"
        )

    run_id = next_table_id(
        connection,
        table_name="ingest_runs",
        column_name="ingest_run_id",
        sequence_name="ingest_run_id_seq",
    )
    connection.execute(
        """
        INSERT INTO ingest_runs
            (ingest_run_id, source_directory, options_json, status)
        VALUES (?, ?, ?::JSON, 'running')
        """,
        [run_id, str(directory), json.dumps(_options_json(options))],
    )
    activate_diagnostic_run(connection, run_id)

    log = _logger(options.verbosity)
    files = discover_files(directory)
    log(f"Discovered {len(files)} file(s) under {directory}")

    try:
        plans, files_skipped, plan_errors = _plan_ingest_files(
            connection, files, run_id, config, options, log
        )
        errors = plan_errors
        errors += _run_local_file_steps(connection, plans, run_id, config, options, log)
        errors += _run_infinity_group(connection, plans, run_id, options, log)
        errors += _run_markdown_groups(connection, plans, run_id, options, log)

        files_processed = sum(1 for plan in plans if plan.processed)
        chunks_created = sum(plan.chunk_count for plan in plans)
        errors += sum(plan.engine_errors for plan in plans)

        status = "ok" if errors == 0 else "completed_with_errors"
        connection.execute(
            """
            UPDATE ingest_runs
            SET finished_at = current_timestamp, status = ?, error = ?
            WHERE ingest_run_id = ?
            """,
            [status, f"{errors} OCR engine run(s) failed" if errors else None, run_id],
        )
        return IngestSummary(
            files_seen=len(files),
            files_processed=files_processed,
            files_skipped=files_skipped,
            chunks_created=chunks_created,
            errors=errors,
        )
    except Exception as exc:
        connection.execute(
            """
            UPDATE ingest_runs
            SET finished_at = current_timestamp, status = 'error', error = ?
            WHERE ingest_run_id = ?
            """,
            [_error_detail(exc), run_id],
        )
        raise
    finally:
        deactivate_diagnostic_run()


def _plan_ingest_files(  # noqa: PLR0913
    connection: DuckConnection,
    files: list[Path],
    run_id: int,
    config: RuntimeConfig,
    options: IngestOptions,
    log: Callable[[str], None],
) -> tuple[list[FileExecutionPlan], int, int]:
    del config
    plans: list[FileExecutionPlan] = []
    files_skipped = 0
    errors = 0
    for index, path in enumerate(files, start=1):
        file_hash = str(path)
        with traced_span(
            "trapo.ingest.plan_file",
            attributes={
                "file.name": path.name,
                "file.extension": path.suffix.lower(),
                "ingest.file_index": index,
                "ingest.file_count": len(files),
            },
        ) as file_span:
            try:
                log(f"[{index}/{len(files)}] Hashing {path}")
                file_hash = sha256_file(path)
                stat = path.stat()
                span_set_attributes(
                    file_span,
                    {"file.hash": file_hash, "file.size_bytes": stat.st_size},
                )
                _upsert_file(connection, path, file_hash, stat.st_size, stat.st_mtime)
                engines = _supported_engines(path, options)
                if not engines:
                    log(f"Skipping unsupported preview/annotation type: {path}")
                    files_skipped += 1
                    span_set_attributes(file_span, {"ingest.status": "skipped"})
                    continue
                preview_cache_pending = (
                    options.reprocess
                    or not _preview_cache_complete(connection, file_hash)
                )
                pending_engines = [
                    engine
                    for engine in engines
                    if options.reprocess
                    or not _engine_complete(connection, file_hash, engine, options)
                ]
                markdown_pending = pending_page_markdown(
                    connection,
                    path,
                    file_hash,
                    pending_engines=pending_engines,
                    options=options,
                )
                if (
                    not preview_cache_pending
                    and not pending_engines
                    and not markdown_pending
                ):
                    log(f"Skipping unchanged OCR outputs: {path}")
                    files_skipped += 1
                    span_set_attributes(
                        file_span,
                        {
                            "ingest.status": "skipped",
                            "annotation.engines": ",".join(engines),
                        },
                    )
                    continue
                plan = FileExecutionPlan(
                    path=path,
                    file_hash=file_hash,
                    index=index,
                    file_count=len(files),
                    engines=engines,
                    pending_engines=pending_engines,
                    markdown_pending=markdown_pending,
                    preview_cache_pending=preview_cache_pending,
                )
                _upsert_plan_work_units(connection, run_id, plan, options)
                plans.append(plan)
                span_set_attributes(
                    file_span,
                    {
                        "ingest.status": "planned",
                        "annotation.engines": ",".join(engines),
                        "annotation.pending_engines": ",".join(pending_engines),
                        "markdown.pending": markdown_pending,
                    },
                )
            except Exception as exc:
                mark_span_error(file_span, exc)
                span_set_attributes(
                    file_span,
                    {"file.hash": file_hash, "ingest.status": "error"},
                )
                log(f"Error while planning {path}: {exc}")
                errors += 1
                record_docling_error(connection, file_hash, run_id, exc)
    return plans, files_skipped, errors


def _upsert_plan_work_units(
    connection: DuckConnection,
    run_id: int,
    plan: FileExecutionPlan,
    options: IngestOptions,
) -> None:
    if plan.preview_cache_pending:
        _upsert_file_work_unit(
            connection,
            run_id,
            plan,
            phase="artifact",
            engine="preview_cache",
            provider="local-renderer",
            model="trapo-preview-cache",
            execution_key="local:preview_cache",
        )
    for engine in plan.pending_engines:
        provider, model, execution_key = _engine_identity(engine, options)
        _upsert_file_work_unit(
            connection,
            run_id,
            plan,
            phase="annotation",
            engine=engine,
            provider=provider,
            model=model,
            execution_key=execution_key,
        )
    if plan.markdown_pending:
        for markdown_engine in requested_markdown_engines(options):
            provider, model, execution_key = _markdown_identity(
                markdown_engine, options
            )
            _upsert_file_work_unit(
                connection,
                run_id,
                plan,
                phase="markdown",
                engine=markdown_engine,
                provider=provider,
                model=model,
                execution_key=execution_key,
            )


def _run_local_file_steps(  # noqa: PLR0912, PLR0913
    connection: DuckConnection,
    plans: list[FileExecutionPlan],
    run_id: int,
    config: RuntimeConfig,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    for plan in plans:
        with traced_span(
            "trapo.ingest.file_local_steps",
            attributes={
                "file.hash": plan.file_hash,
                "file.name": plan.path.name,
                "ingest.file_index": plan.index,
                "ingest.file_count": plan.file_count,
            },
        ) as file_span:
            if "docling" in plan.pending_engines:
                _run_docling_step(connection, plan, run_id, config, options, log)
            try:
                with traced_span(
                    "trapo.ingest.docling_orientation_heuristic",
                    attributes={"file.hash": plan.file_hash},
                ) as orientation_span:
                    heuristic_overrides = process_docling_orientation_heuristic(
                        connection,
                        plan.path,
                        plan.file_hash,
                        options,
                        log,
                    )
                    span_set_attributes(
                        orientation_span,
                        {"orientation.override_count": heuristic_overrides},
                    )
            except Exception as exc:
                plan.engine_errors += 1
                log(f"Docling orientation heuristic failed for {plan.path}: {exc}")
            if plan.preview_cache_pending:
                _run_preview_step(connection, plan, run_id, log)
            if DOCLING_NORMALIZED_ENGINE in plan.pending_engines:
                _run_ocr_step(
                    connection,
                    plan,
                    run_id,
                    DOCLING_NORMALIZED_ENGINE,
                    "local-docling",
                    "docling-normalized-jpg",
                    lambda: process_docling_normalized(
                        connection,
                        plan.path,
                        plan.file_hash,
                        run_id,
                        options,
                        log,
                    ),
                    log,
                )
            if "mineru" in plan.pending_engines:
                _run_ocr_step(
                    connection,
                    plan,
                    run_id,
                    "mineru",
                    "local-mineru",
                    f"mineru-{options.mineru_backend}",
                    lambda: process_mineru(
                        connection,
                        plan.path,
                        plan.file_hash,
                        run_id,
                        options,
                        log,
                    ),
                    log,
                )
            if MINERU_NORMALIZED_ENGINE in plan.pending_engines:
                _run_ocr_step(
                    connection,
                    plan,
                    run_id,
                    MINERU_NORMALIZED_ENGINE,
                    "local-mineru",
                    f"mineru-{options.mineru_backend}-normalized-jpg",
                    lambda: process_mineru_normalized(
                        connection,
                        plan.path,
                        plan.file_hash,
                        run_id,
                        options,
                        log,
                    ),
                    log,
                )
            span_set_attributes(
                file_span,
                {
                    "chunk.count": plan.chunk_count,
                    "region.count": plan.region_count,
                    "preview.image_count": plan.preview_image_count,
                    "engine.error_count": plan.engine_errors,
                },
            )
    return 0


def _run_infinity_group(
    connection: DuckConnection,
    plans: list[FileExecutionPlan],
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    infinity_plans = [plan for plan in plans if INFINITY_ENGINE in plan.pending_engines]
    if not infinity_plans:
        return 0
    infinity_options = InfinityOptions(
        model=options.infinity_model,
        backend=options.infinity_backend,
        batch_size=options.infinity_batch_size,
        device=options.infinity_device,
        torch_dtype=options.infinity_torch_dtype,
    )
    if infinity_options.backend == "lmstudio":
        try:
            with _recorded_lmstudio_lease(
                connection,
                run_id=run_id,
                execution_key=_lmstudio_execution_key(
                    options.lmstudio_base_url, infinity_options.model
                ),
                model=infinity_options.model,
                base_url=options.lmstudio_base_url,
                timeout_seconds=min(options.lmstudio_timeout_seconds, 60.0),
                enabled=options.lmstudio_maximize_context,
                log=log,
            ):
                for plan in infinity_plans:
                    _run_infinity_step(
                        connection, plan, run_id, options, log, lease=False
                    )
        except Exception as exc:
            log(f"Infinity Parser2 LM Studio batch failed before execution: {exc}")
            for plan in infinity_plans:
                plan.engine_errors += 1
                record_ocr_error(
                    connection,
                    plan.file_hash,
                    run_id,
                    annotation_engine=INFINITY_ENGINE,
                    reader_provider="local-infinity-parser2",
                    reader_model=infinity_options.model,
                    exc=exc,
                )
                fail_work_unit(
                    connection,
                    run_id,
                    _work_key("annotation", INFINITY_ENGINE, plan.file_hash),
                    _error_detail(exc),
                )
        return 0
    for plan in infinity_plans:
        _run_infinity_step(connection, plan, run_id, options, log, lease=True)
    return 0


def _run_markdown_groups(
    connection: DuckConnection,
    plans: list[FileExecutionPlan],
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    markdown_plans = [plan for plan in plans if plan.markdown_pending]
    if not markdown_plans:
        return 0
    requested = requested_markdown_engines(options)
    local_markdown = [
        engine
        for engine in requested
        if engine in {MARKITDOWN_MARKDOWN_ENGINE, MARKITDOWN_CU_MARKDOWN_ENGINE}
    ]
    if local_markdown:
        _run_markdown_engines(
            connection, markdown_plans, run_id, options, log, local_markdown
        )
    if INFINITY_MARKDOWN_ENGINE in requested:
        infinity_options = InfinityOptions(
            model=options.infinity_model,
            backend=options.infinity_backend,
            batch_size=options.infinity_batch_size,
            device=options.infinity_device,
            torch_dtype=options.infinity_torch_dtype,
        )
        if infinity_options.backend == "lmstudio":
            try:
                with _recorded_lmstudio_lease(
                    connection,
                    run_id=run_id,
                    execution_key=_lmstudio_execution_key(
                        options.lmstudio_base_url, infinity_options.model
                    ),
                    model=infinity_options.model,
                    base_url=options.lmstudio_base_url,
                    timeout_seconds=min(options.lmstudio_timeout_seconds, 60.0),
                    enabled=options.lmstudio_maximize_context,
                    log=log,
                ):
                    _run_markdown_engines(
                        connection,
                        markdown_plans,
                        run_id,
                        options,
                        log,
                        [INFINITY_MARKDOWN_ENGINE],
                        lease_lmstudio=False,
                    )
            except Exception as exc:
                _fail_markdown_group(
                    connection,
                    markdown_plans,
                    run_id,
                    [INFINITY_MARKDOWN_ENGINE],
                    exc,
                    log,
                )
        else:
            _run_markdown_engines(
                connection,
                markdown_plans,
                run_id,
                options,
                log,
                [INFINITY_MARKDOWN_ENGINE],
            )
    return 0


def _run_docling_step(  # noqa: PLR0913
    connection: DuckConnection,
    plan: FileExecutionPlan,
    run_id: int,
    config: RuntimeConfig,
    options: IngestOptions,
    log: Callable[[str], None],
) -> None:
    work_key = _work_key("annotation", "docling", plan.file_hash)
    start_work_unit(connection, run_id, work_key)
    try:
        chunks, regions = _process_docling(
            connection,
            plan.path,
            plan.file_hash,
            run_id,
            config,
            options,
            log,
        )
        plan.chunk_count += chunks
        plan.region_count += regions
        plan.processed = True
        finish_work_unit(
            connection,
            run_id,
            work_key,
            result={"chunk_count": chunks, "region_count": regions},
        )
    except Exception as exc:
        plan.engine_errors += 1
        record_docling_error(connection, plan.file_hash, run_id, exc)
        fail_work_unit(connection, run_id, work_key, _error_detail(exc))
        log(f"Docling failed for {plan.path}: {exc}")


def _run_preview_step(
    connection: DuckConnection,
    plan: FileExecutionPlan,
    run_id: int,
    log: Callable[[str], None],
) -> None:
    work_key = _work_key("artifact", "preview_cache", plan.file_hash)
    start_work_unit(connection, run_id, work_key)
    try:
        with traced_span(
            "trapo.ingest.preview_cache",
            attributes={"file.hash": plan.file_hash},
        ) as preview_span:
            image_count = _process_preview_cache(
                connection,
                plan.path,
                plan.file_hash,
                log,
            )
            _record_preview_artifacts(connection, run_id, plan.file_hash)
            span_set_attributes(preview_span, {"preview.image_count": image_count})
        plan.preview_image_count = image_count
        plan.processed = True
        finish_work_unit(
            connection,
            run_id,
            work_key,
            result={"preview_image_count": image_count},
        )
    except Exception as exc:
        plan.engine_errors += 1
        fail_work_unit(connection, run_id, work_key, _error_detail(exc))
        log(f"Preview cache rendering failed for {plan.path}: {exc}")


def _run_ocr_step(  # noqa: PLR0913
    connection: DuckConnection,
    plan: FileExecutionPlan,
    run_id: int,
    annotation_engine: str,
    reader_provider: str,
    reader_model: str,
    action: Callable[[], int],
    log: Callable[[str], None],
) -> None:
    work_key = _work_key("annotation", annotation_engine, plan.file_hash)
    start_work_unit(connection, run_id, work_key)
    try:
        region_count = action()
        plan.region_count += region_count
        plan.processed = True
        finish_work_unit(
            connection,
            run_id,
            work_key,
            result={"region_count": region_count},
        )
    except Exception as exc:
        plan.engine_errors += 1
        record_ocr_error(
            connection,
            plan.file_hash,
            run_id,
            annotation_engine=annotation_engine,
            reader_provider=reader_provider,
            reader_model=reader_model,
            exc=exc,
        )
        fail_work_unit(connection, run_id, work_key, _error_detail(exc))
        log(f"{annotation_engine} failed for {plan.path}: {exc}")


def _run_infinity_step(  # noqa: PLR0913
    connection: DuckConnection,
    plan: FileExecutionPlan,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    *,
    lease: bool,
) -> None:
    work_key = _work_key("annotation", INFINITY_ENGINE, plan.file_hash)
    start_work_unit(connection, run_id, work_key)
    try:
        regions = process_infinity(
            connection,
            plan.path,
            plan.file_hash,
            run_id,
            options,
            log,
            lease_lmstudio=lease,
        )
        plan.region_count += regions
        plan.processed = True
        finish_work_unit(connection, run_id, work_key, result={"region_count": regions})
    except Exception as exc:
        plan.engine_errors += 1
        record_ocr_error(
            connection,
            plan.file_hash,
            run_id,
            annotation_engine=INFINITY_ENGINE,
            reader_provider="local-infinity-parser2",
            reader_model=options.infinity_model,
            exc=exc,
        )
        fail_work_unit(connection, run_id, work_key, _error_detail(exc))
        log(f"Infinity Parser2 failed for {plan.path}: {exc}")


def _fail_markdown_group(  # noqa: PLR0913
    connection: DuckConnection,
    plans: list[FileExecutionPlan],
    run_id: int,
    markdown_engines: list[str],
    exc: Exception,
    log: Callable[[str], None],
) -> None:
    log(f"Page Markdown model batch failed before execution: {_error_detail(exc)}")
    for plan in plans:
        for markdown_engine in markdown_engines:
            plan.engine_errors += 1
            fail_work_unit(
                connection,
                run_id,
                _work_key("markdown", markdown_engine, plan.file_hash),
                _error_detail(exc),
            )


def _run_markdown_engines(  # noqa: PLR0913
    connection: DuckConnection,
    plans: list[FileExecutionPlan],
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    markdown_engines: list[str],
    *,
    context_info: LmStudioContextInfo | None = None,
    lease_lmstudio: bool = True,
) -> None:
    for plan in plans:
        for markdown_engine in markdown_engines:
            work_key = _work_key("markdown", markdown_engine, plan.file_hash)
            start_work_unit(connection, run_id, work_key)
            try:
                summary = process_page_markdown(
                    connection,
                    plan.path,
                    plan.file_hash,
                    run_id,
                    options,
                    log,
                    context_info,
                    markdown_engines=[markdown_engine],
                    lease_lmstudio=lease_lmstudio,
                )
                if summary.error_count:
                    plan.engine_errors += summary.error_count
                    fail_work_unit(
                        connection,
                        run_id,
                        work_key,
                        f"{summary.error_count} page Markdown page(s) failed",
                        result={
                            "page_count": summary.page_count,
                            "error_count": summary.error_count,
                            "errors": summary.errors or [],
                        },
                    )
                else:
                    finish_work_unit(
                        connection,
                        run_id,
                        work_key,
                        result={"page_count": summary.page_count},
                    )
                plan.processed = True
            except Exception as exc:
                plan.engine_errors += 1
                fail_work_unit(connection, run_id, work_key, _error_detail(exc))
                log(
                    f"Page Markdown generation failed for {plan.path}: {_error_detail(exc)}"
                )


def _upsert_file_work_unit(  # noqa: PLR0913
    connection: DuckConnection,
    run_id: int,
    plan: FileExecutionPlan,
    *,
    phase: str,
    engine: str,
    provider: str,
    model: str,
    execution_key: str,
    profile: str | None = None,
) -> None:
    upsert_work_unit(
        connection,
        WorkUnit(
            ingest_run_id=run_id,
            work_key=_work_key(phase, engine, plan.file_hash, profile=profile),
            file_hash=plan.file_hash,
            phase=phase,
            engine=engine,
            provider=provider,
            model=model,
            profile=profile,
            execution_key=execution_key,
            metadata={"source_path": str(plan.path)},
        ),
    )


def _record_preview_artifacts(
    connection: DuckConnection,
    run_id: int,
    file_hash: str,
) -> None:
    for image in read_document_preview_images(connection, file_hash):
        upsert_page_artifact(
            connection,
            PageArtifact(
                ingest_run_id=run_id,
                file_hash=file_hash,
                page_no=image.page_no,
                variant=f"preview:{image.variant}",
                page_width=image.page_width,
                page_height=image.page_height,
                render_width=image.render_width,
                render_height=image.render_height,
                mime_type=image.mime_type,
                image_sha256=image.image_sha256,
                cache_path=image.cache_path,
                source_variant=image.variant,
                metadata=image.metadata,
            ),
        )


@contextmanager
def _recorded_lmstudio_lease(  # noqa: PLR0913
    connection: DuckConnection,
    *,
    run_id: int,
    execution_key: str,
    model: str,
    base_url: str,
    timeout_seconds: float,
    enabled: bool,
    log: Callable[[str], None],
) -> Any:
    lease_id = start_model_lease(
        connection,
        ingest_run_id=run_id,
        execution_key=execution_key,
        provider="lmstudio",
        model=model,
        requested_context_tokens=supported_lmstudio_model_max_context(model),
        metadata={
            "base_url": base_url,
            "generation_parameters": _lmstudio_generation_parameters(),
        },
    )
    context_info: LmStudioContextInfo | None = None
    try:
        with lmstudio_model_lease(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
            log=log,
        ) as lease_context:
            context_info = lease_context
            yield lease_context
        finish_model_lease(
            connection,
            lease_id,
            status="ok",
            verified_context_tokens=(
                context_info.effective_context_tokens if context_info else None
            ),
            metadata={
                **_lmstudio_lease_metadata(base_url, context_info),
            },
        )
    except Exception as exc:
        finish_model_lease(
            connection,
            lease_id,
            status="error",
            verified_context_tokens=(
                context_info.effective_context_tokens if context_info else None
            ),
            error=_error_detail(exc),
            metadata={
                **_lmstudio_lease_metadata(base_url, context_info, fallback="error"),
            },
        )
        raise


def _lmstudio_generation_parameters() -> dict[str, object]:
    return {"repeat_penalty": DEFAULT_LMSTUDIO_REPEAT_PENALTY}


def _lmstudio_lease_metadata(
    base_url: str,
    context_info: LmStudioContextInfo | None,
    *,
    fallback: str = "disabled",
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "base_url": base_url,
        "generation_parameters": _lmstudio_generation_parameters(),
        "load_status": context_info.load_status if context_info else fallback,
    }
    if context_info is not None:
        metadata.update(
            {
                "native_base_url": context_info.native_base_url,
                "max_context_tokens": context_info.max_context_tokens,
                "loaded_context_tokens": context_info.loaded_context_tokens,
                "applied_context_tokens": context_info.applied_context_tokens,
                "requested_repeat_penalty": context_info.requested_repeat_penalty,
            }
        )
    return metadata


def _engine_identity(  # noqa: PLR0911
    engine: str,
    options: IngestOptions,
) -> tuple[str, str, str]:
    if engine == "docling":
        return "local-docling", "docling", "local:docling"
    if engine == DOCLING_NORMALIZED_ENGINE:
        return "local-docling", "docling-normalized-jpg", "local:docling_normalized"
    if engine == "mineru":
        model = f"mineru-{options.mineru_backend}"
        return "local-mineru", model, f"local:mineru:{options.mineru_backend}"
    if engine == MINERU_NORMALIZED_ENGINE:
        model = f"mineru-{options.mineru_backend}-normalized-jpg"
        return (
            "local-mineru",
            model,
            f"local:mineru_normalized:{options.mineru_backend}",
        )
    if engine == INFINITY_ENGINE:
        infinity_options = InfinityOptions(
            model=options.infinity_model,
            backend=options.infinity_backend,
            batch_size=options.infinity_batch_size,
            device=options.infinity_device,
            torch_dtype=options.infinity_torch_dtype,
        )
        provider = "local-infinity-parser2"
        execution_key = (
            _lmstudio_execution_key(options.lmstudio_base_url, infinity_options.model)
            if infinity_options.backend == "lmstudio"
            else f"local:infinity:{infinity_options.backend}:{infinity_options.model}"
        )
        return provider, infinity_options.model, execution_key
    return "local", engine, f"local:{engine}"


def _markdown_identity(  # noqa: PLR0911
    markdown_engine: str,
    options: IngestOptions,
) -> tuple[str, str, str]:
    if markdown_engine == INFINITY_MARKDOWN_ENGINE:
        infinity_options = InfinityOptions(
            model=options.infinity_model,
            backend=options.infinity_backend,
            batch_size=options.infinity_batch_size,
            device=options.infinity_device,
            torch_dtype=options.infinity_torch_dtype,
        )
        execution_key = (
            _lmstudio_execution_key(options.lmstudio_base_url, infinity_options.model)
            if infinity_options.backend == "lmstudio"
            else f"local:infinity_markdown:{infinity_options.backend}:{infinity_options.model}"
        )
        return "local-infinity-parser2", infinity_options.model, execution_key
    if markdown_engine == MARKITDOWN_CU_MARKDOWN_ENGINE:
        return (
            "azure-content-understanding",
            "markitdown-content-understanding",
            "local:markitdown_cu",
        )
    return "local-markitdown", "markitdown-ocr", "local:markitdown"


def _lmstudio_execution_key(base_url: str, model: str) -> str:
    return f"lmstudio:{base_url.rstrip('/')}:{model}"


def _work_key(
    phase: str,
    engine: str,
    file_hash: str,
    *,
    profile: str | None = None,
) -> str:
    profile_part = f":{profile}" if profile else ""
    return f"{phase}:{engine}{profile_part}:{file_hash}"


def _process_docling(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    config: RuntimeConfig,
    options: IngestOptions,
    log: Callable[[str], None],
) -> tuple[int, int]:
    log(
        "Reading with Docling: "
        f"{path} device={options.docling_device} "
        f"threads={options.docling_num_threads} "
        f"page_batch={options.docling_page_batch_size} "
        f"ocr_batch={options.docling_ocr_batch_size} "
        f"layout_batch={options.docling_layout_batch_size} "
        f"table_batch={options.docling_table_batch_size}"
    )
    with traced_span(
        "trapo.ingest.docling_read",
        attributes={
            "file.hash": file_hash,
            "docling.device": options.docling_device,
            "docling.num_threads": options.docling_num_threads,
            "docling.page_batch_size": options.docling_page_batch_size,
            "docling.ocr_batch_size": options.docling_ocr_batch_size,
            "docling.layout_batch_size": options.docling_layout_batch_size,
            "docling.table_batch_size": options.docling_table_batch_size,
            "docling.queue_max_size": options.docling_queue_max_size,
        },
    ):
        read_result = read_document(
            path,
            config,
            options=_docling_reader_options(options),
        )
    connection.execute(
        """
        INSERT OR REPLACE INTO docling_documents
            (
                file_hash, ingest_run_id, text, docling_json, status, error,
                reader_provider, reader_model
            )
        VALUES (?, ?, ?, ?::JSON, 'ok', NULL, ?, ?)
        """,
        [
            file_hash,
            run_id,
            read_result.text,
            json.dumps(read_result.data),
            read_result.provider,
            read_result.model,
        ],
    )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine="docling",
        text=read_result.text,
        output_json=read_result.data,
        reader_provider=read_result.provider,
        reader_model=read_result.model,
        metadata={
            "device": options.docling_device,
            "num_threads": options.docling_num_threads,
            "page_batch_size": options.docling_page_batch_size,
            "ocr_batch_size": options.docling_ocr_batch_size,
            "layout_batch_size": options.docling_layout_batch_size,
            "table_batch_size": options.docling_table_batch_size,
            "queue_max_size": options.docling_queue_max_size,
        },
    )
    _delete_existing_chunks(connection, file_hash)
    with traced_span(
        "trapo.ingest.chunk_document",
        attributes={"file.hash": file_hash, "chunker": options.chunker},
    ):
        chunk_records = _chunk_records(read_result, options)
    for index, (chunk, metadata) in enumerate(chunk_records):
        _insert_chunk(connection, file_hash, index, chunk, metadata)
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={"file.hash": file_hash, "annotation.engine": "docling"},
    ) as region_span:
        region_count = rebuild_document_regions(connection, file_hash)
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored Docling: chunks={len(chunk_records)} regions={region_count}")
    return len(chunk_records), region_count


def _docling_reader_options(options: IngestOptions) -> DoclingReaderOptions:
    return DoclingReaderOptions(
        device=options.docling_device,
        num_threads=options.docling_num_threads,
        page_batch_size=options.docling_page_batch_size,
        ocr_batch_size=options.docling_ocr_batch_size,
        layout_batch_size=options.docling_layout_batch_size,
        table_batch_size=options.docling_table_batch_size,
        queue_max_size=options.docling_queue_max_size,
    )


def _chunk_records(
    read_result: DoclingReadResult,
    options: IngestOptions,
) -> list[tuple[str, dict[str, Any]]]:
    if options.chunker == "docling-hybrid":
        return chunk_docling_document(
            read_result.document,
            max_tokens=options.max_chunk_tokens,
        )
    if options.chunker == "chars":
        return [
            (chunk, {"chunker": "char-v1"})
            for chunk in chunk_text(
                read_result.text,
                max_chars=options.max_chars,
                overlap_chars=options.overlap_chars,
            )
        ]
    raise ValueError(f"Unsupported chunker: {options.chunker}")


def _options_json(options: IngestOptions) -> dict[str, object]:
    return dict(options.__dict__)


def _process_preview_cache(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    log: Callable[[str], None],
) -> int:
    overrides = read_page_orientation_overrides(connection, file_hash)
    images = build_document_preview_cache(
        connection,
        path,
        file_hash,
        options=PreviewCacheOptions(
            rotation_degrees_by_page={
                page_no: override.clockwise_degrees
                for page_no, override in overrides.items()
            },
            log=log,
        ),
    )
    return len(images)


def _preview_cache_complete(connection: DuckConnection, file_hash: str) -> bool:
    images = read_document_preview_images(connection, file_hash)
    return bool(images) and all(image.cache_path.exists() for image in images)


def _logger(verbosity: int) -> Callable[[str], None]:
    def log(message: str) -> None:
        log_progress(message, verbosity=verbosity)

    return log


def _error_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return f"{exc}; response={text[:1000]}"
    return str(exc)


def _upsert_file(
    connection: DuckConnection, path: Path, file_hash: str, size: int, mtime: float
) -> None:
    connection.execute(
        """
        INSERT INTO files (file_hash, filename, extension, size_bytes, modified_at, last_seen_at)
        VALUES (?, ?, ?, ?, to_timestamp(?), now())
        ON CONFLICT (file_hash) DO UPDATE SET
            filename = excluded.filename,
            extension = excluded.extension,
            size_bytes = excluded.size_bytes,
            modified_at = excluded.modified_at,
            last_seen_at = now()
        """,
        [file_hash, path.name, path.suffix.lower() or None, size, mtime],
    )
    connection.execute(
        """
        INSERT INTO file_locations (file_hash, path, last_seen_at)
        VALUES (?, ?, now())
        ON CONFLICT (file_hash, path) DO UPDATE SET last_seen_at = now()
        """,
        [file_hash, str(path)],
    )


def _insert_chunk(
    connection: DuckConnection,
    file_hash: str,
    index: int,
    text: str,
    metadata: dict[str, object],
) -> int:
    chunk_id = next_table_id(
        connection,
        table_name="document_chunks",
        column_name="chunk_id",
        sequence_name="chunk_id_seq",
    )
    connection.execute(
        """
        INSERT INTO document_chunks
            (chunk_id, file_hash, chunk_index, text, char_count, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?::JSON)
        """,
        [chunk_id, file_hash, index, text, len(text), json.dumps(metadata)],
    )
    return chunk_id


def _supported_engines(path: Path, options: IngestOptions) -> list[str]:
    if path.suffix.lower() not in PREVIEW_EXTENSIONS:
        return []
    return [
        engine
        for engine in _requested_engines(options.annotation_engines)
        if engine
        in {
            "docling",
            "mineru",
            INFINITY_ENGINE,
            DOCLING_NORMALIZED_ENGINE,
            MINERU_NORMALIZED_ENGINE,
        }
    ]


def _requested_engines(value: str) -> list[str]:
    raw_engines = [part.strip().lower() for part in value.split(",")]
    engines: list[str] = []
    for engine in raw_engines:
        normalized = "docling" if engine in {"docling", "local-docling"} else engine
        normalized = (
            DOCLING_NORMALIZED_ENGINE
            if normalized
            in {
                "docling-normalized",
                "docling_normalized",
                "local-docling-normalized",
            }
            else normalized
        )
        normalized = (
            "mineru" if normalized in {"mineru", "local-mineru"} else normalized
        )
        normalized = (
            MINERU_NORMALIZED_ENGINE
            if normalized
            in {
                "mineru-normalized",
                "mineru_normalized",
                "local-mineru-normalized",
            }
            else normalized
        )
        normalized = (
            INFINITY_ENGINE
            if normalized
            in {
                "infinity",
                "infinity-parser2",
                "local-infinity",
                "local-infinity-parser2",
            }
            else normalized
        )
        if normalized == "all":
            for default_engine in ("docling", "mineru", INFINITY_ENGINE):
                if default_engine not in engines:
                    engines.append(default_engine)
            continue
        if normalized == "normalized":
            for normalized_engine in (
                DOCLING_NORMALIZED_ENGINE,
                MINERU_NORMALIZED_ENGINE,
            ):
                if normalized_engine not in engines:
                    engines.append(normalized_engine)
            continue
        if (
            normalized
            in {
                "docling",
                "mineru",
                INFINITY_ENGINE,
                DOCLING_NORMALIZED_ENGINE,
                MINERU_NORMALIZED_ENGINE,
            }
            and normalized not in engines
        ):
            engines.append(normalized)
    return engines or ["docling"]


def _engine_complete(
    connection: DuckConnection,
    file_hash: str,
    annotation_engine: str,
    options: IngestOptions,
) -> bool:
    if annotation_engine == "docling":
        return _docling_complete(connection, file_hash)
    del options
    return _ocr_engine_complete(connection, file_hash, annotation_engine)


def _ocr_engine_complete(
    connection: DuckConnection, file_hash: str, annotation_engine: str
) -> bool:
    if not table_exists(connection, "ocr_documents"):
        return False
    row = connection.execute(
        """
        SELECT status
        FROM ocr_documents
        WHERE file_hash = ? AND annotation_engine = ?
        """,
        [file_hash, annotation_engine],
    ).fetchone()
    return bool(row and str(row[0]) == "ok")


def _delete_existing_chunks(connection: DuckConnection, file_hash: str) -> None:
    if table_exists(connection, "document_terms"):
        connection.execute(
            "DELETE FROM document_terms WHERE file_hash = ? AND annotation_engine = 'docling'",
            [file_hash],
        )
    if table_exists(connection, "document_regions"):
        connection.execute(
            "DELETE FROM document_regions WHERE file_hash = ? AND annotation_engine = 'docling'",
            [file_hash],
        )
    connection.execute("DELETE FROM document_chunks WHERE file_hash = ?", [file_hash])


def _docling_complete(connection: DuckConnection, file_hash: str) -> bool:
    row = connection.execute(
        "SELECT status FROM docling_documents WHERE file_hash = ?",
        [file_hash],
    ).fetchone()
    if not row or str(row[0]) != "ok":
        return False
    chunk_row = connection.execute(
        "SELECT count(*) FROM document_chunks WHERE file_hash = ?",
        [file_hash],
    ).fetchone()
    return bool(chunk_row and int(chunk_row[0]) > 0)
