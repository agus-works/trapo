from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trapo.db import DuckConnection, scalar_int, table_exists


@dataclass(frozen=True)
class DatabaseStatus:
    db_path: str
    schema_version: str | None
    files: int
    chunks: int
    regions: int
    terms: int
    failed_docs: int
    runtime_id: str | None = None
    source_root: str | None = None


def read_database_status(
    connection: DuckConnection,
    db_path: str | Path,
    *,
    runtime_id: str | None = None,
    source_root: str | Path | None = None,
) -> DatabaseStatus:
    schema_version = _metadata_value(connection, "schema_version")
    return DatabaseStatus(
        db_path=str(db_path),
        schema_version=schema_version,
        files=_table_count(connection, "files"),
        chunks=_table_count(connection, "document_chunks"),
        regions=_table_count(connection, "document_regions"),
        terms=_table_count(connection, "document_terms"),
        failed_docs=_failed_document_count(connection),
        runtime_id=runtime_id,
        source_root=str(source_root) if source_root is not None else None,
    )


def _metadata_value(connection: DuckConnection, key: str) -> str | None:
    if not table_exists(connection, "app_metadata"):
        return None
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = ?", [key]
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _table_count(
    connection: DuckConnection, table_name: str, where: str | None = None
) -> int:
    if not table_exists(connection, table_name):
        return 0
    where_sql = f" WHERE {where}" if where else ""
    return scalar_int(connection, f"SELECT count(*) FROM {table_name}{where_sql}")


def _failed_document_count(connection: DuckConnection) -> int:
    if table_exists(connection, "ocr_documents"):
        return scalar_int(
            connection, "SELECT count(*) FROM ocr_documents WHERE status = 'error'"
        )
    return _table_count(connection, "docling_documents", "status = 'error'")
