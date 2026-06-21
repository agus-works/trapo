import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { DiagnosticsAnalyticsView } from '../diagnostics/DiagnosticsAnalyticsView';
import { DiagnosticsRunBar, DiagnosticsShell } from '../diagnostics/DiagnosticsShell';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics/performance')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsPerformanceRoute,
});

function DiagnosticsPerformanceRoute() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: '/diagnostics/performance' });
  return (
    <DiagnosticsShell activeTab="performance">
      <DiagnosticsRunBar
        onRunChange={(run) => void navigate({ search: (current) => ({ ...current, run }) })}
        runId={search.run}
        summary="Duration, error cost, throughput, and bottleneck reports"
      />
      <DiagnosticsAnalyticsView runId={search.run ?? null} />
    </DiagnosticsShell>
  );
}
