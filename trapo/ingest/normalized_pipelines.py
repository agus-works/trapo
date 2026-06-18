from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trapo.annotation.docling.regions import rebuild_docling_output_regions
from trapo.annotation.mineru.regions import rebuild_mineru_document_regions
from trapo.db import DuckConnection
from trapo.ingest.docling_reader import DoclingReaderOptions, read_with_docling_batch
from trapo.ingest.mineru_reader import read_with_mineru_batch
from trapo.ingest.normalized_outputs import (
    combined_docling_output,
    combined_mineru_output,
)
from trapo.ingest.normalized_pages import (
    normalized_metadata,
    normalized_preview_pages,
)
from trapo.ingest.ocr_storage import record_ocr_success
from trapo.ingest.options import IngestOptions
from trapo.observability import span_set_attributes, traced_span

DOCLING_NORMALIZED_ENGINE = "docling_normalized"
MINERU_NORMALIZED_ENGINE = "mineru_normalized"


def process_docling_normalized(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    with traced_span(
        "trapo.ingest.normalized_pages",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": DOCLING_NORMALIZED_ENGINE,
        },
    ) as pages_span:
        pages = normalized_preview_pages(connection, path, file_hash, log)
        span_set_attributes(pages_span, {"page.count": len(pages)})
    if not pages:
        raise ValueError(f"No normalized preview pages were rendered for: {path}")
    log(f"Reading normalized JPGs with Docling: {path} pages={len(pages)}")
    with traced_span(
        "trapo.ingest.docling_normalized_read",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": DOCLING_NORMALIZED_ENGINE,
            "page.count": len(pages),
            "docling.device": options.docling_device,
            "docling.num_threads": options.docling_num_threads,
            "docling.page_batch_size": options.docling_page_batch_size,
            "docling.ocr_batch_size": options.docling_ocr_batch_size,
            "docling.layout_batch_size": options.docling_layout_batch_size,
            "docling.table_batch_size": options.docling_table_batch_size,
            "docling.queue_max_size": options.docling_queue_max_size,
        },
    ):
        results = read_with_docling_batch(
            [page.image_path for page in pages],
            options=_docling_reader_options(options),
        )
    text, output_json = combined_docling_output(pages, results, source_path=path)
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine=DOCLING_NORMALIZED_ENGINE,
        text=text,
        output_json=output_json,
        reader_provider="local-docling",
        reader_model="docling-normalized-jpg",
        metadata=normalized_metadata(pages),
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": DOCLING_NORMALIZED_ENGINE,
        },
    ) as region_span:
        region_count = rebuild_docling_output_regions(
            connection,
            file_hash,
            output_json,
            annotation_engine=DOCLING_NORMALIZED_ENGINE,
            annotation_provider="local-docling",
            annotation_model="docling-normalized-jpg",
            metadata_source=DOCLING_NORMALIZED_ENGINE,
            link_chunks=False,
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored normalized Docling: pages={len(pages)} regions={region_count}")
    return region_count


def process_mineru_normalized(  # noqa: PLR0913
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    run_id: int,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    with traced_span(
        "trapo.ingest.normalized_pages",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": MINERU_NORMALIZED_ENGINE,
        },
    ) as pages_span:
        pages = normalized_preview_pages(connection, path, file_hash, log)
        span_set_attributes(pages_span, {"page.count": len(pages)})
    if not pages:
        raise ValueError(f"No normalized preview pages were rendered for: {path}")
    log(
        "Reading normalized JPGs with MinerU: "
        f"{path} pages={len(pages)} backend={options.mineru_backend}"
    )
    with traced_span(
        "trapo.ingest.mineru_normalized_read",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": MINERU_NORMALIZED_ENGINE,
            "page.count": len(pages),
            "mineru.backend": options.mineru_backend,
            "mineru.parse_method": options.mineru_parse_method,
            "mineru.processing_window_size": options.mineru_processing_window_size,
        },
    ):
        results = read_with_mineru_batch(
            [page.image_path for page in pages],
            backend=options.mineru_backend,
            parse_method=options.mineru_parse_method,
            language=options.mineru_language,
            formula_enable=True,
            table_enable=True,
            processing_window_size=options.mineru_processing_window_size,
        )
    text, output_json = combined_mineru_output(
        pages, results, options=options, source_path=path
    )
    record_ocr_success(
        connection,
        file_hash,
        run_id,
        annotation_engine=MINERU_NORMALIZED_ENGINE,
        text=text,
        output_json=output_json,
        reader_provider="local-mineru",
        reader_model=f"mineru-{options.mineru_backend}-normalized-jpg",
        metadata=normalized_metadata(pages),
    )
    with traced_span(
        "trapo.ingest.rebuild_regions",
        attributes={
            "file.hash": file_hash,
            "annotation.engine": MINERU_NORMALIZED_ENGINE,
        },
    ) as region_span:
        region_count = rebuild_mineru_document_regions(
            connection,
            file_hash,
            output_json,
            target_pages=[page.page for page in pages],
            annotation_engine=MINERU_NORMALIZED_ENGINE,
            annotation_provider="local-mineru",
            annotation_model=f"mineru-{options.mineru_backend}-normalized-jpg",
        )
        span_set_attributes(region_span, {"region.count": region_count})
    log(f"Stored normalized MinerU: pages={len(pages)} regions={region_count}")
    return region_count


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
