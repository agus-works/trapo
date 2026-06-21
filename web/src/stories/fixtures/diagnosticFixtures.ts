import type {
  DiagnosticEventRecord,
  DiagnosticRunRecord,
  DiagnosticSpanRecord,
  DiagnosticTracePayload,
} from '../../diagnostics/types';
import { anonymizedFileHash } from './anonymizedData';

const traceId = 'anon-trace-0001';
const sampleAttachmentPath = 'C:\\Sample\\Cache\\llm-diagnostics\\page-0002.jpg';

export const diagnosticRuns: DiagnosticRunRecord[] = [
  {
    duration_ms: 1113692,
    error_count: 1,
    file_count: 4,
    finished_at: '2026-01-05T10:18:33Z',
    ingest_run_id: 12,
    page_count: 9,
    source_directory: 'C:\\Sample\\Corpus',
    span_count: 9,
    started_at: '2026-01-05T10:00:00Z',
    status: 'completed_with_errors',
  },
];

export const diagnosticSpans: DiagnosticSpanRecord[] = [
  span({ durationMs: 540000, name: 'trapo.ingest.file', spanId: 'file', status: 'error' }),
  span({
    category: 'docling',
    durationMs: 38000,
    name: 'trapo.ingest.docling_read',
    offsetMs: 2000,
    parentSpanId: 'file',
    spanId: 'docling',
    status: 'ok',
    step: 'docling_read',
  }),
  span({
    category: 'preview',
    durationMs: 9000,
    name: 'trapo.ingest.preview_cache',
    offsetMs: 42000,
    parentSpanId: 'file',
    spanId: 'preview',
    status: 'ok',
    step: 'preview_cache',
  }),
  span({
    durationMs: 61000,
    name: 'trapo.ingest.page_markdown',
    offsetMs: 58000,
    parentSpanId: 'file',
    spanId: 'markdown',
    status: 'error',
    step: 'page_markdown',
  }),
  span({
    durationMs: 12000,
    name: 'trapo.ingest.page_markdown.page',
    offsetMs: 59000,
    pageNo: 1,
    parentSpanId: 'markdown',
    spanId: 'page-1',
    status: 'ok',
  }),
  span({
    durationMs: 36000,
    name: 'trapo.ingest.page_markdown.page',
    offsetMs: 72000,
    pageNo: 2,
    parentSpanId: 'markdown',
    spanId: 'page-2',
    status: 'error',
  }),
  span({
    durationMs: 416000,
    name: 'trapo.ingest.markitdown_markdown',
    offsetMs: 124000,
    parentSpanId: 'file',
    spanId: 'markitdown',
    status: 'ok',
    step: 'markitdown_markdown',
  }),
];

