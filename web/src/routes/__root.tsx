import type { QueryClient } from '@tanstack/react-query';
import { createRootRouteWithContext } from '@tanstack/react-router';
import { AppShell } from '../AppShell';

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient;
}>()({
  component: AppShell,
  notFoundComponent: () => <div className="emptyState">Page not found.</div>,
});
