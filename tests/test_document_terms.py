from __future__ import annotations

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.document_regions import rebuild_document_terms
from trapo.migrations import apply_migrations

EXPECTED_TERM_COUNT = 5
FIRST_TERM_CHAR_END = 5
FIRST_TERM_CHAR_START = 0
SEEDED_CHUNK_ID = 10
SEEDED_PAGE_NO = 2


def test_rebuild_document_terms_uses_region_bbox_and_token_offsets(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        connection.execute(
            """
            INSERT INTO document_regions (
                region_id, file_hash, chunk_id, chunk_index, page_no,
                source_ref, parent_ref, label, text, context_text,
                raw_bbox_json, region_kind
            )
            VALUES (
                'region-1', 'file-1', 10, 0, 2,
                'ref-1', NULL, 'text', 'Total Amount Due: USD 12.50',
                NULL, '{"left": 10, "top": 20, "right": 200, "bottom": 40}'::JSON, 'text'
            )
            """
        )

        inserted = rebuild_document_terms(connection, "file-1")
        rows = connection.execute(
            """
            SELECT text, normalized_text, region_id, chunk_id, page_no,
                   char_start, char_end, metadata_json
            FROM document_terms
            WHERE file_hash = 'file-1'
            ORDER BY char_start
            """
        ).fetchall()

    assert inserted == EXPECTED_TERM_COUNT
    assert [str(row[0]) for row in rows] == ["Total", "Amount", "Due", "USD", "12.50"]
    assert [str(row[1]) for row in rows] == ["total", "amount", "due", "usd", "12.50"]
    assert rows[0][2] == "region-1"
    assert rows[0][3] == SEEDED_CHUNK_ID
    assert rows[0][4] == SEEDED_PAGE_NO
    assert rows[0][5] == FIRST_TERM_CHAR_START
    assert rows[0][6] == FIRST_TERM_CHAR_END
    assert "region" in str(rows[0][7])
