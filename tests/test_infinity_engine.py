from __future__ import annotations

import json

from pytest import approx

from trapo.annotation.infinity.regions import rebuild_infinity_document_regions
from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.document_markdown import INFINITY_MARKDOWN_ENGINE
from trapo.ingest.markdown_engines import requested_markdown_engines
from trapo.ingest.options import IngestOptions
from trapo.ingest.pipeline import _requested_engines
from trapo.migrations import apply_migrations

PIXEL_LEFT = 1200
PIXEL_TOP = 20
PIXEL_RIGHT = 1400
PIXEL_BOTTOM = 120


def test_requested_engines_all_includes_infinity() -> None:
    assert _requested_engines("all") == ["docling", "mineru", "lmstudio", "infinity"]
    assert _requested_engines("local-infinity-parser2") == ["infinity"]


def test_requested_markdown_engines_all_includes_infinity() -> None:
    engines = requested_markdown_engines(IngestOptions(page_markdown_engines="all"))

    assert INFINITY_MARKDOWN_ENGINE in engines
    assert engines.index(INFINITY_MARKDOWN_ENGINE) == 1


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
