export interface DiagnosticRunRecord {
  ingest_run_id: number;
  source_directory: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  span_count: number;
  error_count: number;
  file_count: number;
  page_count: number;
}

export interface DiagnosticSpanRecord {
  span_id: string;
  trace_id: string;
  parent_span_id?: string | null;
  ingest_run_id?: number | null;
  file_hash?: string | null;
  page_no?: number | null;
  name: string;
  pipeline_step: string;
  category: string;
  annotation_engine?: string | null;
  status: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  attributes: Record<string, unknown>;
  error_type?: string | null;
  error_message?: string | null;
  error_stack?: string | null;
}

export interface DiagnosticEventRecord {
  event_id: number;
  trace_id: string;
  span_id?: string | null;
  ingest_run_id?: number | null;
  file_hash?: string | null;
  page_no?: number | null;
  timestamp: string;
  event_type: string;
  name: string;
  severity: string;
  message: string;
  attributes: Record<string, unknown>;
}

export interface DiagnosticTraceSummary {
  ingest_run_id?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms: number;
  span_count: number;
  error_count: number;
  file_count: number;
  page_count: number;
}

export interface DiagnosticTracePayload {
  summary: DiagnosticTraceSummary;
  spans: DiagnosticSpanRecord[];
  events: DiagnosticEventRecord[];
}

export interface DiagnosticProgressSummary {
  ingest_run_id?: number | null;
  total_units: number;
  planned_units: number;
  running_units: number;
  completed_units: number;
  failed_units: number;
  skipped_units: number;
  percent_complete: number;
  estimated_remaining_ms?: number | null;
}

export interface DiagnosticWorkUnitRecord {
  work_unit_id: number;
  ingest_run_id: number;
  work_key: string;
  file_hash?: string | null;
  filename?: string | null;
  source_path?: string | null;
  page_no?: number | null;
  phase: string;
  engine: string;
  provider: string;
  model: string;
  profile?: string | null;
  execution_key: string;
  artifact_variant?: string | null;
  status: string;
  attempt_count: number;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  error?: string | null;
  result: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface DiagnosticBatchRecord {
  lease_id: number;
  ingest_run_id: number;
  execution_key: string;
  provider: string;
  model: string;
  requested_context_tokens?: number | null;
  verified_context_tokens?: number | null;
  status: string;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
  error?: string | null;
  metadata: Record<string, unknown>;
}

export interface DiagnosticProgressPayload {
  summary: DiagnosticProgressSummary;
  work_units: DiagnosticWorkUnitRecord[];
  batches: DiagnosticBatchRecord[];
}

export interface DiagnosticAnalyticsSummary {
  ingest_run_id?: number | null;
  status: string;
  source_directory: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  work_unit_count: number;
  failed_work_unit_count: number;
  span_count: number;
  failed_span_count: number;
  model_lease_count: number;
  failed_llm_duration_ms: number;
}

export interface DiagnosticBreakdownRecord {
  id: string;
  label: string;
  duration_ms: number;
  unit_count: number;
  error_count: number;
  file_count: number;
  page_count: number;
  max_duration_ms: number;
  share_percent: number;
  metadata: Record<string, unknown>;
}

export interface DiagnosticSlowSpanRecord {
  span_id: string;
  trace_id: string;
  file_hash?: string | null;
  page_no?: number | null;
  pipeline_step: string;
  category: string;
  annotation_engine?: string | null;
  status: string;
  duration_ms: number;
  error_type?: string | null;
  error_message?: string | null;
}

export interface DiagnosticRecommendationRecord {
  id: string;
  severity: string;
  title: string;
  detail: string;
  evidence: Record<string, unknown>;
}

export interface DiagnosticAnalyticsPayload {
  summary: DiagnosticAnalyticsSummary;
  phase_breakdown: DiagnosticBreakdownRecord[];
  engine_breakdown: DiagnosticBreakdownRecord[];
  model_breakdown: DiagnosticBreakdownRecord[];
  file_breakdown: DiagnosticBreakdownRecord[];
  page_breakdown: DiagnosticBreakdownRecord[];
  error_breakdown: DiagnosticBreakdownRecord[];
  slow_work_units: DiagnosticWorkUnitRecord[];
  slow_spans: DiagnosticSlowSpanRecord[];
  recommendations: DiagnosticRecommendationRecord[];
}

export interface DiagnosticModelLeaseRecord extends DiagnosticBatchRecord {
  load_status?: string | null;
  requested_parameters: Record<string, unknown>;
  switch_index: number;
}

export interface DiagnosticModelsPayload {
  ingest_run_id?: number | null;
  leases: DiagnosticModelLeaseRecord[];
}

export interface DiagnosticTraceParams {
  fileHash?: string | null;
  ingestRunId?: number | null;
  limit?: number;
  pageNo?: number | null;
  q?: string | null;
  status?: string | null;
}
