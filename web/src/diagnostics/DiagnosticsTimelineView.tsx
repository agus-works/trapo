import { useEffect, useMemo, useState } from 'react';
import { useDiagnosticRunsQuery, useDiagnosticTraceQuery } from '../queries/hooks';
import { DiagnosticsTimelinePanels } from './DiagnosticsTimelinePanels';
import { DiagnosticsTimelineToolbar } from './DiagnosticsTimelineToolbar';
import styles from './DiagnosticsTimelineView.module.css';
import { buildRows, firstErrorId } from './diagnosticsTimelineRows';

interface DiagnosticsTimelineViewProps {
  fileHash?: string | null;
  pageNo?: number | null;
  runId?: number | null;
  selectedSpanId?: string | null;
  onRunChange?: (runId: number) => void;
  onSpanSelect?: (spanId: string) => void;
}

export function DiagnosticsTimelineView(props: DiagnosticsTimelineViewProps) {
  const state = useDiagnosticsTimelineState(props);

  return (
    <div className={styles.timelineShell}>
      <DiagnosticsTimelineToolbar
        effectiveRunId={state.effectiveRunId}
        onQueryChange={state.setQuery}
        onRunSelect={state.selectRun}
        onStatusChange={state.setStatus}
        query={state.query}
        runs={state.runs}
        status={state.status}
        trace={state.trace}
      />
      <DiagnosticsTimelinePanels
        events={state.trace?.events ?? []}
        onSpanSelect={state.selectSpan}
        rows={state.rows}
        selectedId={state.selectedId}
        selectedSpan={state.selectedSpan}
        summary={state.trace?.summary ?? null}
      />
    </div>
  );
}

function useDiagnosticsTimelineState({
  fileHash,
  pageNo,
  runId,
  selectedSpanId,
  onRunChange,
  onSpanSelect,
}: DiagnosticsTimelineViewProps) {
  const runsQuery = useDiagnosticRunsQuery();
  const runs = runsQuery.data ?? [];
  const [localRunId, setLocalRunId] = useState<number | null>(null);
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [localSelectedSpanId, setLocalSelectedSpanId] = useState<string | null>(null);
  const effectiveRunId = useEffectiveRunId(runId, localRunId, runs, setLocalRunId);
  const traceQuery = useDiagnosticTraceQuery({
    fileHash,
    ingestRunId: effectiveRunId,
    pageNo,
    q: query,
    status,
  });
  const trace = traceQuery.data;
  const rows = useMemo(() => buildRows(trace?.spans ?? []), [trace?.spans]);
  const selectedId = selectedSpanId ?? localSelectedSpanId ?? firstErrorId(rows);
  const selectedSpan = rows.find((row) => row.span.span_id === selectedId)?.span ?? null;
  const selectRun = (nextRun: number) => {
    setLocalRunId(nextRun);
    onRunChange?.(nextRun);
  };
  const selectSpan = (spanId: string) => {
    setLocalSelectedSpanId(spanId);
    onSpanSelect?.(spanId);
  };

  return {
    effectiveRunId,
    query,
    rows,
    runs,
    selectedId,
    selectedSpan,
    selectRun,
    selectSpan,
    setQuery,
    setStatus,
    status,
    trace,
  };
}

function useEffectiveRunId(
  runId: number | null | undefined,
  localRunId: number | null,
  runs: { ingest_run_id: number }[],
  setLocalRunId: (runId: number) => void,
): number | null {
  useEffect(() => {
    if (runId === undefined && localRunId === null && runs[0]) {
      setLocalRunId(runs[0].ingest_run_id);
    }
  }, [localRunId, runId, runs, setLocalRunId]);
  return runId ?? localRunId ?? runs[0]?.ingest_run_id ?? null;
}
