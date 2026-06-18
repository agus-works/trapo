from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.server.provenance import parse_json_value


VALID_ROTATION_DEGREES = frozenset({0, 90, 180, 270})


@dataclass(frozen=True)
class PageOrientationOverride:
    file_hash: str
    page_no: int
    clockwise_degrees: int
    source: str
    confidence: float | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class PageOrientationOverrideUpdate:
    file_hash: str
    page_no: int
    clockwise_degrees: int
    source: str = "manual"
    confidence: float | None = None
    metadata: dict[str, Any] | None = None


def normalize_clockwise_degrees(value: object) -> int:
    degrees = _int_or_none(value)
    if degrees is None:
        return 0
    normalized = degrees % 360
    if normalized not in VALID_ROTATION_DEGREES:
        raise ValueError(
            "Image page rotation must be one of 0, 90, 180, or 270 degrees."
        )
    return normalized


def read_page_rotation_degrees(
    connection: DuckConnection,
    file_hash: str,
    *,
    page_no: int = 1,
) -> int:
    row = _orientation_row(connection, file_hash, page_no)
    return row.clockwise_degrees if row is not None else 0


def read_page_orientation_overrides(
    connection: DuckConnection,
    file_hash: str,
) -> dict[int, PageOrientationOverride]:
    if not table_exists(connection, "page_orientation_overrides"):
        return {}
    rows = connection.execute(
        """
        SELECT file_hash, page_no, clockwise_degrees, source, confidence, metadata_json
        FROM page_orientation_overrides
        WHERE file_hash = ?
        ORDER BY page_no
        """,
        [file_hash],
    ).fetchall()
    return {
        int(row[1]): PageOrientationOverride(
            file_hash=str(row[0]),
            page_no=int(row[1]),
            clockwise_degrees=normalize_clockwise_degrees(row[2]),
            source=str(row[3] or "manual"),
            confidence=float(row[4]) if row[4] is not None else None,
            metadata=parse_json_value(row[5]),
        )
        for row in rows
    }


def upsert_page_orientation_override(
    connection: DuckConnection,
    *,
    override: PageOrientationOverrideUpdate,
) -> None:
    degrees = normalize_clockwise_degrees(override.clockwise_degrees)
    if override.page_no <= 0:
        raise ValueError("Page number must be greater than zero.")
    if not table_exists(connection, "page_orientation_overrides"):
        raise RuntimeError(
            "Database is missing page_orientation_overrides. Run migrations first."
        )
    connection.execute(
        """
        INSERT INTO page_orientation_overrides (
            file_hash, page_no, clockwise_degrees, source, confidence, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?::JSON)
        ON CONFLICT (file_hash, page_no) DO UPDATE SET
            clockwise_degrees = excluded.clockwise_degrees,
            source = excluded.source,
            confidence = excluded.confidence,
            metadata_json = excluded.metadata_json,
            updated_at = now()
        """,
        [
            override.file_hash,
            override.page_no,
            degrees,
            override.source,
            override.confidence,
            json.dumps(override.metadata or {}),
        ],
    )


def _orientation_row(
    connection: DuckConnection,
    file_hash: str,
    page_no: int,
) -> PageOrientationOverride | None:
    result: PageOrientationOverride | None = None
    if table_exists(connection, "page_orientation_overrides"):
        row = connection.execute(
            """
            SELECT file_hash, page_no, clockwise_degrees, source, confidence, metadata_json
            FROM page_orientation_overrides
            WHERE file_hash = ? AND page_no = ?
            """,
            [file_hash, page_no],
        ).fetchone()
        if row is not None:
            result = PageOrientationOverride(
                file_hash=str(row[0]),
                page_no=int(row[1]),
                clockwise_degrees=normalize_clockwise_degrees(row[2]),
                source=str(row[3] or "manual"),
                confidence=float(row[4]) if row[4] is not None else None,
                metadata=parse_json_value(row[5]),
            )
    return result


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value.strip())
        except ValueError:
            result = None
    return result
