import { createFileRoute } from '@tanstack/react-router';
import { DiagnosticsPage } from '../diagnostics';
import { validateDiagnosticsSearch } from '../routeSearch';

export const Route = createFileRoute('/diagnostics')({
  validateSearch: validateDiagnosticsSearch,
  component: DiagnosticsPage,
});
