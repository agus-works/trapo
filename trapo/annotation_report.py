from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trapo.db import DuckConnection, table_exists
from trapo.server.provenance import parse_json_value


@dataclass(frozen=True)
class AnnotationEngineReport:
    annotation_engine: str
    status: str | None = None
    error: str | None = None
    reader_provider: str | None = None
    reader_model: str | None = None
    region_count: int = 0
    page_count: int = 0
    text_chars: int = 0
    elapsed_seconds: float | None = None
    profile_name: str | None = None
    agreement_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnnotationComparisonReport:
    file_hash: str
    filename: str | None
    engines: list[AnnotationEngineReport]


def read_annotation_comparison_report(
    connection: DuckConnection,
    file_hash: str,
) -> AnnotationComparisonReport:
    filename = _filename(connection, file_hash)
    ocr_rows = _ocr_rows(connection, file_hash)
    region_stats = _region_stats(connection, file_hash)
    engines = sorted(set(ocr_rows) | set(region_stats))
    reports = [
        _engine_report(
            engine,
            ocr_rows.get(engine, {}),
            region_stats.get(engine, (0, 0)),
        )
        for engine in engines
    ]
    return AnnotationComparisonReport(
        file_hash=file_hash,
        filename=filename,
        engines=reports,
    )


def format_annotation_comparison_report(report: AnnotationComparisonReport) -> str:
    heading = f"Annotation report: file_hash={report.file_hash}"
    if report.filename:
        heading = f"{heading} filename={report.filename}"
    lines = [
        heading,
        "engine\tstatus\tregions\tpages\tchars\tprofile\telapsed_s\tagreement\terror",
    ]
    lines.extend(_format_engine_row(engine) for engine in report.engines)
    return "\n".join(lines)


def _engine_report(
    engine: str,
    row: dict[str, object],
    region_stats: tuple[int, int],
) -> AnnotationEngineReport:
    output_json = parse_json_value(row.get("output_json"))
    text = str(row.get("text") or "")
    region_count, region_page_count = region_stats
    return AnnotationEngineReport(
        annotation_engine=engine,
        status=_string_or_none(row.get("status")),
        error=_string_or_none(row.get("error")),
        reader_provider=_string_or_none(row.get("reader_provider")),
        reader_model=_string_or_none(row.get("reader_model")),
        region_count=region_count,
        page_count=_page_count(output_json) or region_page_count,
        text_chars=len(text),
        elapsed_seconds=_elapsed_seconds(output_json),
        profile_name=_profile_name(output_json),
        agreement_summary=_agreement_summary(output_json),
    )


def _format_engine_row(engine: AnnotationEngineReport) -> str:
    return "\t".join(
        [
            engine.annotation_engine,
            engine.status or "-",
            str(engine.region_count),
            str(engine.page_count),
            str(engine.text_chars),
            engine.profile_name or "-",
            _format_float(engine.elapsed_seconds),
            _format_agreement(engine.agreement_summary),
            _single_line(engine.error or "-"),
        ]
    )


def _ocr_rows(
    connection: DuckConnection, file_hash: str
) -> dict[str, dict[str, object]]:
    if not table_exists(connection, "ocr_documents"):
        return {}
    rows = connection.execute(
        """
        SELECT annotation_engine, status, error, reader_provider, reader_model, text, output_json
        FROM ocr_documents
        WHERE file_hash = ?
        ORDER BY annotation_engine
        """,
        [file_hash],
    ).fetchall()
    return {
        str(row[0]): {
            "status": row[1],
            "error": row[2],
            "reader_provider": row[3],
            "reader_model": row[4],
            "text": row[5],
            "output_json": row[6],
        }
        for row in rows
    }


def _region_stats(
    connection: DuckConnection, file_hash: str
) -> dict[str, tuple[int, int]]:
    if not table_exists(connection, "document_regions"):
        return {}
    rows = connection.execute(
        """
        SELECT annotation_engine, count(*), count(DISTINCT page_no)
        FROM document_regions
        WHERE file_hash = ?
        GROUP BY annotation_engine
        ORDER BY annotation_engine
        """,
        [file_hash],
    ).fetchall()
    return {str(row[0]): (int(row[1]), int(row[2])) for row in rows}


def _filename(connection: DuckConnection, file_hash: str) -> str | None:
    if not table_exists(connection, "files"):
        return None
    row = connection.execute(
        "SELECT filename FROM files WHERE file_hash = ?",
        [file_hash],
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _page_count(output_json: dict[str, Any]) -> int:
    pages = output_json.get("pages")
    return len(pages) if isinstance(pages, list) else 0


def _elapsed_seconds(output_json: dict[str, Any]) -> float | None:
    pages = output_json.get("pages")
    if not isinstance(pages, list):
        return None
    values = [
        float(page["elapsed_seconds"])
        for page in pages
        if isinstance(page, dict)
        and isinstance(page.get("elapsed_seconds"), int | float)
    ]
    return sum(values) if values else None


def _profile_name(output_json: dict[str, Any]) -> str | None:
    prompt_profile = output_json.get("prompt_profile")
    if isinstance(prompt_profile, str) and prompt_profile.strip():
        return prompt_profile.strip()
    profile = output_json.get("profile")
    if isinstance(profile, dict):
        name = profile.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _agreement_summary(output_json: dict[str, Any]) -> dict[str, Any]:
    summary = output_json.get("agreement_summary")
    return summary if isinstance(summary, dict) else {}


def _format_agreement(summary: dict[str, Any]) -> str:
    if not summary:
        return "-"
    return (
        f"all={_int_summary(summary, 'all_source_engines_region_count')},"
        f"multi={_int_summary(summary, 'multi_engine_region_count')},"
        f"single={_int_summary(summary, 'single_engine_region_count')}"
    )


def _int_summary(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key)
    return int(value) if isinstance(value, int | float) else 0


def _format_float(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "-"


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _single_line(value: str) -> str:
    return " ".join(value.split())
