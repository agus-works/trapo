import { ResizableHandle, ResizablePanelGroup } from '../../components/ui/resizable';
import { DetailsPane } from './DetailsPane';
import { DocumentStatusBar } from './DocumentStatusBar';
import styles from './DocumentsPage.module.css';
import { ExplorerPane } from './ExplorerPane';
import { PreviewPane } from './PreviewPane';
import type { DocumentsPageView } from './types';

export function DocumentsPageLayout({ view }: { view: DocumentsPageView }) {
  return (
    <div className={styles.workbench}>
      <ResizablePanelGroup direction="horizontal">
        <ExplorerPane view={view} />
        <ResizableHandle />
        <PreviewPane view={view} />
        <ResizableHandle />
        <DetailsPane view={view} />
      </ResizablePanelGroup>
      <DocumentStatusBar view={view} />
    </div>
  );
}
