from __future__ import annotations

from trapo.config import RuntimeConfig
from trapo.db import connect, scalar_int
from trapo.ingest.pipeline import _upsert_file
from trapo.migrations import apply_migrations


def test_file_upsert_updates_last_seen_without_duckdb_binding_error(tmp_path) -> None:
    db_path = tmp_path / "trapo.duckdb"
    file_path = tmp_path / "example.txt"
    file_path.write_text("hello", encoding="utf-8")
    config = RuntimeConfig.from_env(db_path=str(db_path))

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        _upsert_file(connection, file_path, "abc123", 5, file_path.stat().st_mtime)
        _upsert_file(connection, file_path, "abc123", 5, file_path.stat().st_mtime)

        assert scalar_int(connection, "SELECT count(*) FROM files") == 1
        assert scalar_int(connection, "SELECT count(*) FROM file_locations") == 1
