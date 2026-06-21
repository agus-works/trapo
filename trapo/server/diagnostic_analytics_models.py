from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from trapo.server.diagnostic_models import DiagnosticWorkUnitRecord


class DiagnosticAnalyticsSummary(BaseModel):
    ingest_run_id: int | None = None
    status: str = "unknown"
    source_directory: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    work_unit_count: int = 0
    failed_work_unit_count: int = 0
    span_count: int = 0
    failed_span_count: int = 0
    model_lease_count: int = 0
    failed_llm_duration_ms: float = 0.0


class DiagnosticBreakdownRecord(BaseModel):
    id: str
    label: str
    duration_ms: float
    unit_count: int
    error_count: int = 0
    file_count: int = 0
    page_count: int = 0
    max_duration_ms: float = 0.0
    share_percent: float = 0.0
    metadata: dict[str, object] = Field(default_factory=dict)


class DiagnosticSlowSpanRecord(BaseModel):
    span_id: str
    trace_id: str
    file_hash: str | None = None
    page_no: int | None = None
    pipeline_step: str
    category: str
    annotation_engine: str | None = None
    status: str
    duration_ms: float
    error_type: str | None = None
    error_message: str | None = None


class DiagnosticRecommendationRecord(BaseModel):
    id: str
    severity: str
    title: str
    detail: str
    evidence: dict[str, object] = Field(default_factory=dict)


class DiagnosticAnalyticsPayload(BaseModel):
    summary: DiagnosticAnalyticsSummary
    phase_breakdown: list[DiagnosticBreakdownRecord] = Field(default_factory=list)
    engine_breakdown: list[DiagnosticBreakdownRecord] = Field(default_factory=list)
    model_breakdown: list[DiagnosticBreakdownRecord] = Field(default_factory=list)
    file_breakdown: list[DiagnosticBreakdownRecord] = Field(default_factory=list)
    page_breakdown: list[DiagnosticBreakdownRecord] = Field(default_factory=list)
    error_breakdown: list[DiagnosticBreakdownRecord] = Field(default_factory=list)
    slow_work_units: list[DiagnosticWorkUnitRecord] = Field(default_factory=list)
    slow_spans: list[DiagnosticSlowSpanRecord] = Field(default_factory=list)
    recommendations: list[DiagnosticRecommendationRecord] = Field(default_factory=list)


class DiagnosticModelLeaseRecord(BaseModel):
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
    load_status: str | None = None
    requested_parameters: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    switch_index: int = 0


class DiagnosticModelsPayload(BaseModel):
    ingest_run_id: int | None = None
    leases: list[DiagnosticModelLeaseRecord] = Field(default_factory=list)
