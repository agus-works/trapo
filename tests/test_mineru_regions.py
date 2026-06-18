from __future__ import annotations

import json

from pytest import approx

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.migrations import apply_migrations
from trapo.mineru_regions import extract_mineru_pages, rebuild_mineru_document_regions
from trapo.server.models import PageInfo

EXPECTED_LEFT = 20.0
EXPECTED_TOP = 20.0
EXPECTED_RIGHT = 100.0
EXPECTED_BOTTOM = 40.0
EXPECTED_FIRST_PAGE_WIDTH = 100.0
EXPECTED_SECOND_PAGE_HEIGHT = 792.0


def test_rebuild_mineru_document_regions_uses_content_list_bbox_scale(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "backend": "pipeline",
        "middle_json": {
            "pdf_info": [
                {
                    "page_idx": 0,
                    "page_size": [200.0, 100.0],
                }
            ]
        },
        "content_list": [
            {
                "type": "equation",
                "text": "$$x = y$$",
                "text_format": "latex",
                "bbox": [100, 200, 500, 400],
                "page_idx": 0,
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_mineru_document_regions(connection, "file-1", output_json)
        rows = connection.execute(
            """
            SELECT annotation_engine, region_kind, text, raw_bbox_json
            FROM document_regions
            WHERE file_hash = 'file-1'
            """
        ).fetchall()
        term_row = connection.execute(
            "SELECT count(*) FROM document_terms WHERE file_hash = 'file-1'"
        ).fetchone()

    assert inserted == 1
    assert rows[0][0] == "mineru"
    assert rows[0][1] == "formula"
    assert rows[0][2] == "$$x = y$$"
    bbox = json.loads(str(rows[0][3]))
    assert bbox["left"] == EXPECTED_LEFT
    assert bbox["top"] == EXPECTED_TOP
    assert bbox["right"] == EXPECTED_RIGHT
    assert bbox["bottom"] == EXPECTED_BOTTOM
    assert term_row is not None
    term_count = term_row[0]
    assert term_count > 0


def test_rebuild_mineru_document_regions_scales_content_list_to_target_page(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "backend": "pipeline",
        "middle_json": {"pdf_info": [{"page_idx": 0, "page_size": [509.0, 126.0]}]},
        "content_list": [
            {
                "type": "text",
                "text": "BT*CLICKUP SAN DIEGO US Jan 20, 2026",
                "bbox": [19, 119, 477, 738],
                "page_idx": 0,
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_mineru_document_regions(
            connection,
            "file-1",
            output_json,
            target_pages=[PageInfo(page_no=1, width=1415.0, height=350.0)],
        )
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
    assert bbox["left"] == approx(26.885)
    assert bbox["top"] == approx(41.65)
    assert bbox["right"] == approx(674.955)
    assert bbox["bottom"] == approx(258.3)
    metadata = json.loads(str(row[1]))
    assert metadata["source_page"] == {"page_no": 1, "width": 509.0, "height": 126.0}
    assert metadata["target_page"] == {"page_no": 1, "width": 1415.0, "height": 350.0}


def test_rebuild_mineru_document_regions_accepts_normalized_engine(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    output_json = {
        "backend": "pipeline",
        "middle_json": {"pdf_info": [{"page_idx": 0, "page_size": [200.0, 100.0]}]},
        "content_list": [
            {
                "type": "text",
                "text": "normalized page text",
                "bbox": [100, 100, 400, 300],
                "page_idx": 0,
            }
        ],
    }

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)

        inserted = rebuild_mineru_document_regions(
            connection,
            "file-1",
            output_json,
            target_pages=[PageInfo(page_no=1, width=400.0, height=200.0)],
            annotation_engine="mineru_normalized",
            annotation_provider="local-mineru",
            annotation_model="mineru-pipeline-normalized-jpg",
        )
        row = connection.execute(
            """
            SELECT annotation_engine, annotation_provider, annotation_model
            FROM document_regions
            WHERE file_hash = 'file-1'
            """
        ).fetchone()
        term_row = connection.execute(
            """
            SELECT annotation_engine
            FROM document_terms
            WHERE file_hash = 'file-1'
            LIMIT 1
            """
        ).fetchone()

    assert inserted == 1
    assert row == (
        "mineru_normalized",
        "local-mineru",
        "mineru-pipeline-normalized-jpg",
    )
    assert term_row == ("mineru_normalized",)


def test_extract_mineru_pages_reads_middle_json_page_sizes() -> None:
    pages = extract_mineru_pages(
        {
            "middle_json": {
                "pdf_info": [
                    {"page_idx": 1, "page_size": [612.0, 792.0]},
                    {"page_idx": 0, "page_size": [100.0, 200.0]},
                ]
            }
        }
    )

    assert [page.page_no for page in pages] == [1, 2]
    assert pages[0].width == EXPECTED_FIRST_PAGE_WIDTH
    assert pages[1].height == EXPECTED_SECOND_PAGE_HEIGHT
