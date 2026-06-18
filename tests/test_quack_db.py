from __future__ import annotations

import trapo.db as trapo_db


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object] | None]] = []
        self.closed = False

    def execute(
        self, statement: str, parameters: list[object] | None = None
    ) -> "FakeConnection":
        self.calls.append((statement, parameters))
        return self

    def executemany(
        self, statement: str, parameters: list[list[object]]
    ) -> "FakeConnection":
        for item in parameters:
            self.execute(statement, item)
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        return []

    def close(self) -> None:
        self.closed = True


def test_quack_uri_uses_stateless_query_adapter(monkeypatch) -> None:
    fake = FakeConnection()
    monkeypatch.setenv("TRAPO_QUACK_TOKEN", "secret-token")
    monkeypatch.setattr(trapo_db.duckdb, "connect", lambda path: fake)

    connection = trapo_db.open_connection("quack:localhost:9494")
    connection.execute("SELECT * FROM files WHERE file_hash = ?", ["abc'123"])

    assert isinstance(connection, trapo_db.QuackConnection)
    assert fake.calls[:4] == [
        ("INSTALL quack", None),
        ("LOAD quack", None),
        ("SET httpfs_connection_caching = true", None),
        (
            "FROM quack_query(?, ?, token := ?)",
            [
                "quack:localhost:9494",
                "SELECT * FROM files WHERE file_hash = 'abc''123'",
                "secret-token",
            ],
        ),
    ]


def test_render_query_rejects_parameter_count_mismatch() -> None:
    try:
        trapo_db.render_query("SELECT ? + ?", [1])
    except ValueError as exc:
        assert "Not enough" in str(exc)
    else:
        raise AssertionError("Expected missing SQL parameters to be rejected.")


def test_quack_token_rejects_too_short_value(monkeypatch) -> None:
    monkeypatch.setenv("TRAPO_QUACK_TOKEN", "abc")

    try:
        trapo_db.quack_token()
    except RuntimeError as exc:
        assert "TRAPO_QUACK_TOKEN" in str(exc)
    else:
        raise AssertionError("Expected short Quack tokens to be rejected.")
