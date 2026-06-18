from __future__ import annotations

import json

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.lmstudio_pages import extract_lmstudio_pages
from trapo.lmstudio_regions import rebuild_lmstudio_document_regions
from trapo.migrations import apply_migrations

FIRST_PAGE_WIDTH = 100.0
SECOND_PAGE_HEIGHT = 792.0
BOTTOMLEFT_FLIPPED_TOP = 25.44
BOTTOMLEFT_FLIPPED_BOTTOM = 52.64


def test_rebuild_lmstudio_document_regions_uses_normalized_box_2d(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "model": "google/gemma-4-26b-a4b-qat",
        "box_2d_coord_origin": "TOPLEFT",
        "pages": [
            {
                "page_no": 1,
                "width": 200.0,
                "height": 100.0,
                "render_width": 1000,
                "render_height": 500,
                "regions": [
                    {
                        "label": "total",
                        "region_kind": "text",
                        "text": "Total 42.00",
                        "box_2d": [100, 250, 300, 750],
                        "confidence": 0.91,
                        "source_region_ids": ["docling-region"],
                    }
                ],
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_lmstudio_document_regions(connection, "file-1", output_json)
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
    assert row[0] == "lmstudio"
    assert row[1] == "local-lmstudio"
    assert row[2] == "google/gemma-4-26b-a4b-qat"
    assert row[3] == "text"
    assert row[4] == "Total 42.00"
    bbox = json.loads(str(row[5]))
    assert bbox == {
        "left": 50.0,
        "top": 10.0,
        "right": 150.0,
        "bottom": 30.0,
        "coord_origin": "TOPLEFT",
    }
    metadata = json.loads(str(row[6]))
    assert metadata["raw_item"]["source_region_ids"] == ["docling-region"]


def test_extract_lmstudio_pages_reads_page_sizes() -> None:
    pages = extract_lmstudio_pages(
        {
            "pages": [
                {"page_no": 2, "width": 612.0, "height": 792.0},
                {"page_no": 1, "width": 100.0, "height": 200.0},
            ]
        }
    )

    assert [page.page_no for page in pages] == [1, 2]
    assert pages[0].width == FIRST_PAGE_WIDTH
    assert pages[1].height == SECOND_PAGE_HEIGHT


def test_rebuild_lmstudio_document_regions_flips_bottomleft_box_origin(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "model": "google/gemma-4-26b-a4b-qat",
        "box_2d_coord_origin": "BOTTOMLEFT",
        "pages": [
            {
                "page_no": 1,
                "width": 320.0,
                "height": 160.0,
                "regions": [
                    {
                        "label": "total",
                        "region_kind": "text",
                        "text": "TOTAL 42.00",
                        "box_2d": [671, 44, 841, 955],
                    }
                ],
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_lmstudio_document_regions(connection, "file-1", output_json)
        row = connection.execute(
            """
            SELECT raw_bbox_json, metadata_json
            FROM document_regions
            WHERE file_hash = 'file-1'
            """
        ).fetchone()

    assert inserted == 1
    assert row is not None
    bbox = json.loads(str(row[0]))
    assert bbox["top"] == BOTTOMLEFT_FLIPPED_TOP
    assert bbox["bottom"] == BOTTOMLEFT_FLIPPED_BOTTOM
    metadata = json.loads(str(row[1]))
    assert metadata["box_2d_coord_origin"] == "BOTTOMLEFT"


def test_rebuild_lmstudio_document_regions_uses_profile_engine(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "engine": "lmstudio_strict",
        "model": "google/gemma-4-26b-a4b-qat",
        "prompt_profile": "strict",
        "box_2d_coord_origin": "TOPLEFT",
        "pages": [
            {
                "page_no": 1,
                "width": 200.0,
                "height": 100.0,
                "regions": [
                    {
                        "label": "strict text",
                        "region_kind": "text",
                        "text": "Strict text",
                        "box_2d": [100, 250, 300, 750],
                    }
                ],
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_lmstudio_document_regions(connection, "file-1", output_json)
        row = connection.execute(
            """
            SELECT annotation_engine, metadata_json
            FROM document_regions
            WHERE file_hash = 'file-1'
            """
        ).fetchone()

    assert inserted == 1
    assert row is not None
    assert row[0] == "lmstudio_strict"
    metadata = json.loads(str(row[1]))
    assert metadata["prompt_profile"] == "strict"
    assert metadata["annotation_engine"] == "lmstudio_strict"
