from __future__ import annotations

import pytest

from trapo import __version__
from trapo.config import RuntimeConfig
from trapo.db import connect, next_table_id, required_scalar, scalar_int, table_exists
from trapo.migrations import apply_migrations
from trapo.migrations.runner import ensure_migration_tables
from trapo.migrations.versions import MIGRATIONS

NEXT_INGEST_RUN_ID_AFTER_SEED = 3


def test_apply_initial_migration_creates_schema(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        messages = apply_migrations(connection, config, create_backup=False)
        migration_count = scalar_int(
            connection, "SELECT count(*) FROM schema_migrations"
        )
        schema_version = required_scalar(
            connection,
            "SELECT value FROM app_metadata WHERE key = 'schema_version'",
        )

    assert messages == []
    assert migration_count == len(MIGRATIONS)
    assert schema_version == MIGRATIONS[-1].migration_id

    with connect(db_path) as connection:
        for table in (
            "app_metadata",
            "ingest_runs",
            "files",
            "file_locations",
            "docling_documents",
            "document_chunks",
            "document_regions",
            "document_terms",
            "document_page_markdown",
            "document_page_markdown_regions",
            "document_markdown_generators",
            "document_preview_images",
            "ingest_diagnostic_events",
            "ingest_diagnostic_spans",
            "page_orientation_overrides",
        ):
            assert table_exists(connection, table), table


def test_simplified_schema_drops_legacy_feature_tables(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        for table in (
            "ontology_facts",
            "chunk_embeddings",
            "work_units",
            "chat_conversations",
            "retrieval_hyperedges",
            "eval_runs",
            "financial_line_items",
            "graph_nodes",
        ):
            assert not table_exists(connection, table), table


def test_reapplying_migrations_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        apply_migrations(connection, config, create_backup=False)
        migration_count = scalar_int(
            connection, "SELECT count(*) FROM schema_migrations"
        )

    assert migration_count == len(MIGRATIONS)


def test_legacy_migration_history_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        ensure_migration_tables(connection)
        connection.execute(
            """
            INSERT INTO schema_migrations
                (migration_id, checksum, description, app_version, notes)
            VALUES (?, ?, ?, ?, NULL)
            """,
            [
                "0100_fresh_server_owned_baseline",
                "deadbeef",
                "legacy migration row",
                __version__,
            ],
        )

        with pytest.raises(
            RuntimeError, match="unsupported legacy or unknown migrations"
        ):
            apply_migrations(connection, config, create_backup=False)


def test_next_table_id_skips_existing_rows_when_sequence_is_stale(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        connection.execute(
            """
            INSERT INTO ingest_runs
                (ingest_run_id, source_directory, status)
            VALUES (1, 'a', 'interrupted'), (2, 'b', 'interrupted')
            """
        )

        next_id = next_table_id(
            connection,
            table_name="ingest_runs",
            column_name="ingest_run_id",
            sequence_name="ingest_run_id_seq",
        )

    assert next_id == NEXT_INGEST_RUN_ID_AFTER_SEED
