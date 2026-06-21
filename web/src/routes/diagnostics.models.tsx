import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { DiagnosticsModelsView } from '../diagnostics/DiagnosticsModelsView';
import { DiagnosticsRunBar, DiagnosticsShell } from '../diagnostics/DiagnosticsShell';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics/models')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsModelsRoute,
});

function DiagnosticsModelsRoute() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: '/diagnostics/models' });
  return (
    <DiagnosticsShell activeTab="models">
      <DiagnosticsRunBar
        onRunChange={(run) => void navigate({ search: (current) => ({ ...current, run }) })}
        runId={search.run}
        summary="LM Studio lease order, context, and load parameters"
      />
      <DiagnosticsModelsView runId={search.run ?? null} />
    </DiagnosticsShell>
  );
}
