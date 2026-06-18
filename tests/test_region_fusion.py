from __future__ import annotations

import json

from pytest import approx

from trapo.config import RuntimeConfig
from trapo.db import DuckConnection, connect
from trapo.migrations import apply_migrations
from trapo.region_fusion import rebuild_fused_document_regions
from trapo.server.models import PageInfo


PAGE_WIDTH = 100.0
PAGE_HEIGHT = 100.0
EXPECTED_LEFT = 11.0
EXPECTED_TOP = 11.0
EXPECTED_RIGHT = 59.0
EXPECTED_BOTTOM = 29.0
SINGLE_LEFT = 20
SINGLE_TOP = 40
SINGLE_RIGHT = 80
SINGLE_BOTTOM = 70
PROFILE_RECALL_LEFT = 5.0
PROFILE_RECALL_TOP = 5.0
PROFILE_RECALL_RIGHT = 70.0
PROFILE_RECALL_BOTTOM = 40.0
PROFILE_CONSERVATIVE_LEFT = 10
PROFILE_CONSERVATIVE_TOP = 10
ALL_SOURCE_ENGINE_COUNT = 3


def test_rebuild_fused_regions_uses_tight_consensus_over_broad_lmstudio(
    tmp_path,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _insert_region(
            connection,
            region_id="docling-tight",
            engine="docling",
            bbox={
                "left": 10,
                "top": 10,
                "right": 60,
                "bottom": 30,
                "coord_origin": "TOPLEFT",
            },
        )
        _insert_region(
            connection,
            region_id="mineru-tight",
            engine="mineru",
            bbox={
                "left": 12,
                "top": 12,
                "right": 58,
                "bottom": 28,
                "coord_origin": "TOPLEFT",
            },
        )
        _insert_region(
            connection,
            region_id="lmstudio-broad",
            engine="lmstudio",
            bbox={
                "left": 0,
                "top": 0,
                "right": 100,
                "bottom": 100,
                "coord_origin": "TOPLEFT",
            },
        )

        result = rebuild_fused_document_regions(
            connection,
            "file-1",
            [PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)],
        )
        row = connection.execute(
            """
            SELECT raw_bbox_json, metadata_json
            FROM document_regions
            WHERE file_hash = 'file-1' AND annotation_engine = 'fusion'
            """
        ).fetchone()

    assert result.region_count == 1
    assert row is not None
    bbox = json.loads(str(row[0]))
    assert bbox["left"] == approx(EXPECTED_LEFT)
    assert bbox["top"] == approx(EXPECTED_TOP)
    assert bbox["right"] == approx(EXPECTED_RIGHT)
    assert bbox["bottom"] == approx(EXPECTED_BOTTOM)
    metadata = json.loads(str(row[1]))
    assert set(metadata["contributing_region_ids"]) == {"docling-tight", "mineru-tight"}
    assert metadata["agreement_level"] == "all_source_engines"
    assert metadata["source_engine_count"] == ALL_SOURCE_ENGINE_COUNT
    broad_source = next(
        item
        for item in metadata["source_regions"]
        if item["region_id"] == "lmstudio-broad"
    )
    assert broad_source["contributed_to_bbox"] is False
    assert result.data["agreement_summary"]["source_engine_region_counts"] == {
        "docling": 1,
        "lmstudio": 1,
        "mineru": 1,
    }
    assert result.data["agreement_summary"]["all_source_engines_region_count"] == 1
    assert result.data["agreement_summary"]["support_combination_counts"] == {
        "docling+lmstudio+mineru": 1
    }


