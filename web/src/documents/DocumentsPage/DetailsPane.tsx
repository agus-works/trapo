import { MousePointer2, PanelRight } from 'lucide-react';
import { ResizablePanel } from '../../components/ui/resizable';
import { ScrollArea } from '../../components/ui/scroll-area';
import { PaneHeader } from '../../components/workbench';
import { PanelToggleButton } from '../DocumentTopBar';
import styles from './DocumentsPage.module.css';
import { ExplorerDetailsPane } from './ExplorerDetailsPane';
import type { DocumentsPageView } from './types';

export function DetailsPane({ view }: { view: DocumentsPageView }) {
  return (
    <ResizablePanel
      className={styles.detailPane}
      collapsedSize={0}
      collapsible
      defaultSize={24}
      maxSize={38}
      minSize={16}
      onCollapse={() => view.onRightCollapsedChange(true)}
      onExpand={() => view.onRightCollapsedChange(false)}
      ref={view.rightPanelRef}
    >
      <PaneHeader
        actions={
          <PanelToggleButton
            collapsed={view.rightCollapsed}
            icon={<PanelRight size={15} />}
            label="Collapse details"
            panel={view.rightPanelRef.current}
          />
        }
        icon={<MousePointer2 size={14} />}
        title="Details"
      />
      <ScrollArea className={styles.paneScroll}>
        <ExplorerDetailsPane
          documents={view.documents}
          regions={view.regions}
          selection={view.explorerSelection}
        />
      </ScrollArea>
    </ResizablePanel>
  );
}
