import { Clock3, Search } from 'lucide-react';
import styles from './DiagnosticsTimelineToolbar.module.css';
import type { DiagnosticRunRecord, DiagnosticTracePayload } from './types';

interface DiagnosticsTimelineToolbarProps {
  effectiveRunId: number | null;
  runs: DiagnosticRunRecord[];
  status: string;
  query: string;
  trace: DiagnosticTracePayload | undefined;
  onRunSelect: (runId: number) => void;
  onStatusChange: (status: string) => void;
  onQueryChange: (query: string) => void;
}

export function DiagnosticsTimelineToolbar({
  effectiveRunId,
  runs,
  status,
  query,
  trace,
  onRunSelect,
  onStatusChange,
  onQueryChange,
}: DiagnosticsTimelineToolbarProps) {
  return (
    <div className={styles.toolbar}>
      <Clock3 size={15} />
      <select
        aria-label="Ingest run"
        onChange={(event) => onRunSelect(Number(event.target.value))}
        value={effectiveRunId ?? ''}
      >
        {runs.map((run) => (
          <option key={run.ingest_run_id} value={run.ingest_run_id}>
            {runLabel(run)}
          </option>
        ))}
      </select>
      <select
        aria-label="Status filter"
        onChange={(event) => onStatusChange(event.target.value)}
        value={status}
      >
        <option value="all">All statuses</option>
        <option value="error">Failures</option>
        <option value="ok">Succeeded</option>
        <option value="skipped">Skipped</option>
      </select>
      <label className={styles.searchBox}>
        <Search size={14} />
        <input
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Filter steps"
          value={query}
        />
      </label>
      <span className={styles.summary}>
        {trace?.summary.span_count ?? 0} spans · {trace?.summary.error_count ?? 0} failures
      </span>
    </div>
  );
}

function runLabel(run: DiagnosticRunRecord): string {
  const started = run.started_at
    ? new Date(run.started_at).toLocaleString()
    : `Run ${run.ingest_run_id}`;
  return `#${run.ingest_run_id} · ${started} · ${run.error_count} errors`;
}
