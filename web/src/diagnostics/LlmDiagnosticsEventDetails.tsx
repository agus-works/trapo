import styles from './LlmDiagnosticsEventDetails.module.css';
import type { DiagnosticEventRecord } from './types';

interface LlmDiagnosticsEventDetailsProps {
  events: DiagnosticEventRecord[];
}

const EVENT_TITLES: Record<string, string> = {
  'llm.error': 'LLM error',
  'llm.request': 'LLM request',
  'llm.response': 'LLM response',
};

export function LlmDiagnosticsEventDetails({ events }: LlmDiagnosticsEventDetailsProps) {
  const llmEvents = events.filter((event) => event.name.startsWith('llm.'));
  if (llmEvents.length === 0) {
    return null;
  }
  return (
    <section>
      <h3>LLM diagnostics</h3>
      <div className={styles.eventStack}>
        {llmEvents.map((event) => (
          <LlmEventCard event={event} key={event.event_id} />
        ))}
      </div>
    </section>
  );
}

function LlmEventCard({ event }: { event: DiagnosticEventRecord }) {
  const attrs = event.attributes;
  const prompt = textAttr(attrs, 'llm.request.prompt');
  const systemPrompt = textAttr(attrs, 'llm.request.system_prompt');
  const attachment = objectAttr(attrs, 'llm.attachment');
  const attachmentPath = textAttr(attachment, 'file_path');
  const parameters = objectAttr(attrs, 'llm.request.parameters');
  const requestPayload = attrs['llm.request.payload'];
  const responseContent = textAttr(attrs, 'llm.response.content');
  const rawResponse = attrs['llm.response.raw_json'];
  const errorResponseText = textAttr(attrs, 'llm.error.response_text');
  const errorResponseJson = attrs['llm.error.response_json'];

  return (
    <article className={styles.eventCard} data-severity={event.severity}>
      <header>
        <strong>{EVENT_TITLES[event.name] ?? event.name}</strong>
        <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
      </header>
      <dl className={styles.eventMeta}>
        <dt>Stage</dt>
        <dd>{textAttr(attrs, 'llm.stage') ?? '-'}</dd>
        <dt>Model</dt>
        <dd>{textAttr(attrs, 'llm.model') ?? '-'}</dd>
        <dt>Status</dt>
        <dd>{numberOrText(attrs['llm.response.status_code'] ?? attrs['llm.error.status_code'])}</dd>
        <dt>Elapsed</dt>
        <dd>{formatElapsed(attrs['llm.response.elapsed_ms'] ?? attrs['llm.error.elapsed_ms'])}</dd>
      </dl>
      {attachmentPath && (
        <div className={styles.attachment}>
          <a href={fileHref(attachmentPath)} rel="noreferrer" target="_blank">
            Open prompt attachment
          </a>
          <code>{attachmentPath}</code>
        </div>
      )}
      <JsonBlock label="Parameters" value={parameters} />
      <TextBlock label="System prompt" value={systemPrompt} />
      <TextBlock label="Prompt" value={prompt} />
      <JsonBlock label="Sanitized request payload" value={requestPayload} />
      <TextBlock label="Assistant content" value={responseContent} />
      <JsonBlock label="Raw response" value={rawResponse} />
      <TextBlock label="Error response body" value={errorResponseText} />
      <JsonBlock label="Error response JSON" value={errorResponseJson} />
    </article>
  );
}

function TextBlock({ label, value }: { label: string; value?: string | null }) {
  if (!value) {
    return null;
  }
  return (
    <details className={styles.eventBlock}>
      <summary>{label}</summary>
      <pre>{value}</pre>
    </details>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null) {
    return null;
  }
  return (
    <details className={styles.eventBlock}>
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function objectAttr(value: unknown, key: string): Record<string, unknown> | null {
  const item = key ? (value as Record<string, unknown> | null)?.[key] : value;
  return item !== null && typeof item === 'object' && !Array.isArray(item)
    ? (item as Record<string, unknown>)
    : null;
}

function textAttr(value: unknown, key: string): string | null {
  const item = key ? (value as Record<string, unknown> | null)?.[key] : value;
  return typeof item === 'string' && item.length > 0 ? item : null;
}

function numberOrText(value: unknown): string {
  if (typeof value === 'number' || typeof value === 'string') {
    return String(value);
  }
  return '-';
}

function formatElapsed(value: unknown): string {
  return typeof value === 'number' ? `${value.toFixed(1)}ms` : '-';
}

function fileHref(path: string): string {
  const normalized = path.replaceAll('\\', '/');
  return normalized.startsWith('/') ? `file://${normalized}` : `file:///${normalized}`;
}
