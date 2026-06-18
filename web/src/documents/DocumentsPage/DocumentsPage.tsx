import { DocumentsPageLayout } from './DocumentsPageLayout';
import { useDocumentsPageState } from './useDocumentsPageState';

export function DocumentsPage() {
  return <DocumentsPageLayout view={useDocumentsPageState()} />;
}
