import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { DiagnosticsShell } from '../diagnostics/DiagnosticsShell';
import { DiagnosticsTimelineView } from '../diagnostics/DiagnosticsTimelineView';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics/waterfall')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsWaterfallRoute,
});

function DiagnosticsWaterfallRoute() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: '/diagnostics/waterfall' });
  return (
    <DiagnosticsShell activeTab="waterfall">
      <DiagnosticsTimelineView
        onQueryChange={(q) =>
          void navigate({ search: (current) => ({ ...current, q: q || undefined }) })
        }
        onRunChange={(run) => void navigate({ search: (current) => ({ ...current, run }) })}
        onSpanSelect={(span) => void navigate({ search: (current) => ({ ...current, span }) })}
        onStatusChange={(status) =>
          void navigate({
            search: (current) => ({
              ...current,
              status: routeStatus(status),
            }),
          })
        }
        query={search.q ?? ''}
        runId={search.run ?? null}
        selectedSpanId={search.span ?? null}
        showProgress={false}
        status={search.status ?? 'all'}
      />
    </DiagnosticsShell>
  );
}

function routeStatus(status: string): 'ok' | 'error' | 'skipped' | undefined {
  if (status === 'ok' || status === 'error' || status === 'skipped') {
    return status;
  }
  return undefined;
}
