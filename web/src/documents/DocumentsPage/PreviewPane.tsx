import { ResizablePanel } from '../../components/ui/resizable';
import { cn } from '../../lib/utils';
import { DocumentTopBar } from '../DocumentTopBar';
import styles from './DocumentsPage.module.css';
import { PreviewPaneBody } from './PreviewPaneBody';
import type { DocumentsPageView } from './types';

export function PreviewPane({ view }: { view: DocumentsPageView }) {
  const folderSelected =
    view.explorerSelection.kind === 'root' || view.explorerSelection.kind === 'directory';
  const diagnosticsSelection =
    view.explorerSelection.kind === 'diagnostics' ? view.explorerSelection : null;
  const folderTitle =
    view.explorerSelection.kind === 'directory' ? view.explorerSelection.label : 'Documents';
  const folderPath =
    view.explorerSelection.kind === 'directory' ? view.explorerSelection.pathKey : 'Workspace root';
  return (
    <ResizablePanel className={styles.mainPane} defaultSize={52} minSize={36}>
      <div
        className={cn(
          styles.previewPane,
          folderSelected && styles.folderPreviewPane,
          diagnosticsSelection && styles.diagnosticsPreviewPane,
        )}
      >
        <DocumentTopBar
          activeDocumentPath={folderSelected ? folderPath : (view.activeDocument?.path ?? null)}
          error={view.loadError}
          filename={folderSelected ? folderTitle : (view.activeDocument?.filename ?? null)}
          leftCollapsed={view.leftCollapsed}
          leftPanel={view.leftPanelRef.current}
          loading={view.loading}
          previewError={view.previewError}
          previewLoading={view.previewLoading}
          rightCollapsed={view.rightCollapsed}
          rightPanel={view.rightPanelRef.current}
        />
        <PreviewPaneBody
          diagnosticsSelection={diagnosticsSelection}
          folderSelected={folderSelected}
          view={view}
        />
      </div>
    </ResizablePanel>
  );
}
