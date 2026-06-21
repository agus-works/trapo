import type {
  DiagnosticAnalyticsPayload,
  DiagnosticModelsPayload,
  DiagnosticProgressPayload,
} from '../../diagnostics/types';
import { anonymizedFileHash } from './anonymizedData';

const maxContextTokens = 262144;

export const diagnosticProgress: DiagnosticProgressPayload = {
  batches: [
    {
      duration_ms: 94000,
      error: null,
      execution_key: 'lmstudio:anonymized-local-api:sample-parser-model',
      finished_at: '2026-01-05T10:04:30Z',
      ingest_run_id: 12,
      lease_id: 1,
      metadata: { load_status: 'loaded_max' },
      model: 'sample-parser-model',
      provider: 'lmstudio',
      requested_context_tokens: maxContextTokens,
      started_at: '2026-01-05T10:02:56Z',
      status: 'ok',
      verified_context_tokens: maxContextTokens,
    },
    {
      duration_ms: null,
      error: null,
      execution_key: 'lmstudio:anonymized-local-api:sample-parser-model',
      finished_at: null,
      ingest_run_id: 12,
      lease_id: 2,
      metadata: { load_status: 'running' },
      model: 'sample-parser-model',
      provider: 'lmstudio',
      requested_context_tokens: maxContextTokens,
      started_at: '2026-01-05T10:05:00Z',
      status: 'running',
      verified_context_tokens: null,
    },
  ],
  summary: {
    completed_units: 5,
    estimated_remaining_ms: 186000,
    failed_units: 1,
    ingest_run_id: 12,
    percent_complete: 54.5,
    planned_units: 4,
    running_units: 1,
    skipped_units: 0,
    total_units: 11,
  },
  work_units: [
    workUnit({
      durationMs: 32000,
      engine: 'docling',
      phase: 'annotation',
      status: 'ok',
      workUnitId: 1,
    }),
    workUnit({
      durationMs: 94000,
      engine: 'infinity',
      model: 'sample-parser-model',
      phase: 'annotation',
      provider: 'local-infinity-parser2',
      status: 'ok',
      workUnitId: 2,
    }),
    workUnit({
      engine: 'infinity_markdown',
      model: 'sample-parser-model',
      phase: 'markdown',
      provider: 'local-infinity-parser2',
      status: 'running',
      workUnitId: 3,
    }),
    workUnit({
      engine: 'infinity_markdown',
      error: 'An anonymized parser output validation error.',
      model: 'sample-parser-model',
      phase: 'markdown',
      provider: 'local-infinity-parser2',
      status: 'error',
      workUnitId: 4,
    }),
  ],
};

export const diagnosticAnalytics: DiagnosticAnalyticsPayload = {
  error_breakdown: [
    breakdown('sample-local-vision-model', 'sample-local-vision-model', 42000, 4, 38),
  ],
  engine_breakdown: [
    breakdown('annotation:infinity', 'annotation / infinity', 94000, 1, 45),
    breakdown('markdown:infinity_markdown', 'markdown / infinity_markdown', 61000, 1, 29),
    breakdown('annotation:docling', 'annotation / docling', 32000, 1, 15),
  ],
  file_breakdown: [
    breakdown('anon-file-1', 'anonymized-document.pdf', 144000, 4, 68),
    breakdown('anon-file-2', 'anonymized-image.jpg', 34000, 2, 16),
  ],
  model_breakdown: [
    breakdown(
      'local-infinity-parser2:sample-parser-model',
      'local-infinity-parser2 / parser',
      94000,
      1,
      45,
    ),
    breakdown(
      'local-infinity-parser2:sample-parser-model',
      'local-infinity-parser2 / parser',
      61000,
      1,
      29,
    ),
  ],
  page_breakdown: [
    breakdown('anon-file-1:2', 'anonymized-document.pdf · page 2', 88000, 3, 42),
    breakdown('anon-file-1:1', 'anonymized-document.pdf · page 1', 56000, 2, 26),
  ],
  phase_breakdown: [
    breakdown('annotation', 'annotation', 126000, 3, 60),
    breakdown('markdown', 'markdown', 61000, 1, 29),
  ],
  recommendations: [
    {
      detail: 'Synthetic failed Infinity Parser2 calls consume a large share of this sample run.',
      evidence: { failed_llm_duration_ms: 42000 },
      id: 'failed-llm-cost',
      severity: 'high',
      title: 'Failed Infinity Parser2 calls dominate useful work',
    },
  ],
  slow_spans: [
    {
      annotation_engine: 'infinity_markdown',
      category: 'infinity',
      duration_ms: 42000,
      error_message: 'An anonymized invalid JSON response.',
      error_type: 'ExampleStructuredOutputError',
      file_hash: anonymizedFileHash,
      page_no: 2,
      pipeline_step: 'infinity_parser2',
      span_id: 'anon-slow-span',
      status: 'error',
      trace_id: 'anon-trace-0001',
    },
  ],
  slow_work_units: diagnosticProgress.work_units,
  summary: {
    duration_ms: 211000,
    failed_llm_duration_ms: 42000,
    failed_span_count: 3,
    failed_work_unit_count: 1,
    finished_at: '2026-01-05T10:18:33Z',
    ingest_run_id: 12,
    model_lease_count: 2,
    source_directory: 'C:\\Sample\\Corpus',
    span_count: 24,
    started_at: '2026-01-05T10:15:02Z',
    status: 'completed_with_errors',
    work_unit_count: 11,
  },
};

export const diagnosticModels: DiagnosticModelsPayload = {
  ingest_run_id: 12,
  leases: diagnosticProgress.batches.map((batch, index) => ({
    ...batch,
    load_status: typeof batch.metadata.load_status === 'string' ? batch.metadata.load_status : null,
    requested_parameters: { repeat_penalty: 1.2 },
    switch_index: index + 1,
  })),
};

function workUnit({
  durationMs = null,
  engine,
  error = null,
  model = 'sample-local-model',
  phase,
  provider = 'local',
  status,
  workUnitId,
}: {
  engine: string;
  phase: string;
  status: string;
  workUnitId: number;
  durationMs?: number | null;
  error?: string | null;
  model?: string;
  provider?: string;
}) {
  return {
    artifact_variant: null,
    attempt_count: status === 'planned' ? 0 : 1,
    duration_ms: durationMs,
    engine,
    error,
    execution_key:
      provider === 'local-lmstudio' ? `lmstudio:anonymized-local-api:${model}` : provider,
    file_hash: anonymizedFileHash,
    finished_at: durationMs === null ? null : '2026-01-05T10:04:30Z',
    ingest_run_id: 12,
    metadata: { source_path: 'anonymized-document.pdf' },
    model,
    page_no: null,
    phase,
    profile: null,
    provider,
    result: {},
    started_at: status === 'planned' ? null : '2026-01-05T10:02:56Z',
    status,
    work_key: `${phase}:${engine}:anonymized`,
    work_unit_id: workUnitId,
  };
}

function breakdown(
  id: string,
  label: string,
  durationMs: number,
  unitCount: number,
  sharePercent: number,
) {
  return {
    duration_ms: durationMs,
    error_count: id.includes('sample-local-vision') ? 1 : 0,
    file_count: 1,
    id,
    label,
    max_duration_ms: durationMs,
    metadata: {},
    page_count: 1,
    share_percent: sharePercent,
    unit_count: unitCount,
  };
}
