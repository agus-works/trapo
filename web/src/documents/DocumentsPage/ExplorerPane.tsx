import { FileText, PanelLeft } from 'lucide-react';
import { ResizablePanel } from '../../components/ui/resizable';
import { ScrollArea } from '../../components/ui/scroll-area';
import { PaneHeader, TreeGrid } from '../../components/workbench';
import { PanelToggleButton } from '../DocumentTopBar';
import styles from './DocumentsPage.module.css';
import type { DocumentsPageView } from './types';

export function ExplorerPane({ view }: { view: DocumentsPageView }) {
  return (
    <ResizablePanel
      className={styles.sidePane}
      collapsedSize={0}
      collapsible
      defaultSize={24}
      maxSize={36}
      minSize={16}
      onCollapse={() => view.onLeftCollapsedChange(true)}
      onExpand={() => view.onLeftCollapsedChange(false)}
      ref={view.leftPanelRef}
    >
      <PaneHeader
        actions={
          <PanelToggleButton
            collapsed={view.leftCollapsed}
            icon={<PanelLeft size={15} />}
            label="Collapse explorer"
            panel={view.leftPanelRef.current}
          />
        }
        icon={<FileText size={14} />}
        title="Explorer"
      />
      <ScrollArea className={styles.paneScroll}>
        <TreeGrid
          expandedIds={view.expandedTreeNodeIds}
          nodes={view.documentTree}
          onToggle={view.onTreeToggle}
        />
      </ScrollArea>
    </ResizablePanel>
  );
}
