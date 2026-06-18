import styles from './DiagnosticsDetailsPane.module.css';
import type { DiagnosticSpanRecord } from './types';

export function DiagnosticsSpanFailure({ span }: { span: DiagnosticSpanRecord }) {
  if (!span.error_message) {
    return null;
  }
  return (
    <section className={styles.errorBlock}>
      <h3>{span.error_type ?? 'Failure'}</h3>
      <p>{span.error_message}</p>
      {span.error_stack && <pre>{span.error_stack}</pre>}
    </section>
  );
}
