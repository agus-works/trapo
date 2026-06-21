import { createFileRoute, Outlet } from '@tanstack/react-router';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsLayout,
});

function DiagnosticsLayout() {
  return <Outlet />;
}