def test_rebuild_fused_regions_keeps_single_engine_regions(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _insert_region(
            connection,
            region_id="lmstudio-only",
            engine="lmstudio",
            bbox={
                "left": SINGLE_LEFT,
                "top": SINGLE_TOP,
                "right": SINGLE_RIGHT,
                "bottom": SINGLE_BOTTOM,
                "coord_origin": "TOPLEFT",
            },
        )

        result = rebuild_fused_document_regions(
            connection,
            "file-1",
            [PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)],
        )
        row = connection.execute(
            """
            SELECT text, raw_bbox_json, metadata_json
            FROM document_regions
            WHERE file_hash = 'file-1' AND annotation_engine = 'fusion'
            """
        ).fetchone()

    assert result.region_count == 1
    assert row is not None
    assert row[0] == "Total 42.00"
    bbox = json.loads(str(row[1]))
    assert bbox["left"] == SINGLE_LEFT
    assert bbox["top"] == SINGLE_TOP
    metadata = json.loads(str(row[2]))
    assert metadata["source_engine_counts"] == {"lmstudio": 1}
    assert metadata["agreement_level"] == "single_engine"
    assert result.data["agreement_summary"]["single_engine_region_count"] == 1
    assert (
        result.data["agreement_summary"]["single_engine_region_count_by_engine"][
            "lmstudio"
        ]
        == 1
    )


def test_rebuild_fused_regions_can_store_profile_alternatives(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _insert_region(
            connection,
            region_id="docling-tight",
            engine="docling",
            bbox={
                "left": 10,
                "top": 10,
                "right": 60,
                "bottom": 30,
                "coord_origin": "TOPLEFT",
            },
        )
        _insert_region(
            connection,
            region_id="lmstudio-wide",
            engine="lmstudio",
            bbox={
                "left": 0,
                "top": 0,
                "right": 80,
                "bottom": 50,
                "coord_origin": "TOPLEFT",
            },
        )

        conservative = rebuild_fused_document_regions(
            connection,
            "file-1",
            [PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)],
            profile="conservative",
        )
        recall = rebuild_fused_document_regions(
            connection,
            "file-1",
            [PageInfo(page_no=1, width=PAGE_WIDTH, height=PAGE_HEIGHT)],
            profile="recall",
        )
        rows = connection.execute(
            """
            SELECT annotation_engine, raw_bbox_json, metadata_json
            FROM document_regions
            WHERE file_hash = 'file-1'
              AND annotation_engine IN ('fusion_conservative', 'fusion_recall')
            ORDER BY annotation_engine
            """
        ).fetchall()

    assert conservative.region_count == 1
    assert recall.region_count == 1
    assert [row[0] for row in rows] == ["fusion_conservative", "fusion_recall"]
    conservative_bbox = json.loads(str(rows[0][1]))
    recall_bbox = json.loads(str(rows[1][1]))
    assert conservative_bbox["left"] == PROFILE_CONSERVATIVE_LEFT
    assert conservative_bbox["top"] == PROFILE_CONSERVATIVE_TOP
    assert recall_bbox["left"] == approx(PROFILE_RECALL_LEFT)
    assert recall_bbox["top"] == approx(PROFILE_RECALL_TOP)
    assert recall_bbox["right"] == approx(PROFILE_RECALL_RIGHT)
    assert recall_bbox["bottom"] == approx(PROFILE_RECALL_BOTTOM)
    recall_metadata = json.loads(str(rows[1][2]))
    assert recall_metadata["fusion_profile"]["name"] == "recall"
    assert set(recall_metadata["contributing_region_ids"]) == {
        "docling-tight",
        "lmstudio-wide",
    }


def _insert_region(
    connection: DuckConnection,
    *,
    region_id: str,
    engine: str,
    bbox: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO document_regions (
            region_id, file_hash, annotation_engine, annotation_provider,
            annotation_model, page_no, source_ref, label, text, context_text,
            raw_bbox_json, region_kind, metadata_json
        )
        VALUES (
            ?, 'file-1', ?, ?, ?, 1, ?, 'text', 'Total 42.00', 'Total 42.00',
            ?::JSON, 'text', '{}'::JSON
        )
        """,
        [
            region_id,
            engine,
            f"local-{engine}",
            engine,
            f"{engine}:0",
            json.dumps(bbox),
        ],
    )
