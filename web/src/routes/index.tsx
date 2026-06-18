import { createFileRoute } from '@tanstack/react-router';
import { DocumentsPage } from '../App';
import { validateDocumentSearch } from '../routeSearch';

export const Route = createFileRoute('/')({
  validateSearch: validateDocumentSearch,
  component: DocumentsPage,
});
