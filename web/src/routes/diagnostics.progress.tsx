import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { DiagnosticsProgressView } from '../diagnostics/DiagnosticsProgressView';
import { DiagnosticsRunBar, DiagnosticsShell } from '../diagnostics/DiagnosticsShell';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics/progress')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsProgressRoute,
});

function DiagnosticsProgressRoute() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: '/diagnostics/progress' });
  const expandedIds = expandedSet(search.expanded);
  return (
    <DiagnosticsShell activeTab="progress">
      <DiagnosticsRunBar
        onRunChange={(run) => void navigate({ search: (current) => ({ ...current, run }) })}
        runId={search.run}
        summary="Progress by file, page, phase, and task"
      />
      <DiagnosticsProgressView
        expandedIds={expandedIds}
        onExpandedChange={(next) =>
          void navigate({
            search: (current) => ({ ...current, expanded: serializeExpanded(next) }),
          })
        }
        onUnitSelect={(unit) => void navigate({ search: (current) => ({ ...current, unit }) })}
        runId={search.run ?? null}
        selectedUnitId={search.unit ?? null}
      />
    </DiagnosticsShell>
  );
}

function expandedSet(value: string | undefined): Set<string> {
  return new Set((value ?? '').split(',').filter(Boolean));
}

function serializeExpanded(value: Set<string>): string | undefined {
  const serialized = [...value].join(',');
  return serialized || undefined;
}
