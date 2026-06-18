import styles from './DiagnosticsDetailsPane.module.css';
import { DiagnosticsSpanFailure } from './DiagnosticsSpanFailure';
import { LlmDiagnosticsEventDetails } from './LlmDiagnosticsEventDetails';
import type { DiagnosticEventRecord, DiagnosticSpanRecord } from './types';

export function DiagnosticsDetailsPane({
  events,
  span,
}: {
  events: DiagnosticEventRecord[];
  span: DiagnosticSpanRecord | null;
}) {
  if (!span) {
    return <div className={styles.detailsEmpty}>Select a span to inspect timing and failures.</div>;
  }
  const spanEvents = events.filter((event) => event.span_id === span.span_id);
  return (
    <div className={styles.detailsPane}>
      <div className={styles.detailsHeader}>
        <strong>{span.pipeline_step}</strong>
        <span data-status={span.status}>{span.status}</span>
      </div>
      <SpanMetadata span={span} />
      <DiagnosticsSpanFailure span={span} />
      <LlmDiagnosticsEventDetails events={spanEvents} />
      <SpanEvents events={spanEvents} />
      <section>
        <h3>Attributes</h3>
        <pre>{JSON.stringify(span.attributes, null, 2)}</pre>
      </section>
    </div>
  );
}

function SpanMetadata({ span }: { span: DiagnosticSpanRecord }) {
  return (
    <dl className={styles.detailsGrid}>
      <dt>Duration</dt>
      <dd>{formatMs(span.duration_ms)}</dd>
      <dt>File</dt>
      <dd>{span.file_hash ?? 'all files'}</dd>
      <dt>Page</dt>
      <dd>{span.page_no ?? 'all pages'}</dd>
      <dt>Engine</dt>
      <dd>{span.annotation_engine ?? span.category}</dd>
      <dt>Span</dt>
      <dd>{span.span_id}</dd>
      <dt>Parent</dt>
      <dd>{span.parent_span_id ?? 'root'}</dd>
    </dl>
  );
}

function SpanEvents({ events }: { events: DiagnosticEventRecord[] }) {
  return (
    <section>
      <h3>Events</h3>
      {events.length > 0 ? (
        <ol className={styles.eventList}>
          {events.map((event) => (
            <li key={event.event_id}>
              <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
              <strong>{event.name}</strong>
              <p>{event.message}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.muted}>No events recorded for this span.</p>
      )}
    </section>
  );
}

function formatMs(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)}s`;
  }
  return `${value.toFixed(1)}ms`;
}