export const diagnosticEvents: DiagnosticEventRecord[] = [
  {
    attributes: {
      'llm.attachment': {
        bytes: 81244,
        file_path: sampleAttachmentPath,
        mime_type: 'image/jpeg',
        page_no: 2,
        render_height: 1280,
        render_width: 904,
        sha256: 'anon-image-sha256',
      },
      'llm.endpoint': 'anonymized-local-lmstudio-chat-endpoint',
      'llm.model': 'sample-local-vision-model',
      'llm.provider': 'lmstudio',
      'llm.request.parameters': {
        max_tokens: 262144,
        schema_name: null,
        stream: false,
        structured_output: false,
        temperature: 0,
      },
      'llm.request.payload': {
        max_tokens: 262144,
        messages: [
          { content: 'Return faithful Markdown for this page.', role: 'system' },
          {
            content: [
              { text: 'Convert anonymized page 2 to Markdown.', type: 'text' },
              {
                image_url: {
                  attachment: { file_path: sampleAttachmentPath },
                  url: '[diagnostic attachment on filesystem]',
                },
                type: 'image_url',
              },
            ],
            role: 'user',
          },
        ],
        model: 'sample-local-vision-model',
        stream: false,
        temperature: 0,
      },
      'llm.request.prompt': 'Convert anonymized page 2 to Markdown.',
      'llm.request.system_prompt': 'Return faithful Markdown for this page.',
      'llm.stage': 'page_markdown',
      'page.no': 2,
    },
    event_id: 10,
    event_type: 'llm.request',
    file_hash: anonymizedFileHash,
    ingest_run_id: 12,
    message: 'LM Studio request: stage=page_markdown model=sample-local-vision-model page=2',
    name: 'llm.request',
    page_no: 2,
    severity: 'info',
    span_id: 'page-2',
    timestamp: '2026-01-05T10:01:13Z',
    trace_id: traceId,
  },
  {
    attributes: {
      'llm.error.elapsed_ms': 24112.4,
      'llm.error.message': '400 Bad Request: context length exceeded for anonymized prompt.',
      'llm.error.response_text':
        '{"error":"The prompt exceeded the local model context window in this anonymized fixture."}',
      'llm.error.status_code': 400,
      'llm.error.type': 'HTTPStatusError',
      'llm.model': 'sample-local-vision-model',
      'llm.provider': 'lmstudio',
      'llm.stage': 'page_markdown',
      'page.no': 2,
    },
    event_id: 11,
    event_type: 'llm.error',
    file_hash: anonymizedFileHash,
    ingest_run_id: 12,
    message:
      'LM Studio error: stage=page_markdown model=sample-local-vision-model page=2 status=400',
    name: 'llm.error',
    page_no: 2,
    severity: 'error',
    span_id: 'page-2',
    timestamp: '2026-01-05T10:01:47Z',
    trace_id: traceId,
  },
  {
    attributes: { phase: 'progress' },
    event_id: 1,
    event_type: 'log',
    file_hash: anonymizedFileHash,
    ingest_run_id: 12,
    message: 'Generating anonymized page Markdown: page=2 evidence=4 render=900x1280',
    name: 'log',
    page_no: 2,
    severity: 'info',
    span_id: 'page-2',
    timestamp: '2026-01-05T10:01:12Z',
    trace_id: traceId,
  },
  {
    attributes: { 'exception.type': 'ExampleStructuredOutputError' },
    event_id: 2,
    event_type: 'exception',
    file_hash: anonymizedFileHash,
    ingest_run_id: 12,
    message: 'The model returned an empty Markdown payload for this anonymized page.',
    name: 'exception',
    page_no: 2,
    severity: 'error',
    span_id: 'page-2',
    timestamp: '2026-01-05T10:01:48Z',
    trace_id: traceId,
  },
];

export const diagnosticTrace: DiagnosticTracePayload = {
  events: diagnosticEvents,
  spans: diagnosticSpans,
  summary: {
    duration_ms: 540000,
    ended_at: '2026-01-05T10:09:00Z',
    error_count: 2,
    file_count: 1,
    ingest_run_id: 12,
    page_count: 2,
    span_count: diagnosticSpans.length,
    started_at: '2026-01-05T10:00:00Z',
  },
};

interface SpanFixture {
  durationMs: number;
  name: string;
  spanId: string;
  category?: string;
  offsetMs?: number;
  pageNo?: number | null;
  parentSpanId?: string | null;
  status?: string;
  step?: string;
}

function span({
  category = 'markdown',
  durationMs,
  name,
  offsetMs = 0,
  pageNo = null,
  parentSpanId = null,
  spanId,
  status = 'ok',
  step = 'page_markdown_page',
}: SpanFixture): DiagnosticSpanRecord {
  const startedAt = new Date(Date.UTC(2026, 0, 5, 10, 0, 0) + offsetMs);
  return {
    annotation_engine: category === 'markdown' ? 'infinity_markdown' : null,
    attributes: { 'file.hash': anonymizedFileHash, 'pipeline.step': step },
    category,
    duration_ms: durationMs,
    ended_at: new Date(startedAt.getTime() + durationMs).toISOString(),
    error_message:
      status === 'error' ? 'An anonymized pipeline step failed with a sample error.' : null,
    error_stack: status === 'error' ? 'Error: anonymized failure\n    at sampleStep()' : null,
    error_type: status === 'error' ? 'ExamplePipelineError' : null,
    file_hash: anonymizedFileHash,
    ingest_run_id: 12,
    name,
    page_no: pageNo,
    parent_span_id: parentSpanId,
    pipeline_step: step,
    span_id: spanId,
    started_at: startedAt.toISOString(),
    status,
    trace_id: traceId,
  };
}
