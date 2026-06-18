from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from docling.datamodel.base_models import InputFormat
from docling.document_converter import ImageFormatOption, PdfFormatOption

from trapo.ingest import docling_reader


DOCLING_TEST_THREADS = 2
DOCLING_TEST_QUEUE_MAX_SIZE = 3


def test_get_converter_caches_per_device(monkeypatch) -> None:
    docling_reader._CONVERTER_CACHE.clear()
    build_calls: list[docling_reader.DoclingReaderOptions] = []

    def fake_build(options: docling_reader.DoclingReaderOptions) -> object:
        build_calls.append(options)
        return object()

    monkeypatch.setattr(docling_reader, "_build_converter", fake_build)

    first = docling_reader.get_converter()
    second = docling_reader.get_converter()

    assert first is second
    assert build_calls == [docling_reader.DoclingReaderOptions()]


def test_get_converter_rebuilds_for_new_options(monkeypatch) -> None:
    docling_reader._CONVERTER_CACHE.clear()
    build_calls: list[docling_reader.DoclingReaderOptions] = []

    def fake_build(options: docling_reader.DoclingReaderOptions) -> object:
        build_calls.append(options)
        return object()

    monkeypatch.setattr(docling_reader, "_build_converter", fake_build)

    cpu = docling_reader.get_converter(
        docling_reader.DoclingReaderOptions(device="cpu")
    )
    cuda = docling_reader.get_converter(
        docling_reader.DoclingReaderOptions(device="cuda:0")
    )

    assert cpu is not cuda
    assert build_calls == [
        docling_reader.DoclingReaderOptions(device="cpu"),
        docling_reader.DoclingReaderOptions(device="cuda:0"),
    ]


def test_get_converter_rebuilds_for_batch_options(monkeypatch) -> None:
    docling_reader._CONVERTER_CACHE.clear()
    build_calls: list[docling_reader.DoclingReaderOptions] = []

    def fake_build(options: docling_reader.DoclingReaderOptions) -> object:
        build_calls.append(options)
        return object()

    monkeypatch.setattr(docling_reader, "_build_converter", fake_build)

    small = docling_reader.get_converter(
        docling_reader.DoclingReaderOptions(device="cpu", ocr_batch_size=1)
    )
    large = docling_reader.get_converter(
        docling_reader.DoclingReaderOptions(device="cpu", ocr_batch_size=2)
    )

    assert small is not large
    assert build_calls == [
        docling_reader.DoclingReaderOptions(device="cpu", ocr_batch_size=1),
        docling_reader.DoclingReaderOptions(device="cpu", ocr_batch_size=2),
    ]


def test_build_converter_configures_pdf_and_image_formats() -> None:
    converter = docling_reader._build_converter(
        docling_reader.DoclingReaderOptions(
            device="cpu",
            num_threads=DOCLING_TEST_THREADS,
            ocr_batch_size=1,
            layout_batch_size=1,
            table_batch_size=1,
            queue_max_size=DOCLING_TEST_QUEUE_MAX_SIZE,
        )
    )

    pdf_options = converter.format_to_options[InputFormat.PDF]
    image_options = converter.format_to_options[InputFormat.IMAGE]
    pdf_pipeline_options = cast(Any, pdf_options.pipeline_options)

    assert isinstance(pdf_options, PdfFormatOption)
    assert isinstance(image_options, ImageFormatOption)
    assert pdf_options.pipeline_options is not None
    assert image_options.pipeline_options is not None
    assert pdf_options.pipeline_options.accelerator_options.device == "cpu"
    assert image_options.pipeline_options.accelerator_options.device == "cpu"
    assert (
        image_options.pipeline_options.accelerator_options.num_threads
        == DOCLING_TEST_THREADS
    )
    assert pdf_pipeline_options.ocr_batch_size == 1
    assert pdf_pipeline_options.layout_batch_size == 1
    assert pdf_pipeline_options.table_batch_size == 1
    assert pdf_pipeline_options.queue_max_size == DOCLING_TEST_QUEUE_MAX_SIZE


def test_read_with_docling_batch_uses_convert_all(monkeypatch, tmp_path) -> None:
    first = tmp_path / "page-0001.jpg"
    second = tmp_path / "page-0002.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    converter = _FakeDoclingConverter()
    monkeypatch.setattr(
        docling_reader, "get_converter", lambda _options=None: converter
    )

    results = docling_reader.read_with_docling_batch(
        [first, second],
        options=docling_reader.DoclingReaderOptions(device="cpu", num_threads=2),
    )

    assert converter.paths == [first, second]
    assert list(results) == [first, second]
    assert results[first].text == f"markdown:{first.name}"
    assert results[second].data["source"] == str(second)


def test_read_with_docling_batch_rejects_duplicate_paths(tmp_path) -> None:
    sample = tmp_path / "page.jpg"
    sample.write_bytes(b"single")

    try:
        docling_reader.read_with_docling_batch([sample, sample])
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("Expected duplicate path validation to fail")


class _FakeDoclingConverter:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def convert_all(self, paths: list[Path]):
        self.paths = list(paths)
        return [_FakeDoclingConversion(path) for path in paths]


class _FakeDoclingConversion:
    def __init__(self, path: Path) -> None:
        self.document = _FakeDoclingDocument(path)


class _FakeDoclingDocument:
    def __init__(self, path: Path) -> None:
        self.path = path

    def export_to_markdown(self) -> str:
        return f"markdown:{self.path.name}"

    def export_to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.path),
            "pages": {"1": {"page_no": 1, "size": {"width": 10.0, "height": 20.0}}},
        }
