from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb


DuckConnection = duckdb.DuckDBPyConnection


@contextmanager
def connect(db_path: str | Path) -> Iterator[DuckConnection]:
    path = str(db_path)
    connection = duckdb.connect(path)
    configure_connection(connection)
    try:
        yield connection
    finally:
        connection.close()


def configure_connection(connection: DuckConnection) -> None:
    try:
        connection.execute("INSTALL fts")
        connection.execute("LOAD fts")
    except Exception:
        pass


def table_exists(connection: DuckConnection, table_name: str) -> bool:
    result = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return bool(result and result[0])


def scalar_int(
    connection: DuckConnection, sql: str, parameters: list[object] | None = None
) -> int:
    row = connection.execute(sql, parameters or []).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def required_scalar(
    connection: DuckConnection, sql: str, parameters: list[object] | None = None
) -> object:
    row = connection.execute(sql, parameters or []).fetchone()
    if row is None:
        raise RuntimeError(f"Expected one row for query: {sql}")
    return row[0]


def next_sequence_value(connection: DuckConnection, sequence_name: str) -> int:
    value = required_scalar(connection, f"SELECT nextval('{sequence_name}')")
    if not isinstance(value, int | str):
        raise RuntimeError(f"Unexpected sequence value for {sequence_name}: {value!r}")
    return int(value)


def next_table_id(
    connection: DuckConnection,
    *,
    table_name: str,
    column_name: str,
    sequence_name: str,
) -> int:
    sequence_value = next_sequence_value(connection, sequence_name)
    max_value = scalar_int(connection, f"SELECT max({column_name}) FROM {table_name}")
    return max(sequence_value, max_value + 1)
