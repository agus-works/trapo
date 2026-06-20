from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trapo.assets import PREVIEW_EXTENSIONS
from trapo.annotation.docling.regions import rebuild_document_regions
from trapo.annotation.fusion import FUSION_MODEL, FUSION_PROVIDER
from trapo.config import RuntimeConfig
from trapo.db import DuckConnection, next_table_id, table_exists
from trapo.diagnostics import activate_diagnostic_run, deactivate_diagnostic_run
from trapo.hash import sha256_file
from trapo.ingest.chunking import chunk_docling_document, chunk_text
from trapo.ingest.docling_reader import DoclingReaderOptions, DoclingReadResult
from trapo.ingest.engine_steps import (
    lmstudio_profile_engines,
    pending_fusion_profiles,
    process_fusion,
    process_infinity,
    process_lmstudio_profiles,
    process_mineru,
)
from trapo.ingest.infinity_models import INFINITY_ENGINE
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
    process_lmstudio_orientation,
    should_run_lmstudio_orientation,
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
    if "lmstudio" in _requested_engines(options.annotation_engines):
        lmstudio_profile_engines(options)

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

    files_seen = 0
    files_processed = 0
    files_skipped = 0
    chunks_created = 0
    errors = 0

    for path in files:
        files_seen += 1
        file_hash = str(path)
        with traced_span(
            "trapo.ingest.file",
            attributes={
                "file.name": path.name,
                "file.extension": path.suffix.lower(),
                "ingest.file_index": files_seen,
                "ingest.file_count": len(files),
            },
        ) as file_span:
            try:
                log(f"[{files_seen}/{len(files)}] Hashing {path}")
                file_hash = sha256_file(path)
                stat = path.stat()
                span_set_attributes(
                    file_span,
                    {
                        "file.hash": file_hash,
                        "file.size_bytes": stat.st_size,
                    },
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
                    or not _preview_cache_complete(
                        connection,
                        file_hash,
                    )
                )
                pending_engines = [
                    engine
                    for engine in engines
                    if options.reprocess
                    or not _engine_complete(connection, file_hash, engine, options)
                ]
                requested_fusion_outputs = pending_fusion_profiles(
                    connection,
                    file_hash,
                    pending_engines=pending_engines,
                    options=options,
                )
                fusion_pending = bool(requested_fusion_outputs)
                markdown_pending = pending_page_markdown(
                    connection,
                    path,
                    file_hash,
                    pending_engines=pending_engines,
                    fusion_pending=fusion_pending,
                    options=options,
                )
                if (
                    not preview_cache_pending
                    and not pending_engines
                    and not fusion_pending
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

                file_chunk_count = 0
                file_region_count = 0
                file_engine_errors = 0
                file_preview_image_count = 0
                if should_run_lmstudio_orientation(path, pending_engines, options):
                    try:
                        process_lmstudio_orientation(
                            connection,
                            path,
                            file_hash,
                            options,
                            log,
                        )
                    except Exception as exc:
                        log(f"LM Studio orientation detection failed for {path}: {exc}")
                if "docling" in pending_engines:
                    try:
                        docling_chunks, docling_regions = _process_docling(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            config,
                            options,
                            log,
                        )
                        file_chunk_count += docling_chunks
                        file_region_count += docling_regions
                    except Exception as exc:
                        file_engine_errors += 1
                        record_docling_error(connection, file_hash, run_id, exc)
                        log(f"Docling failed for {path}: {exc}")
                with traced_span(
                    "trapo.ingest.docling_orientation_heuristic",
                    attributes={"file.hash": file_hash},
                ) as orientation_span:
                    heuristic_overrides = process_docling_orientation_heuristic(
                        connection,
                        path,
                        file_hash,
                        options,
                        log,
                    )
                    span_set_attributes(
                        orientation_span,
                        {"orientation.override_count": heuristic_overrides},
                    )
                if preview_cache_pending:
                    try:
                        with traced_span(
                            "trapo.ingest.preview_cache",
                            attributes={"file.hash": file_hash},
                        ) as preview_span:
                            file_preview_image_count = _process_preview_cache(
                                connection,
                                path,
                                file_hash,
                                log,
                            )
                            span_set_attributes(
                                preview_span,
                                {"preview.image_count": file_preview_image_count},
                            )
                    except Exception as exc:
                        file_engine_errors += 1
                        log(f"Preview cache rendering failed for {path}: {exc}")
                if DOCLING_NORMALIZED_ENGINE in pending_engines:
                    try:
                        docling_normalized_regions = process_docling_normalized(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            options,
                            log,
                        )
                        file_region_count += docling_normalized_regions
                    except Exception as exc:
                        file_engine_errors += 1
                        record_ocr_error(
                            connection,
                            file_hash,
                            run_id,
                            annotation_engine=DOCLING_NORMALIZED_ENGINE,
                            reader_provider="local-docling",
                            reader_model="docling-normalized-jpg",
                            exc=exc,
                        )
                        log(f"Normalized Docling failed for {path}: {exc}")
                if "mineru" in pending_engines:
                    try:
                        mineru_regions = process_mineru(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            options,
                            log,
                        )
                        file_region_count += mineru_regions
                    except Exception as exc:
                        file_engine_errors += 1
                        record_ocr_error(
                            connection,
                            file_hash,
                            run_id,
                            annotation_engine="mineru",
                            reader_provider="local-mineru",
                            reader_model=f"mineru-{options.mineru_backend}",
                            exc=exc,
                        )
                        log(f"MinerU failed for {path}: {exc}")
                if INFINITY_ENGINE in pending_engines:
                    try:
                        infinity_regions = process_infinity(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            options,
                            log,
                        )
                        file_region_count += infinity_regions
                    except Exception as exc:
                        file_engine_errors += 1
                        record_ocr_error(
                            connection,
                            file_hash,
                            run_id,
                            annotation_engine=INFINITY_ENGINE,
                            reader_provider="local-infinity-parser2",
                            reader_model=options.infinity_model,
                            exc=exc,
                        )
                        log(f"Infinity Parser2 failed for {path}: {exc}")
                if MINERU_NORMALIZED_ENGINE in pending_engines:
                    try:
                        mineru_normalized_regions = process_mineru_normalized(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            options,
                            log,
                        )
                        file_region_count += mineru_normalized_regions
                    except Exception as exc:
                        file_engine_errors += 1
                        record_ocr_error(
                            connection,
                            file_hash,
                            run_id,
                            annotation_engine=MINERU_NORMALIZED_ENGINE,
                            reader_provider="local-mineru",
                            reader_model=f"mineru-{options.mineru_backend}-normalized-jpg",
                            exc=exc,
                        )
                        log(f"Normalized MinerU failed for {path}: {exc}")
                if "lmstudio" in pending_engines:
                    lmstudio_summary = process_lmstudio_profiles(
                        connection,
                        path,
                        file_hash,
                        run_id,
                        options,
                        log,
                    )
                    file_region_count += lmstudio_summary.region_count
                    file_engine_errors += lmstudio_summary.error_count
                for fusion_profile in requested_fusion_outputs:
                    try:
                        fused_regions = process_fusion(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            fusion_profile,
                            log,
                        )
                        file_region_count += fused_regions
                    except Exception as exc:
                        file_engine_errors += 1
                        record_ocr_error(
                            connection,
                            file_hash,
                            run_id,
                            annotation_engine=fusion_profile.annotation_engine,
                            reader_provider=FUSION_PROVIDER,
                            reader_model=FUSION_MODEL,
                            exc=exc,
                        )
                        log(f"Region fusion failed for {path}: {exc}")

                if markdown_pending:
                    try:
                        markdown_summary = process_page_markdown(
                            connection,
                            path,
                            file_hash,
                            run_id,
                            options,
                            log,
                            None,
                        )
                        file_engine_errors += markdown_summary.error_count
                    except Exception as exc:
                        file_engine_errors += 1
                        log(
                            f"Page Markdown generation failed for {path}: {_error_detail(exc)}"
                        )

                if file_engine_errors:
                    errors += file_engine_errors
                if (
                    file_chunk_count
                    or file_region_count
                    or pending_engines
                    or markdown_pending
                    or file_preview_image_count
                ):
                    files_processed += 1
                log(
                    f"Stored OCR outputs for {path}; chunks={file_chunk_count}, "
                    f"regions={file_region_count}, preview_images={file_preview_image_count}, "
                    f"engine_errors={file_engine_errors}"
                )
                span_set_attributes(
                    file_span,
                    {
                        "ingest.status": "processed"
                        if file_engine_errors == 0
                        else "error",
                        "annotation.engines": ",".join(engines),
                        "chunk.count": file_chunk_count,
                        "region.count": file_region_count,
                        "preview.image_count": file_preview_image_count,
                        "engine.error_count": file_engine_errors,
                    },
                )
                chunks_created += file_chunk_count
            except Exception as exc:
                mark_span_error(file_span, exc)
                span_set_attributes(
                    file_span,
                    {
                        "file.hash": file_hash,
                        "ingest.status": "error",
                    },
                )
                log(f"Error while processing {path}: {exc}")
                errors += 1
                record_docling_error(connection, file_hash, run_id, exc)

    status = "ok" if errors == 0 else "completed_with_errors"
    connection.execute(
        """
        UPDATE ingest_runs
        SET finished_at = current_timestamp, status = ?, error = ?
        WHERE ingest_run_id = ?
        """,
        [status, f"{errors} OCR engine run(s) failed" if errors else None, run_id],
    )
    deactivate_diagnostic_run()
    return IngestSummary(
        files_seen=files_seen,
        files_processed=files_processed,
        files_skipped=files_skipped,
        chunks_created=chunks_created,
        errors=errors,
    )


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
            "lmstudio",
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
            "lmstudio"
            if normalized in {"lmstudio", "lm-studio", "local-lmstudio"}
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
            for default_engine in ("docling", "mineru", "lmstudio", INFINITY_ENGINE):
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
                "lmstudio",
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
    if annotation_engine == "lmstudio":
        return all(
            _ocr_engine_complete(connection, file_hash, profile_engine)
            for profile_engine in lmstudio_profile_engines(options)
        )
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
