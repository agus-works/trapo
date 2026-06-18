from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from trapo import __version__
from trapo.config import RuntimeConfig
from trapo.db import DuckConnection, table_exists


@dataclass(frozen=True)
class MigrationContext:
    config: RuntimeConfig


@dataclass(frozen=True)
class Migration:
    migration_id: str
    description: str
    risky: bool
    warning: str | None
    apply: Callable[[DuckConnection, MigrationContext], None]
    legacy_checksums: tuple[str, ...] = ()

    @property
    def checksum(self) -> str:
        payload = f"{self.migration_id}|{self.description}|{self.warning or ''}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def accepts_checksum(self, checksum: str) -> bool:
        return checksum == self.checksum or checksum in self.legacy_checksums


def ensure_migration_tables(connection: DuckConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            description TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT current_timestamp,
            app_version TEXT NOT NULL,
            notes TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_warnings (
            warning_id BIGINT PRIMARY KEY,
            migration_id TEXT NOT NULL,
            warning TEXT NOT NULL,
            acknowledged BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )


def applied_migrations(connection: DuckConnection) -> dict[str, str]:
    if not table_exists(connection, "schema_migrations"):
        return {}
    rows = connection.execute(
        "SELECT migration_id, checksum FROM schema_migrations"
    ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows}


def apply_migrations(
    connection: DuckConnection,
    config: RuntimeConfig,
    *,
    create_backup: bool = True,
) -> list[str]:
    # versions imports Migration from this module, so this import must stay lazy.
    from trapo.migrations.versions import MIGRATIONS  # noqa: PLC0415

    ensure_migration_tables(connection)
    applied = applied_migrations(connection)
    messages: list[str] = []
    known_migration_ids = {migration.migration_id for migration in MIGRATIONS}
    unsupported_migration_ids = sorted(set(applied) - known_migration_ids)
    if unsupported_migration_ids:
        formatted_ids = ", ".join(unsupported_migration_ids)
        raise RuntimeError(
            "Database uses unsupported legacy or unknown migrations: "
            f"{formatted_ids}. Create a new Trapo database or export data manually before upgrading."
        )

    for migration in MIGRATIONS:
        existing_checksum = applied.get(migration.migration_id)
        if existing_checksum is not None:
            if not migration.accepts_checksum(existing_checksum):
                raise RuntimeError(
                    f"Applied migration {migration.migration_id} checksum does not match code."
                )
            continue

        if migration.risky and create_backup:
            db_path = Path(config.db_path)
            if db_path.exists():
                backup_path = db_path.with_suffix(
                    f".before-{migration.migration_id}.duckdb"
                )
                shutil.copy2(db_path, backup_path)
                messages.append(f"Created migration backup: {backup_path}")

        connection.execute("BEGIN TRANSACTION")
        try:
            migration.apply(connection, MigrationContext(config=config))
            connection.execute(
                """
                INSERT INTO schema_migrations
                    (migration_id, checksum, description, app_version, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    migration.migration_id,
                    migration.checksum,
                    migration.description,
                    __version__,
                    migration.warning,
                ],
            )
            if migration.warning:
                connection.execute(
                    """
                    INSERT INTO migration_warnings
                        (warning_id, migration_id, warning, acknowledged)
                    VALUES (nextval('warning_id_seq'), ?, ?, false)
                    """,
                    [migration.migration_id, migration.warning],
                )
                messages.append(f"{migration.migration_id}: {migration.warning}")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    return messages
