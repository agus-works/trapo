import { createFileRoute, Navigate } from '@tanstack/react-router';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics/')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsIndexRedirect,
});

function DiagnosticsIndexRedirect() {
  const search = Route.useSearch();
  return <Navigate replace search={search} to="/diagnostics/progress" />;
}
