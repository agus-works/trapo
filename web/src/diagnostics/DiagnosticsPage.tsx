import { useNavigate, useSearch } from '@tanstack/react-router';
import type { DiagnosticsRouteSearch } from '../routeSearch';
import { DiagnosticsTimelineView } from './DiagnosticsTimelineView';

export function DiagnosticsPage() {
  const search = useSearch({ from: '/diagnostics' }) as DiagnosticsRouteSearch;
  const navigate = useNavigate({ from: '/diagnostics' });
  return (
    <DiagnosticsTimelineView
      runId={search.run ?? null}
      selectedSpanId={search.span ?? null}
      onRunChange={(run) => void navigate({ search: (current) => ({ ...current, run }) })}
      onSpanSelect={(span) => void navigate({ search: (current) => ({ ...current, span }) })}
    />
  );
}
