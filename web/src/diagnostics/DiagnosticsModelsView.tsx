import { useDiagnosticModelsQuery } from '../queries/hooks';
import styles from './DiagnosticsModelsView.module.css';
import { formatDuration } from './diagnosticsFormat';
import type { DiagnosticModelLeaseRecord, DiagnosticModelsPayload } from './types';

export function DiagnosticsModelsView({ runId }: { runId: number | null }) {
  const modelsQuery = useDiagnosticModelsQuery(runId);
  const payload = modelsQuery.data;
  if (!payload) {
    return <div className={styles.empty}>Loading model leases...</div>;
  }
  return <DiagnosticsModelsPanel payload={payload} />;
}

export function DiagnosticsModelsPanel({ payload }: { payload: DiagnosticModelsPayload }) {
  const switches = payload.leases.length;
  const uniqueModels = new Set(payload.leases.map((lease) => lease.model)).size;
  const maxContextFailures = payload.leases.filter(
    (lease) =>
      lease.requested_context_tokens &&
      lease.verified_context_tokens &&
      lease.verified_context_tokens < lease.requested_context_tokens,
  ).length;
  return (
    <section className={styles.modelsShell}>
      <div className={styles.summary}>
        <SummaryCell label="Leases" value={switches} />
        <SummaryCell label="Unique models" value={uniqueModels} />
        <SummaryCell label="Context mismatches" value={maxContextFailures} />
        <SummaryCell label="Repeat penalty" value="1.2 requested" />
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.modelsTable}>
          <thead>
            <tr>
              <th>#</th>
              <th>Model</th>
              <th>Status</th>
              <th>Load status</th>
              <th>Context</th>
              <th>Parameters</th>
              <th>Duration</th>
              <th>Execution key</th>
            </tr>
          </thead>
          <tbody>
            {payload.leases.map((lease) => (
              <ModelLeaseRow key={lease.lease_id} lease={lease} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: number | string }) {
  return (
    <div className={styles.summaryCell}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ModelLeaseRow({ lease }: { lease: DiagnosticModelLeaseRecord }) {
  return (
    <tr>
      <td>{lease.switch_index}</td>
      <td>{lease.model}</td>
      <td>
        <span className={styles.status} data-status={lease.status}>
          {lease.status}
        </span>
      </td>
      <td>{lease.load_status ?? '-'}</td>
      <td>
        {formatContext(lease.verified_context_tokens)} /{' '}
        {formatContext(lease.requested_context_tokens)}
      </td>
      <td>
        <code>{JSON.stringify(lease.requested_parameters)}</code>
      </td>
      <td>{formatDuration(lease.duration_ms)}</td>
      <td>
        <code>{lease.execution_key}</code>
      </td>
    </tr>
  );
}

function formatContext(value: number | null | undefined): string {
  return value ? value.toLocaleString() : '-';
}
