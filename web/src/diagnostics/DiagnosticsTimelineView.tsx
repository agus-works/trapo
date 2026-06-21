import { useEffect, useMemo, useState } from 'react';
import { useDiagnosticRunsQuery, useDiagnosticTraceQuery } from '../queries/hooks';
import { DiagnosticsProgressView } from './DiagnosticsProgressView';
import { DiagnosticsTimelinePanels } from './DiagnosticsTimelinePanels';
import { DiagnosticsTimelineToolbar } from './DiagnosticsTimelineToolbar';
import styles from './DiagnosticsTimelineView.module.css';
import { buildRows, firstErrorId } from './diagnosticsTimelineRows';

interface DiagnosticsTimelineViewProps {
  fileHash?: string | null;
  pageNo?: number | null;
  query?: string | null;
  runId?: number | null;
  selectedSpanId?: string | null;
  showProgress?: boolean;
  status?: string | null;
  onQueryChange?: (query: string) => void;
  onRunChange?: (runId: number) => void;
  onSpanSelect?: (spanId: string) => void;
  onStatusChange?: (status: string) => void;
}

export function DiagnosticsTimelineView(props: DiagnosticsTimelineViewProps) {
  const state = useDiagnosticsTimelineState(props);
  const showProgress = props.showProgress !== false;

  return (
    <div className={styles.timelineShell} data-show-progress={showProgress}>
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
      {showProgress && (
        <DiagnosticsProgressView
          expandedIds={new Set<string>()}
          onExpandedChange={() => undefined}
          onUnitSelect={() => undefined}
          runId={state.effectiveRunId}
        />
      )}
      <DiagnosticsTimelinePanels
        events={state.trace?.events ?? []}
        onSpanSelect={state.selectSpan}
        rows={state.rows}
        selectedId={state.selectedId}
        selectedSpan={state.selectedSpan}
        summary={state.trace?.summary ?? null}
        traceError={state.traceError}
        traceLoading={state.traceLoading}
      />
    </div>
  );
}

function useDiagnosticsTimelineState({
  fileHash,
  pageNo,
  runId,
  selectedSpanId,
  query: externalQuery,
  status: externalStatus,
  onQueryChange,
  onRunChange,
  onSpanSelect,
  onStatusChange,
}: DiagnosticsTimelineViewProps) {
  const runsQuery = useDiagnosticRunsQuery();
  const runs = runsQuery.data ?? [];
  const [localRunId, setLocalRunId] = useState<number | null>(null);
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [localSelectedSpanId, setLocalSelectedSpanId] = useState<string | null>(null);
  const effectiveRunId = useEffectiveRunId(runId, localRunId, runs, setLocalRunId);
  const effectiveStatus = externalStatus ?? status;
  const effectiveQuery = externalQuery ?? query;
  const traceQuery = useDiagnosticTraceQuery({
    fileHash,
    ingestRunId: effectiveRunId,
    pageNo,
    q: effectiveQuery,
    status: effectiveStatus,
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
  const updateQuery = (nextQuery: string) => {
    setQuery(nextQuery);
    onQueryChange?.(nextQuery);
  };
  const updateStatus = (nextStatus: string) => {
    setStatus(nextStatus);
    onStatusChange?.(nextStatus);
  };
  const traceError = traceQuery.isError
    ? traceQuery.error instanceof Error
      ? traceQuery.error.message
      : 'Unable to load diagnostics trace.'
    : null;

  return {
    effectiveRunId,
    query: effectiveQuery,
    rows,
    runs,
    selectedId,
    selectedSpan,
    selectRun,
    selectSpan,
    setQuery: updateQuery,
    setStatus: updateStatus,
    status: effectiveStatus,
    trace,
    traceError,
    traceLoading: traceQuery.isPending || (traceQuery.isFetching && !trace),
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
