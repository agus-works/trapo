from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from trapo.server.diagnostic_models import (
    DiagnosticEventRecord,
    DiagnosticRunRecord,
    DiagnosticSpanRecord,
    DiagnosticTraceSummary,
)


def trace_summary(
    spans: list[DiagnosticSpanRecord], *, ingest_run_id: int | None
) -> DiagnosticTraceSummary:
    started = min((span.started_at for span in spans), default=None)
    ended = max((span.ended_at for span in spans), default=None)
    file_count, page_count = _trace_scope_counts(spans)
    return DiagnosticTraceSummary(
        ingest_run_id=ingest_run_id,
        started_at=started,
        ended_at=ended,
        duration_ms=_trace_duration_ms(started, ended),
        span_count=len(spans),
        error_count=sum(1 for span in spans if span.status == "error"),
        file_count=file_count,
        page_count=page_count,
    )


def run_record(row: tuple[object, ...]) -> DiagnosticRunRecord:
    started = _datetime(row[9]) or _datetime(row[3])
    ended = _datetime(row[10]) or _datetime(row[4])
    duration_ms = (
        max(0.0, (ended - started).total_seconds() * 1000)
        if started is not None and ended is not None
        else 0.0
    )
    return DiagnosticRunRecord(
        ingest_run_id=_int_value(row[0]),
        source_directory=str(row[1]),
        status=str(row[2]),
        started_at=_datetime(row[3]),
        finished_at=_datetime(row[4]),
        duration_ms=duration_ms,
        span_count=_int_value(row[5]),
        error_count=_int_value(row[6]),
        file_count=_int_value(row[7]),
        page_count=_int_value(row[8]),
    )


def span_record(row: tuple[object, ...]) -> DiagnosticSpanRecord:
    return DiagnosticSpanRecord(
        span_id=str(row[0]),
        trace_id=str(row[1]),
        parent_span_id=str(row[2]) if row[2] is not None else None,
        ingest_run_id=_optional_int_value(row[3]),
        file_hash=str(row[4]) if row[4] is not None else None,
        page_no=_optional_int_value(row[5]),
        name=str(row[6]),
        pipeline_step=str(row[7]),
        category=str(row[8]),
        annotation_engine=str(row[9]) if row[9] is not None else None,
        status=str(row[10]),
        started_at=_datetime(row[11]) or datetime.min,
        ended_at=_datetime(row[12]) or datetime.min,
        duration_ms=_float_value(row[13]),
        attributes=_json_dict(row[14]),
        error_type=str(row[15]) if row[15] is not None else None,
        error_message=str(row[16]) if row[16] is not None else None,
        error_stack=str(row[17]) if row[17] is not None else None,
    )


def event_record(row: tuple[object, ...]) -> DiagnosticEventRecord:
    return DiagnosticEventRecord(
        event_id=_int_value(row[0]),
        trace_id=str(row[1]),
        span_id=str(row[2]) if row[2] is not None else None,
        ingest_run_id=_optional_int_value(row[3]),
        file_hash=str(row[4]) if row[4] is not None else None,
        page_no=_optional_int_value(row[5]),
        timestamp=_datetime(row[6]) or datetime.min,
        event_type=str(row[7]),
        name=str(row[8]),
        severity=str(row[9]),
        message=str(row[10]) if row[10] is not None else "",
        attributes=_json_dict(row[11]),
    )


def _datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _trace_duration_ms(started: datetime | None, ended: datetime | None) -> float:
    if started is None or ended is None:
        return 0.0
    return max(0.0, (ended - started).total_seconds() * 1000)


def _trace_scope_counts(spans: list[DiagnosticSpanRecord]) -> tuple[int, int]:
    pages = {
        (span.file_hash, span.page_no)
        for span in spans
        if span.file_hash is not None and span.page_no is not None
    }
    files = {span.file_hash for span in spans if span.file_hash is not None}
    return len(files), len(pages)


def _optional_int_value(value: object) -> int | None:
    return _int_value(value) if value is not None else None


def _int_value(value: object) -> int:
    result = 0
    if isinstance(value, bool | int | float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            result = 0
    return result


def _float_value(value: object) -> float:
    result = 0.0
    if isinstance(value, bool | int | float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            result = 0.0
    return result


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}
