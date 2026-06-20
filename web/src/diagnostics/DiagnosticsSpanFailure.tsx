import styles from './DiagnosticsDetailsPane.module.css';
import type { DiagnosticSpanRecord } from './types';

export function DiagnosticsSpanFailure({ span }: { span: DiagnosticSpanRecord }) {
  if (!span.error_message) {
    return null;
  }
  return (
    <section className={styles.errorBlock}>
      <h3>{span.error_type ?? 'Failure'}</h3>
      <details open={span.error_message.length < 700}>
        <summary>{clipText(span.error_message, 220)}</summary>
        <pre>{span.error_message}</pre>
      </details>
      {span.error_stack && (
        <details>
          <summary>Stack trace</summary>
          <pre>{span.error_stack}</pre>
        </details>
      )}
    </section>
  );
}

function clipText(value: string, maxLength: number): string {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength)}...`;
}
