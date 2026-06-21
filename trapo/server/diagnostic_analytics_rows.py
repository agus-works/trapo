from __future__ import annotations

from collections import defaultdict
from typing import Any

from trapo.server.diagnostic_analytics_models import (
    DiagnosticAnalyticsSummary,
    DiagnosticBreakdownRecord,
    DiagnosticRecommendationRecord,
    DiagnosticSlowSpanRecord,
)
from trapo.server.diagnostic_models import DiagnosticWorkUnitRecord


FAILED_LLM_SHARE_THRESHOLD = 0.2


def work_unit_breakdown(
    units: list[DiagnosticWorkUnitRecord],
    key: Any,
    limit: int,
    *,
    label: Any | None = None,
    metadata: Any | None = None,
) -> list[DiagnosticBreakdownRecord]:
    groups: dict[str, list[DiagnosticWorkUnitRecord]] = defaultdict(list)
    for unit in units:
        groups[str(key(unit))].append(unit)
    total_duration = sum(unit_duration(unit) for unit in units)
    rows = [
        _breakdown_record(
            group_key,
            group_units,
            total_duration,
            label=label,
            metadata=metadata,
        )
        for group_key, group_units in groups.items()
    ]
    return sorted(rows, key=lambda row: row.duration_ms, reverse=True)[:limit]


def span_error_breakdown(
    spans: list[Any],
    total_duration_ms: float,
    limit: int,
) -> list[DiagnosticBreakdownRecord]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for span in spans:
        if span.status == "error":
            key = span.annotation_engine or span.category or span.pipeline_step
            groups[str(key)].append(span)
    rows = [
        _span_error_record(group_key, group, total_duration_ms)
        for group_key, group in groups.items()
    ]
    return sorted(rows, key=lambda row: row.duration_ms, reverse=True)[:limit]


def slow_spans(spans: list[Any], limit: int) -> list[DiagnosticSlowSpanRecord]:
    return [
        DiagnosticSlowSpanRecord(
            span_id=span.span_id,
            trace_id=span.trace_id,
            file_hash=span.file_hash,
            page_no=span.page_no,
            pipeline_step=span.pipeline_step,
            category=span.category,
            annotation_engine=span.annotation_engine,
            status=span.status,
            duration_ms=span.duration_ms,
            error_type=span.error_type,
            error_message=span.error_message,
        )
        for span in sorted(spans, key=lambda item: item.duration_ms, reverse=True)[
            :limit
        ]
    ]


def analytics_recommendations(
    summary: DiagnosticAnalyticsSummary,
    units: list[DiagnosticWorkUnitRecord],
) -> list[DiagnosticRecommendationRecord]:
    recommendations: list[DiagnosticRecommendationRecord] = []
    duration_ms = summary.duration_ms
    if (
        duration_ms
        and summary.failed_llm_duration_ms / duration_ms > FAILED_LLM_SHARE_THRESHOLD
    ):
        recommendations.append(
            DiagnosticRecommendationRecord(
                id="failed-llm-cost",
                severity="high",
                title="Failed LM Studio calls dominate useful work",
                detail=(
                    "Add fail-fast repetition detection and inspect the Infinity "
                    "LM Studio backend context and retry settings."
                ),
                evidence={"failed_llm_duration_ms": summary.failed_llm_duration_ms},
            )
        )
    if summary.model_lease_count > 1:
        recommendations.append(
            DiagnosticRecommendationRecord(
                id="model-switches",
                severity="medium",
                title="The run used multiple model leases",
                detail=(
                    "Keep the planner model-centered so each model processes all "
                    "eligible units before another model is loaded."
                ),
                evidence={"model_lease_count": summary.model_lease_count},
            )
        )
    return recommendations or [
        DiagnosticRecommendationRecord(
            id="no-dominant-bottleneck",
            severity="info",
            title="No single bottleneck crossed the built-in thresholds",
            detail="Use the ranked tables to compare the next slowest phase or file.",
        )
    ]


def unit_duration(unit: DiagnosticWorkUnitRecord) -> float:
    return float(unit.duration_ms or 0.0)


def unit_file_label(unit: DiagnosticWorkUnitRecord) -> str:
    return (
        unit.filename
        or _basename(unit.source_path)
        or _basename(_metadata_source_path(unit))
    )


def unit_page_label(unit: DiagnosticWorkUnitRecord) -> str:
    return f"{unit_file_label(unit)} · page {unit.page_no}"


def file_metadata(
    unit: DiagnosticWorkUnitRecord,
    units: list[DiagnosticWorkUnitRecord],
) -> dict[str, object]:
    return {
        "file_hash": unit.file_hash,
        "filename": unit.filename,
        "source_path": unit.source_path or _metadata_source_path(unit),
        "phase_count": len({item.phase for item in units}),
    }


def page_metadata(
    unit: DiagnosticWorkUnitRecord,
    _units: list[DiagnosticWorkUnitRecord],
) -> dict[str, object]:
    return {
        "file_hash": unit.file_hash,
        "filename": unit.filename,
        "source_path": unit.source_path or _metadata_source_path(unit),
        "page_no": unit.page_no,
    }


def _breakdown_record(
    group_key: str,
    units: list[DiagnosticWorkUnitRecord],
    total_duration: float,
    *,
    label: Any | None,
    metadata: Any | None,
) -> DiagnosticBreakdownRecord:
    duration = sum(unit_duration(unit) for unit in units)
    pages = {
        (unit.file_hash, unit.page_no)
        for unit in units
        if unit.file_hash and unit.page_no is not None
    }
    return DiagnosticBreakdownRecord(
        id=group_key,
        label=str(label(units[0]) if label else group_key),
        duration_ms=duration,
        unit_count=len(units),
        error_count=sum(1 for unit in units if unit.status == "error"),
        file_count=len({unit.file_hash for unit in units if unit.file_hash}),
        page_count=len(pages),
        max_duration_ms=max((unit_duration(unit) for unit in units), default=0.0),
        share_percent=(duration / total_duration * 100.0) if total_duration else 0.0,
        metadata=metadata(units[0], units) if metadata else {},
    )


def _span_error_record(
    group_key: str,
    group: list[Any],
    total_duration_ms: float,
) -> DiagnosticBreakdownRecord:
    duration = sum(float(span.duration_ms) for span in group)
    return DiagnosticBreakdownRecord(
        id=group_key,
        label=group_key,
        duration_ms=duration,
        unit_count=len(group),
        error_count=len(group),
        file_count=len({span.file_hash for span in group if span.file_hash}),
        page_count=len(
            {
                (span.file_hash, span.page_no)
                for span in group
                if span.file_hash and span.page_no is not None
            }
        ),
        max_duration_ms=max((span.duration_ms for span in group), default=0.0),
        share_percent=(duration / total_duration_ms * 100.0)
        if total_duration_ms
        else 0.0,
        metadata={
            "sample_error": next(
                (span.error_message for span in group if span.error_message),
                None,
            )
        },
    )


def _metadata_source_path(unit: DiagnosticWorkUnitRecord) -> str | None:
    value = unit.metadata.get("source_path")
    return value if isinstance(value, str) else None


def _basename(path: str | None) -> str:
    if not path:
        return "run"
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or path
