from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trapo.annotation.infinity.regions import rebuild_infinity_document_regions
from trapo.annotation.mineru.regions import rebuild_mineru_document_regions
from trapo.db import DuckConnection
from trapo.ingest.infinity_models import (
    INFINITY_ENGINE,
    InfinityOptions,
)
from trapo.ingest.infinity_reader import read_regions_with_infinity
from trapo.ingest.lmstudio_lifecycle import lmstudio_model_lease
from trapo.ingest.mineru_reader import read_with_mineru
from trapo.ingest.normalized_pages import normalized_metadata, normalized_preview_pages
from trapo.ingest.ocr_storage import record_ocr_success
from trapo.ingest.options import IngestOptions
from trapo.ingest.target_pages import (
    target_pages_for_regions,
)
from trapo.observability import span_set_attributes, traced_span


def process_mineru(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    log(
        "Reading with MinerU: "
        f"{path} backend={options.mineru_backend} "
        f"method={options.mineru_parse_method} "
        f"window={options.mineru_processing_window_size}"
    )
    with traced_span(
        "trapo.ingest.mineru_read",
        attributes={
            "file.hash": file_hash,
            "mineru.backend": options.mineru_backend,
            "mineru.parse_method": options.mineru_parse_method,
            "mineru.processing_window_size": options.mineru_processing_window_size,
        },
    ):
        read_result = read_with_mineru(
            path,
            backend=options.mineru_backend,
            parse_method=options.mineru_parse_method,
            language=options.mineru_language,
            formula_enable=True,
            table_enable=True,
            processing_window_size=options.mineru_processing_window_size,
        )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine="mineru",
        text=read_result.text,
        output_json=read_result.data,
        reader_provider=read_result.provider,
        reader_model=read_result.model,
        metadata={
            "backend": options.mineru_backend,
            "parse_method": options.mineru_parse_method,
            "language": options.mineru_language,
            "processing_window_size": options.mineru_processing_window_size,
        },
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={"file.hash": file_hash, "annotation.engine": "mineru"},
    ) as region_span:
        region_count = rebuild_mineru_document_regions(
            connection,
            file_hash,
            read_result.data,
            target_pages=target_pages_for_regions(connection, path, file_hash),
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored MinerU: regions={region_count}")
    return region_count


def process_infinity(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
    *,
    lease_lmstudio: bool = True,
) -> int:
    with traced_span(
        "trapo.ingest.normalized_pages",
        attributes={"file.hash": file_hash, "annotation.engine": INFINITY_ENGINE},
    ) as pages_span:
        pages = normalized_preview_pages(connection, path, file_hash, log)
        span_set_attributes(pages_span, {"page.count": len(pages)})
    if not pages:
        raise ValueError(f"No normalized preview pages were rendered for: {path}")
    log(
        "Reading normalized JPGs with Infinity Parser2: "
        f"{path} pages={len(pages)} model={options.infinity_model} "
        f"backend={options.infinity_backend}"
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
        "trapo.ingest.infinity_read",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": INFINITY_ENGINE,
            "page.count": len(pages),
            "infinity.model": resolved_model,
            "infinity.backend": options.infinity_backend,
            "infinity.batch_size": options.infinity_batch_size,
        },
    ):
        if infinity_options.backend == "lmstudio" and lease_lmstudio:
            with lmstudio_model_lease(
                base_url=options.lmstudio_base_url,
                model=resolved_model,
                timeout_seconds=min(options.lmstudio_timeout_seconds, 60.0),
                enabled=options.lmstudio_maximize_context,
                log=log,
            ):
                read_result = read_regions_with_infinity(
                    pages,
                    source_path=path,
                    options=infinity_options,
                    log=log,
                )
        else:
            read_result = read_regions_with_infinity(
                pages,
                source_path=path,
                options=infinity_options,
                log=log,
            )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine=INFINITY_ENGINE,
        text=read_result.text,
        output_json=read_result.data,
        reader_provider=read_result.provider,
        reader_model=resolved_model,
        metadata={
            **normalized_metadata(pages),
            "model": resolved_model,
            "requested_model": options.infinity_model,
            "backend": options.infinity_backend,
            "batch_size": options.infinity_batch_size,
            "device": options.infinity_device,
            "torch_dtype": options.infinity_torch_dtype,
            "page_error_count": read_result.data.get("page_error_count", 0),
        },
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={"file.hash": file_hash, "annotation.engine": INFINITY_ENGINE},
    ) as region_span:
        region_count = rebuild_infinity_document_regions(
            connection,
            file_hash,
            read_result.data,
            annotation_model=resolved_model,
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored Infinity Parser2: pages={len(pages)} regions={region_count}")
    return region_count
