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

export interface DiagnosticTraceParams {
  fileHash?: string | null;
  ingestRunId?: number | null;
  limit?: number;
  pageNo?: number | null;
  q?: string | null;
  status?: string | null;
}
