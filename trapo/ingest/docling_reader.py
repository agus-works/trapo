from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.ingest.options import (
    DEFAULT_DOCLING_BATCH_SIZE,
    DEFAULT_DOCLING_QUEUE_MAX_SIZE,
)
from trapo.logging_filters import suppress_noisy_pdf_stderr


@dataclass(frozen=True)
class DoclingReadResult:
    text: str
    data: dict[str, Any]
    document: Any
    provider: str = "local-docling"
    model: str = "docling"


@dataclass(frozen=True)
class DoclingReaderOptions:
    device: str = "auto"
    num_threads: int = 4
    page_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    ocr_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    layout_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    table_batch_size: int = DEFAULT_DOCLING_BATCH_SIZE
    queue_max_size: int = DEFAULT_DOCLING_QUEUE_MAX_SIZE

    def normalized(self) -> DoclingReaderOptions:
        return DoclingReaderOptions(
            device=self.device,
            num_threads=max(1, self.num_threads),
            page_batch_size=max(1, self.page_batch_size),
            ocr_batch_size=max(1, self.ocr_batch_size),
            layout_batch_size=max(1, self.layout_batch_size),
            table_batch_size=max(1, self.table_batch_size),
            queue_max_size=max(1, self.queue_max_size),
        )


# Docling caches initialized pipelines (and their loaded model weights) per
# DocumentConverter instance. Reusing one converter across an ingest run means
# the OCR/layout/table weights load once instead of once per file. Cache by the
# accelerator and batch options because they are baked into pipeline instances.
_CONVERTER_CACHE: dict[DoclingReaderOptions, Any] = {}
_CONVERTER_LOCK = threading.Lock()


def _build_converter(options: DoclingReaderOptions) -> Any:
    # Docling imports initialize heavy OCR/model plumbing; defer until ingest needs it.
    from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
    from docling.document_converter import (  # noqa: PLC0415
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    normalized_options = options.normalized()
    pdf_pipeline_options = _pipeline_options(normalized_options)
    image_pipeline_options = _pipeline_options(normalized_options)
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_pipeline_options),
            InputFormat.IMAGE: ImageFormatOption(
                pipeline_options=image_pipeline_options
            ),
        }
    )


def _pipeline_options(options: DoclingReaderOptions) -> Any:
    from docling.datamodel.pipeline_options import (  # noqa: PLC0415
        AcceleratorOptions,
        PdfPipelineOptions,
    )

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = AcceleratorOptions(
        device=options.device,
        num_threads=options.num_threads,
    )
    pipeline_options.ocr_batch_size = options.ocr_batch_size
    pipeline_options.layout_batch_size = options.layout_batch_size
    pipeline_options.table_batch_size = options.table_batch_size
    pipeline_options.queue_max_size = options.queue_max_size
    return pipeline_options


def get_converter(options: DoclingReaderOptions | None = None) -> Any:
    """Return a cached DocumentConverter so model weights load once per run."""
    key = (options or DoclingReaderOptions()).normalized()
    converter = _CONVERTER_CACHE.get(key)
    if converter is None:
        with _CONVERTER_LOCK:
            converter = _CONVERTER_CACHE.get(key)
            if converter is None:
                converter = _build_converter(key)
                _CONVERTER_CACHE[key] = converter
    return converter


@contextmanager
def _docling_perf_scope(page_batch_size: int) -> Iterator[None]:
    from docling.datamodel.settings import settings, scoped  # noqa: PLC0415

    perf = settings.perf.model_copy(deep=True)
    perf.page_batch_size = max(1, page_batch_size)
    with scoped(perf=perf):
        yield


def read_with_docling(
    path: Path,
    *,
    options: DoclingReaderOptions | None = None,
) -> DoclingReadResult:
    reader_options = (options or DoclingReaderOptions()).normalized()
    converter = get_converter(reader_options)
    with (
        _docling_perf_scope(reader_options.page_batch_size),
        suppress_noisy_pdf_stderr(),
    ):
        return _read_result_from_conversion(path, converter.convert(path))


def read_with_docling_batch(
    paths: list[Path],
    *,
    options: DoclingReaderOptions | None = None,
) -> dict[Path, DoclingReadResult]:
    if not paths:
        return {}
    if len(set(paths)) != len(paths):
        raise ValueError("read_with_docling_batch expects unique file paths")
    reader_options = (options or DoclingReaderOptions()).normalized()
    converter = get_converter(reader_options)
    with (
        _docling_perf_scope(reader_options.page_batch_size),
        suppress_noisy_pdf_stderr(),
    ):
        return {
            path: _read_result_from_conversion(path, result)
            for path, result in zip(paths, converter.convert_all(paths), strict=True)
        }


def _read_result_from_conversion(path: Path, result: Any) -> DoclingReadResult:
    document = result.document
    text = ""
    if hasattr(document, "export_to_markdown"):
        text = str(document.export_to_markdown())
    elif hasattr(document, "export_to_text"):
        text = str(document.export_to_text())
    else:
        text = str(document)

    data: dict[str, Any] = {"source": str(path)}
    if hasattr(document, "export_to_dict"):
        exported = document.export_to_dict()
        if isinstance(exported, dict):
            data = exported
    return DoclingReadResult(text=text, data=data, document=document)
