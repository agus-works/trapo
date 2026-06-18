from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.migrations import apply_migrations


@dataclass(frozen=True)
class DatabaseInitialization:
    migration_messages: list[str]
    vss_warning: str | None


def initialize_database(config: RuntimeConfig) -> DatabaseInitialization:
    try:
        with connect(config.db_path) as connection:
            messages = apply_migrations(connection, config)
    except duckdb.IOException:
        db_path = Path(config.db_path)
        if not db_path.exists() or db_path.stat().st_size != 0:
            raise
        db_path.unlink()
        with connect(config.db_path) as connection:
            messages = apply_migrations(connection, config)
    return DatabaseInitialization(
        migration_messages=messages,
        vss_warning=None,
    )
