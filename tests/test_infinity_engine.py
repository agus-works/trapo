from __future__ import annotations

import json
from pathlib import Path

from pytest import approx

from trapo.annotation.infinity.regions import rebuild_infinity_document_regions
from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.document_markdown import INFINITY_MARKDOWN_ENGINE
from trapo.ingest.infinity_models import (
    DEFAULT_INFINITY_LMSTUDIO_MODEL,
    DEFAULT_INFINITY_MODEL,
    InfinityOptions,
    normalize_infinity_model,
)
from trapo.ingest.markdown_engines import requested_markdown_engines
from trapo.ingest.options import IngestOptions
from trapo.ingest.pipeline import _requested_engines
from trapo.ingest.infinity_uvx import UVX_SCRIPT, _uvx_command
from trapo.ingest.infinity_reader import read_page_markdown_with_infinity
from trapo.ingest.page_images import RenderedPageImage
from trapo.ingest.page_markdown_types import MarkdownPageImage
from trapo.migrations import apply_migrations

PIXEL_LEFT = 1200
PIXEL_TOP = 20
PIXEL_RIGHT = 1400
PIXEL_BOTTOM = 120
INFINITY_UVX_RUNTIME_DEPENDENCY_COUNT = 3
SECOND_PAGE_NO = 2


def test_requested_engines_all_includes_infinity() -> None:
    assert _requested_engines("all") == ["docling", "mineru", "infinity"]
    assert _requested_engines("local-infinity-parser2") == ["infinity"]


def test_requested_markdown_engines_all_includes_infinity() -> None:
    engines = requested_markdown_engines(IngestOptions(page_markdown_engines="all"))

    assert INFINITY_MARKDOWN_ENGINE in engines
    assert engines.index(INFINITY_MARKDOWN_ENGINE) == 0


def test_infinity_model_alias_resolves_flash_model() -> None:
    assert normalize_infinity_model("infinity-parser2-flash") == DEFAULT_INFINITY_MODEL
    assert InfinityOptions(model="infly/infinity-parser2-flash").model == (
        DEFAULT_INFINITY_MODEL
    )
    lmstudio_options = InfinityOptions(
        model="infly/Infinity-Parser2-Flash",
        backend="lm-studio",
    )
    assert lmstudio_options.backend == "lmstudio"
    assert lmstudio_options.model == DEFAULT_INFINITY_LMSTUDIO_MODEL


def test_infinity_uvx_fallback_installs_vision_runtime() -> None:
    command = _uvx_command()

    assert command[:3] == ["uvx", "--from", "infinity-parser2"]
    assert command.count("--with") == INFINITY_UVX_RUNTIME_DEPENDENCY_COUNT
    assert "torch" in command
    assert "torchvision" in command
    assert "accelerate" in command
    assert "--torch-backend" in command


def test_infinity_uvx_fallback_uses_transformers_when_vllm_engine_requested() -> None:
    assert 'if backend == "vllm-engine":' in UVX_SCRIPT
    assert 'backend = "transformers"' in UVX_SCRIPT
    assert 'sys.modules["vllm"] = vllm_module' in UVX_SCRIPT


def test_rebuild_infinity_regions_scales_normalized_bbox(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "model": "infly/Infinity-Parser2-Flash",
        "pages": [
            {
                "page_no": 1,
                "width": 200.0,
                "height": 100.0,
                "result": {
                    "elements": [
                        {
                            "category": "table",
                            "bbox": [100, 200, 500, 400],
                            "text": "<table><tr><td>Total</td></tr></table>",
                        }
                    ]
                },
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_infinity_document_regions(connection, "file-1", output_json)
        row = connection.execute(
            """
            SELECT annotation_engine, annotation_provider, annotation_model,
                region_kind, text, raw_bbox_json, metadata_json
            FROM document_regions
            WHERE file_hash = 'file-1'
            """
        ).fetchone()

    assert inserted == 1
    assert row is not None
    assert row[0] == "infinity"
    assert row[1] == "local-infinity-parser2"
    assert row[2] == "infly/Infinity-Parser2-Flash"
    assert row[3] == "table"
    assert row[4] == "<table><tr><td>Total</td></tr></table>"
    bbox = json.loads(str(row[5]))
    assert bbox["left"] == approx(20.0)
    assert bbox["top"] == approx(20.0)
    assert bbox["right"] == approx(100.0)
    assert bbox["bottom"] == approx(40.0)
    metadata = json.loads(str(row[6]))
    assert metadata["source"] == "infinity_parser2_json"
    assert metadata["raw_item"]["category"] == "table"


def test_infinity_batch_failure_retries_atomic_pages(tmp_path) -> None:
    class FakeParser:
        def parse(self, source: object, **_kwargs: object) -> object:
            if isinstance(source, list):
                raise RuntimeError("batch failed")
            if str(source).endswith("page-2.jpg"):
                raise ValueError("page failed")
            return "# Page 1"

    page_1 = _markdown_page(tmp_path / "page-1.jpg", page_no=1)
    page_2 = _markdown_page(tmp_path / "page-2.jpg", page_no=2)
    outputs = read_page_markdown_with_infinity(
        [page_1, page_2],
        source_path=tmp_path / "source.pdf",
        options=InfinityOptions(batch_size=2),
        parser=FakeParser(),
    )

    assert [output["status"] for output in outputs] == ["ok", "error"]
    assert outputs[0]["page_no"] == 1
    assert outputs[0]["result"] == "# Page 1"
    assert outputs[1]["page_no"] == SECOND_PAGE_NO
    assert outputs[1]["error_type"] == "ValueError"
    assert outputs[1]["error"] == "page failed"


def test_rebuild_infinity_regions_accepts_pixel_bbox(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "pages": [
            {
                "page_no": 1,
                "width": 900.0,
                "height": 1200.0,
                "result": [
                    {
                        "category": "formula",
                        "bbox": [PIXEL_LEFT, PIXEL_TOP, PIXEL_RIGHT, PIXEL_BOTTOM],
                        "text": "$$x=y$$",
                    }
                ],
            }
        ]
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_infinity_document_regions(connection, "file-1", output_json)
        row = connection.execute(
            """
            SELECT region_kind, raw_bbox_json
            FROM document_regions
            WHERE file_hash = 'file-1'
            """
        ).fetchone()

    assert inserted == 1
    assert row is not None
    assert row[0] == "formula"
    bbox = json.loads(str(row[1]))
    assert bbox["left"] == PIXEL_LEFT
    assert bbox["top"] == PIXEL_TOP
    assert bbox["right"] == PIXEL_RIGHT
    assert bbox["bottom"] == PIXEL_BOTTOM


def _markdown_page(path: Path, *, page_no: int) -> MarkdownPageImage:
    path.write_bytes(b"fake-jpeg")
    rendered = RenderedPageImage(
        page_no=page_no,
        width=100.0,
        height=200.0,
        render_width=100,
        render_height=200,
        mime_type="image/jpeg",
        image_bytes=b"fake-jpeg",
        image_sha256=f"sha-{page_no}",
    )
    return MarkdownPageImage(
        page=rendered,
        cache_hit=False,
        image_path=path,
        metadata_path=None,
        metadata={"variant": "test"},
    )
