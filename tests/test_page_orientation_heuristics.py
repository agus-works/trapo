from __future__ import annotations

import json
from dataclasses import dataclass

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.migrations import apply_migrations
from trapo.page_orientation_heuristics import infer_docling_image_rotation
from trapo.server.models import PageInfo


PAGE_WIDTH = 300.0
PAGE_HEIGHT = 500.0
EXPECTED_LEFT_SIDE_ROTATION = 270
EXPECTED_RIGHT_SIDE_ROTATION = 90


@dataclass(frozen=True)
class RegionBox:
    left: float
    top: float
    right: float
    bottom: float


def test_infer_docling_image_rotation_uses_right_side_vertical_text(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    page = PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _insert_docling_region(connection, "a", RegionBox(240, 430, 260, 220))
        _insert_docling_region(connection, "b", RegionBox(230, 390, 250, 160))
        _insert_docling_region(connection, "c", RegionBox(250, 350, 270, 130))
        _insert_docling_region(connection, "d", RegionBox(40, 80, 180, 60))

        override = infer_docling_image_rotation(
            connection, file_hash="hash1", page=page
        )

    assert override is not None
    assert override.clockwise_degrees == EXPECTED_RIGHT_SIDE_ROTATION
    assert override.source == "docling_layout_heuristic"
    assert override.confidence is not None
    assert override.confidence > 0.0


def test_infer_docling_image_rotation_uses_left_side_vertical_text(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    page = PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _insert_docling_region(connection, "a", RegionBox(40, 430, 60, 220))
        _insert_docling_region(connection, "b", RegionBox(50, 390, 70, 160))
        _insert_docling_region(connection, "c", RegionBox(30, 350, 50, 130))
        _insert_docling_region(connection, "d", RegionBox(120, 80, 260, 60))

        override = infer_docling_image_rotation(
            connection, file_hash="hash1", page=page
        )

    assert override is not None
    assert override.clockwise_degrees == EXPECTED_LEFT_SIDE_ROTATION
    assert override.source == "docling_layout_heuristic"
    assert override.confidence is not None
    assert override.confidence > 0.0


def test_infer_docling_image_rotation_ignores_sparse_vertical_text(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))
    page = PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _insert_docling_region(connection, "a", RegionBox(240, 430, 260, 220))

        override = infer_docling_image_rotation(
            connection, file_hash="hash1", page=page
        )

    assert override is None


def _insert_docling_region(
    connection,
    suffix: str,
    box: RegionBox,
) -> None:
    connection.execute(
        """
        INSERT INTO document_regions (
            region_id, file_hash, annotation_engine, annotation_provider,
            annotation_model, page_no, source_ref, label, text, context_text,
            raw_bbox_json, region_kind, metadata_json
        )
        VALUES (
            ?, 'hash1', 'docling', 'local-docling', 'docling', 1, ?,
            'text', 'Long vertical text', 'Long vertical text', ?::JSON, 'text', '{}'::JSON
        )
        """,
        [
            f"docling-{suffix}",
            f"docling:{suffix}",
            json.dumps(
                {
                    "left": box.left,
                    "top": box.top,
                    "right": box.right,
                    "bottom": box.bottom,
                    "coord_origin": "BOTTOMLEFT",
                }
            ),
        ],
    )
