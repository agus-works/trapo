from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import math
import os
from pathlib import Path
from typing import Any, Iterator, Protocol, Sequence

import duckdb


class DuckConnection(Protocol):
    def execute(
        self, query: str, parameters: Sequence[object] | None = None
    ) -> "DuckConnection": ...

    def executemany(
        self, query: str, parameters: Sequence[Sequence[object]]
    ) -> "DuckConnection": ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...


DEFAULT_QUACK_TOKEN = "trapo-local-quack-token"
MIN_QUACK_TOKEN_LENGTH = 4


@contextmanager
def connect(db_path: str | Path) -> Iterator[DuckConnection]:
    connection = open_connection(db_path)
    try:
        yield connection
    finally:
        connection.close()


def open_connection(db_path: str | Path) -> DuckConnection:
    path = str(db_path)
    if is_quack_uri(path):
        connection = duckdb.connect(":memory:")
        return QuackConnection(connection, path, token=quack_token())
    connection = duckdb.connect(path)
    configure_connection(connection)
    return connection


def is_quack_uri(db_path: str | Path) -> bool:
    return str(db_path).strip().lower().startswith("quack:")


def quack_token() -> str:
    token = os.getenv("TRAPO_QUACK_TOKEN", DEFAULT_QUACK_TOKEN).strip()
    if len(token) < MIN_QUACK_TOKEN_LENGTH:
        raise RuntimeError("TRAPO_QUACK_TOKEN must contain at least 4 characters.")
    return token


class QuackConnection:
    def __init__(self, client: duckdb.DuckDBPyConnection, uri: str, *, token: str):
        self._client = client
        self._uri = uri
        self._token = token
        self._client.execute("INSTALL quack")
        self._client.execute("LOAD quack")
        self._client.execute("SET httpfs_connection_caching = true")

    def execute(
        self, query: str, parameters: Sequence[object] | None = None
    ) -> "QuackConnection":
        rendered_query = render_query(query, parameters or [])
        if _is_transaction_control(rendered_query):
            self._client.execute("SELECT 1 WHERE false")
        else:
            self._client.execute(
                "FROM quack_query(?, ?, token := ?)",
                [self._uri, rendered_query, self._token],
            )
        return self

    def executemany(
        self, query: str, parameters: Sequence[Sequence[object]]
    ) -> "QuackConnection":
        for item in parameters:
            self.execute(query, item)
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._client.fetchone()

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._client.fetchall()

    def close(self) -> None:
        self._client.close()


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


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_query(query: str, parameters: Sequence[object]) -> str:
    if not parameters:
        return query
    rendered: list[str] = []
    parameter_index = 0
    in_string = False
    index = 0
    while index < len(query):
        char = query[index]
        if char == "'":
            rendered.append(char)
            if in_string and index + 1 < len(query) and query[index + 1] == "'":
                rendered.append(query[index + 1])
                index += 2
                continue
            in_string = not in_string
        elif char == "?" and not in_string:
            if parameter_index >= len(parameters):
                raise ValueError("Not enough parameters supplied for SQL query.")
            rendered.append(sql_literal(parameters[parameter_index]))
            parameter_index += 1
        else:
            rendered.append(char)
        index += 1
    if parameter_index != len(parameters):
        raise ValueError("Too many parameters supplied for SQL query.")
    return "".join(rendered)


def sql_literal(value: object) -> str:
    result: str
    if value is None:
        result = "NULL"
    elif isinstance(value, bool):
        result = "true" if value else "false"
    elif isinstance(value, int):
        result = str(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite float values cannot be sent to DuckDB.")
        result = repr(value)
    elif isinstance(value, datetime | date):
        result = _sql_string(value.isoformat())
    elif isinstance(value, bytes):
        result = "X'" + value.hex() + "'"
    else:
        result = _sql_string(str(value))
    return result


def _is_transaction_control(query: str) -> bool:
    normalized = query.strip().rstrip(";").upper()
    return normalized in {"BEGIN", "BEGIN TRANSACTION", "COMMIT", "ROLLBACK"}
