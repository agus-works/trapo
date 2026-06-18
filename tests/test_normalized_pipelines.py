from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from trapo.config import RuntimeConfig
from trapo.db import DuckConnection, connect
from trapo.ingest import normalized_pipelines
from trapo.ingest.docling_reader import DoclingReaderOptions, DoclingReadResult
from trapo.ingest.mineru_reader import MinerUReadResult
from trapo.ingest.normalized_pipelines import (
    DOCLING_NORMALIZED_ENGINE,
    MINERU_NORMALIZED_ENGINE,
    process_docling_normalized,
    process_mineru_normalized,
)
from trapo.ingest.options import IngestOptions
from trapo.migrations import apply_migrations
from trapo.preview_cache import PreviewCacheOptions, build_document_preview_cache

EXPECTED_NORMALIZED_PAGE_COUNT = 2
DOCLING_TEST_THREADS = 2
DOCLING_TEST_QUEUE_MAX_SIZE = 8
MINERU_TEST_PROCESSING_WINDOW_SIZE = 16


def test_process_docling_normalized_reads_cached_pages_in_one_batch(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    source_path = _write_multipage_tiff(tmp_path / "source.tif")
    file_hash = "normalized-docling-hash"
    captured_paths: list[Path] = []

    def fake_read_with_docling_batch(
        paths: list[Path],
        *,
        options: DoclingReaderOptions,
    ) -> dict[Path, DoclingReadResult]:
        captured_paths.extend(paths)
        assert options.device == "cpu"
        assert options.num_threads == DOCLING_TEST_THREADS
        assert options.page_batch_size == 1
        assert options.ocr_batch_size == 1
        assert options.layout_batch_size == 1
        assert options.table_batch_size == 1
        assert options.queue_max_size == DOCLING_TEST_QUEUE_MAX_SIZE
        return {
            path: DoclingReadResult(
                text=f"Docling page {index}",
                data=_docling_page_output(index),
                document=object(),
            )
            for index, path in enumerate(paths, start=1)
        }

    monkeypatch.setattr(
        normalized_pipelines,
        "read_with_docling_batch",
        fake_read_with_docling_batch,
    )

    with connect(db_path) as connection:
        _prepare_normalized_fixture(
            connection, config, source_path, file_hash, tmp_path
        )

        inserted = process_docling_normalized(
            connection,
            source_path,
            file_hash,
            1,
            IngestOptions(
                docling_device="cpu", docling_num_threads=DOCLING_TEST_THREADS
            ),
            lambda _message: None,
        )
        rows = connection.execute(
            """
            SELECT annotation_engine, annotation_provider, annotation_model, page_no, text
            FROM document_regions
            WHERE file_hash = ?
            ORDER BY page_no
            """,
            [file_hash],
        ).fetchall()
        ocr_row = connection.execute(
            """
            SELECT status, reader_model, metadata_json
            FROM ocr_documents
            WHERE file_hash = ? AND annotation_engine = ?
            """,
            [file_hash, DOCLING_NORMALIZED_ENGINE],
        ).fetchone()

    assert len(captured_paths) == EXPECTED_NORMALIZED_PAGE_COUNT
    assert all(path.suffix == ".jpg" and path.exists() for path in captured_paths)
    assert inserted == EXPECTED_NORMALIZED_PAGE_COUNT
    assert [row[0] for row in rows] == [
        DOCLING_NORMALIZED_ENGINE,
        DOCLING_NORMALIZED_ENGINE,
    ]
    assert [row[3] for row in rows] == [1, 2]
    assert [row[4] for row in rows] == ["Docling page 1", "Docling page 2"]
    assert ocr_row is not None
    assert ocr_row[0] == "ok"
    assert ocr_row[1] == "docling-normalized-jpg"
    metadata = json.loads(str(ocr_row[2]))
    assert metadata["input"] == "normalized_preview_jpg"
    assert len(metadata["pages"]) == EXPECTED_NORMALIZED_PAGE_COUNT


def test_process_mineru_normalized_reads_cached_pages_in_one_batch(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    source_path = _write_multipage_tiff(tmp_path / "source.tif")
    file_hash = "normalized-mineru-hash"
    captured_paths: list[Path] = []

    def fake_read_with_mineru_batch(
        paths: list[Path],
        **kwargs: object,
    ) -> dict[Path, MinerUReadResult]:
        captured_paths.extend(paths)
        assert kwargs["backend"] == "pipeline"
        assert kwargs["parse_method"] == "auto"
        assert kwargs["language"] == "en"
        assert kwargs["formula_enable"] is True
        assert kwargs["table_enable"] is True
        assert kwargs["processing_window_size"] == MINERU_TEST_PROCESSING_WINDOW_SIZE
        return {
            path: MinerUReadResult(
                text=f"MinerU page {index}",
                data=_mineru_page_output(index),
                model="mineru-pipeline",
            )
            for index, path in enumerate(paths, start=1)
        }

    monkeypatch.setattr(
        normalized_pipelines,
        "read_with_mineru_batch",
        fake_read_with_mineru_batch,
    )

    with connect(db_path) as connection:
        _prepare_normalized_fixture(
            connection, config, source_path, file_hash, tmp_path
        )

        inserted = process_mineru_normalized(
            connection,
            source_path,
            file_hash,
            1,
            IngestOptions(mineru_backend="pipeline"),
            lambda _message: None,
        )
        rows = connection.execute(
            """
            SELECT annotation_engine, annotation_provider, annotation_model, page_no, text
            FROM document_regions
            WHERE file_hash = ?
            ORDER BY page_no
            """,
            [file_hash],
        ).fetchall()
        ocr_row = connection.execute(
            """
            SELECT status, reader_model, metadata_json
            FROM ocr_documents
            WHERE file_hash = ? AND annotation_engine = ?
            """,
            [file_hash, MINERU_NORMALIZED_ENGINE],
        ).fetchone()

    assert len(captured_paths) == EXPECTED_NORMALIZED_PAGE_COUNT
    assert all(path.suffix == ".jpg" and path.exists() for path in captured_paths)
    assert inserted == EXPECTED_NORMALIZED_PAGE_COUNT
    assert [row[0] for row in rows] == [
        MINERU_NORMALIZED_ENGINE,
        MINERU_NORMALIZED_ENGINE,
    ]
    assert [row[3] for row in rows] == [1, 2]
    assert [row[4] for row in rows] == ["MinerU page 1", "MinerU page 2"]
    assert ocr_row is not None
    assert ocr_row[0] == "ok"
    assert ocr_row[1] == "mineru-pipeline-normalized-jpg"
    metadata = json.loads(str(ocr_row[2]))
    assert metadata["input"] == "normalized_preview_jpg"
    assert len(metadata["pages"]) == EXPECTED_NORMALIZED_PAGE_COUNT


def _prepare_normalized_fixture(
    connection: DuckConnection,
    config: RuntimeConfig,
    source_path: Path,
    file_hash: str,
    tmp_path: Path,
) -> None:
    apply_migrations(connection, config, create_backup=False)
    connection.execute(
        "INSERT INTO ingest_runs (ingest_run_id, source_directory, status) VALUES (1, ?, 'done')",
        [str(source_path.parent)],
    )
    build_document_preview_cache(
        connection,
        source_path,
        file_hash,
        options=PreviewCacheOptions(cache_root=str(tmp_path / "preview-cache")),
    )


def _write_multipage_tiff(path: Path) -> Path:
    first = Image.new("RGB", (120, 80), "white")
    second = Image.new("RGB", (80, 120), "white")
    first.save(path, save_all=True, append_images=[second])
    return path


def _docling_page_output(page_no: int) -> dict[str, object]:
    return {
        "pages": {"1": {"page_no": 1, "size": {"width": 120.0, "height": 80.0}}},
        "texts": [
            {
                "self_ref": "#/texts/0",
                "label": "text",
                "text": f"Docling page {page_no}",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "left": 10.0,
                            "top": 20.0,
                            "right": 90.0,
                            "bottom": 40.0,
                            "coord_origin": "TOPLEFT",
                        },
                    }
                ],
            }
        ],
    }


def _mineru_page_output(page_no: int) -> dict[str, object]:
    return {
        "backend": "pipeline",
        "middle_json": {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [120.0, 80.0],
                }
            ]
        },
        "content_list": [
            {
                "type": "text",
                "text": f"MinerU page {page_no}",
                "bbox": [100, 100, 600, 300],
                "page_idx": 0,
            }
        ],
    }
