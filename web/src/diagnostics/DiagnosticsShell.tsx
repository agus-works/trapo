import { useNavigate } from '@tanstack/react-router';
import { Activity, BarChart3, GitBranch, Layers3 } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { WorkbenchTabs } from '../components/workbench';
import { useDiagnosticRunsQuery } from '../queries/hooks';
import styles from './DiagnosticsShell.module.css';
import { runLabel } from './diagnosticsFormat';
import type { DiagnosticRunRecord } from './types';

type DiagnosticsTabId = 'progress' | 'performance' | 'models' | 'waterfall';

const tabs = [
  { id: 'progress', label: 'Progress', icon: <GitBranch size={14} /> },
  { id: 'performance', label: 'Performance', icon: <BarChart3 size={14} /> },
  { id: 'models', label: 'Models', icon: <Layers3 size={14} /> },
  { id: 'waterfall', label: 'Waterfall', icon: <Activity size={14} /> },
];

const tabRoutes = {
  progress: '/diagnostics/progress',
  performance: '/diagnostics/performance',
  models: '/diagnostics/models',
  waterfall: '/diagnostics/waterfall',
} as const satisfies Record<DiagnosticsTabId, string>;

export function DiagnosticsShell({
  activeTab,
  children,
}: {
  activeTab: DiagnosticsTabId;
  children: ReactNode;
}) {
  const navigate = useNavigate({ from: '/diagnostics' });
  return (
    <div className={styles.shell}>
      <div className={styles.tabBar}>
        <WorkbenchTabs
          active={activeTab}
          ariaLabel="Diagnostics sections"
          onChange={(tabId) =>
            void navigate({
              search: (current) => current,
              to: tabRoutes[tabId as DiagnosticsTabId],
            })
          }
          storageKey="trapo.diagnostics.tabs"
          tabs={tabs}
        />
      </div>
      <div className={styles.content}>{children}</div>
    </div>
  );
}

export function DiagnosticsRunBar({
  runId,
  onRunChange,
  summary,
}: {
  runId?: number | null;
  onRunChange: (runId: number) => void;
  summary?: ReactNode;
}) {
  const { effectiveRunId, runs } = useDiagnosticsRunSelection(runId, onRunChange);
  return (
    <div className={styles.runBar}>
      <select
        aria-label="Ingest run"
        onChange={(event) => onRunChange(Number(event.target.value))}
        value={effectiveRunId ?? ''}
      >
        {runs.map((run) => (
          <option key={run.ingest_run_id} value={run.ingest_run_id}>
            {runLabel(run)}
          </option>
        ))}
      </select>
      {summary && <span className={styles.runBarSummary}>{summary}</span>}
    </div>
  );
}

export function useDiagnosticsRunSelection(
  runId: number | null | undefined,
  onRunChange?: (runId: number) => void,
) {
  const runsQuery = useDiagnosticRunsQuery();
  const runs = runsQuery.data ?? [];
  const effectiveRunId = runId ?? runs[0]?.ingest_run_id ?? null;

  useEffect(() => {
    if (runId === undefined && effectiveRunId !== null) {
      onRunChange?.(effectiveRunId);
    }
  }, [effectiveRunId, onRunChange, runId]);

  return { effectiveRunId, runs };
}

export function latestRunSummary(runs: DiagnosticRunRecord[], runId: number | null): string {
  const run = runs.find((item) => item.ingest_run_id === runId);
  if (!run) {
    return 'No diagnostic run selected';
  }
  return `${run.file_count} files · ${run.page_count} pages · ${run.span_count} spans`;
}
