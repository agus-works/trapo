from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DiagnosticRunRecord(BaseModel):
    ingest_run_id: int
    source_directory: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    span_count: int = 0
    error_count: int = 0
    file_count: int = 0
    page_count: int = 0


class DiagnosticSpanRecord(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    ingest_run_id: int | None = None
    file_hash: str | None = None
    page_no: int | None = None
    name: str
    pipeline_step: str
    category: str
    annotation_engine: str | None = None
    status: str
    started_at: datetime
    ended_at: datetime
    duration_ms: float
    attributes: dict[str, object] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    error_stack: str | None = None


class DiagnosticEventRecord(BaseModel):
    event_id: int
    trace_id: str
    span_id: str | None = None
    ingest_run_id: int | None = None
    file_hash: str | None = None
    page_no: int | None = None
    timestamp: datetime
    event_type: str
    name: str
    severity: str
    message: str = ""
    attributes: dict[str, object] = Field(default_factory=dict)


class DiagnosticTraceSummary(BaseModel):
    ingest_run_id: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    span_count: int = 0
    error_count: int = 0
    file_count: int = 0
    page_count: int = 0


class DiagnosticTracePayload(BaseModel):
    summary: DiagnosticTraceSummary
    spans: list[DiagnosticSpanRecord] = Field(default_factory=list)
    events: list[DiagnosticEventRecord] = Field(default_factory=list)


class DiagnosticProgressSummary(BaseModel):
    ingest_run_id: int | None = None
    total_units: int = 0
    planned_units: int = 0
    running_units: int = 0
    completed_units: int = 0
    failed_units: int = 0
    skipped_units: int = 0
    percent_complete: float = 0.0
    estimated_remaining_ms: float | None = None


class DiagnosticWorkUnitRecord(BaseModel):
    work_unit_id: int
    ingest_run_id: int
    work_key: str
    file_hash: str | None = None
    filename: str | None = None
    source_path: str | None = None
    page_no: int | None = None
    phase: str
    engine: str
    provider: str
    model: str
    profile: str | None = None
    execution_key: str
    artifact_variant: str | None = None
    status: str
    attempt_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    error: str | None = None
    result: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class DiagnosticBatchRecord(BaseModel):
    lease_id: int
    ingest_run_id: int
    execution_key: str
    provider: str
    model: str
    requested_context_tokens: int | None = None
    verified_context_tokens: int | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: float | None = None
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class DiagnosticProgressPayload(BaseModel):
    summary: DiagnosticProgressSummary
    work_units: list[DiagnosticWorkUnitRecord] = Field(default_factory=list)
    batches: list[DiagnosticBatchRecord] = Field(default_factory=list)
