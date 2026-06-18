import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '../../components/ui/resizable';
import { DiagnosticsTimelineView } from '../../diagnostics';
import { MarkdownDocumentView } from '../MarkdownDocumentView';
import { PdfDocumentPreview } from '../PdfDocumentPreview';
import { PdfPreviewToolbar } from '../PdfPreviewToolbar';
import { documentPreviewExtension } from '../previewSupport';
import styles from './DocumentsPage.module.css';
import { FolderContentView } from './FolderContentView';
import type { DocumentsPageView } from './types';

type DiagnosticsSelection = Extract<
  DocumentsPageView['explorerSelection'],
  { kind: 'diagnostics' }
>;

export function PreviewPaneBody({
  view,
  folderSelected,
  diagnosticsSelection,
}: {
  view: DocumentsPageView;
  folderSelected: boolean;
  diagnosticsSelection: DiagnosticsSelection | null;
}) {
  if (folderSelected) {
    return <FolderContentView view={view} />;
  }
  if (diagnosticsSelection) {
    return (
      <DiagnosticsTimelineView
        fileHash={diagnosticsSelection.fileHash}
        pageNo={diagnosticsSelection.pageNo ?? null}
        selectedSpanId={view.diagnosticSpanId}
        onSpanSelect={view.onDiagnosticSpanSelect}
      />
    );
  }
  return <StandardPreviewPaneBody view={view} />;
}

function StandardPreviewPaneBody({ view }: { view: DocumentsPageView }) {
  return (
    <>
      <PdfPreviewToolbar
        annotationEngines={view.annotationEngines}
        currentPage={view.activePageNo}
        engineVisibility={view.engineVisibility}
        markdownEngine={view.markdownEngine}
        markdownEngines={view.markdownEngines}
        numPages={Math.max(view.numPages, view.regions?.document.pages?.length ?? 0)}
        onEngineVisibilityChange={view.onEngineVisibilityChange}
        onMarkdownEngineChange={view.onMarkdownEngineChange}
        onOverlayModeChange={view.onOverlayModeChange}
        onPageChange={view.onPageSelect}
        onPreviewRotationChange={view.onPreviewRotationChange}
        onPreviewTransformReset={view.onPreviewTransformReset}
        onPreviewZoomChange={view.onPreviewZoomChange}
        onViewModeChange={view.onViewModeChange}
        overlayMode={view.overlayMode}
        previewRotation={view.previewRotation}
        previewZoom={view.previewZoom}
        viewMode={view.viewMode}
      />
      <PreviewContent view={view} />
    </>
  );
}

function PreviewContent({ view }: { view: DocumentsPageView }) {
  const preview = (
    <PdfDocumentPreview
      activeOverlay={view.activeOverlay}
      activePageNo={view.activePageNo}
      assetObjectUrl={view.assetObjectUrl}
      document={view.activeDocument}
      extension={documentPreviewExtension(view.activeDocument)}
      onOverlaySelect={view.onOverlaySelect}
      onPageSelect={view.onPageSelect}
      onPreviewZoomChange={view.onPreviewZoomChange}
      onRenderError={view.onPreviewRenderErrorChange}
      onRenderSuccess={view.onPreviewRenderSuccess}
      previewRotation={view.previewRotation}
      previewZoom={view.previewZoom}
      regions={view.regions}
      visibleOverlayIds={view.visibleOverlays}
    />
  );
  const markdown = (
    <MarkdownDocumentView
      activeRegionId={view.activeOverlay?.overlay_id.replace(/^region:/, '') ?? null}
      activePageNo={view.activePageNo}
      error={view.markdownError}
      highlightQuery={view.markdownHighlight}
      loading={view.markdownLoading}
      markdown={view.markdown}
      onRegionSelect={view.onMarkdownRegionSelect}
    />
  );
  if (view.viewMode === 'preview') {
    return <div className={styles.previewContent}>{preview}</div>;
  }
  if (view.viewMode === 'markdown') {
    return <div className={styles.previewContent}>{markdown}</div>;
  }
  return (
    <ResizablePanelGroup className={styles.previewSplit} direction="horizontal">
      <ResizablePanel className={styles.previewSplitPane} defaultSize={58} minSize={30}>
        {preview}
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel className={styles.previewSplitPane} defaultSize={42} minSize={24}>
        {markdown}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
