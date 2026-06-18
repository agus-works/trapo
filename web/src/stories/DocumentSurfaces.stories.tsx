import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { DocumentTopBar } from '../documents/DocumentTopBar';
import { OverlayDetailsPane } from '../documents/OverlayDetailsPane';
import { PdfPreviewToolbar } from '../documents/PdfPreviewToolbar';
import type { DocumentViewMode, OverlayMode, PreviewRotation } from '../documents/types';
import { markdownEngines, mockOverlay } from './fixtures/anonymizedData';
import { StoryFrame } from './StoryFrame';

const meta = {
  title: 'Features/Documents',
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const HeaderAndToolbar: Story = {
  render: () => <DocumentControlsShowcase />,
};

export const OverlayInspector: Story = {
  render: () => (
    <StoryFrame
      description="Region details pane using one synthetic overlay record."
      title="Overlay details"
      width="narrow"
    >
      <section className="storybookSurface storybookViewportMedium">
        <OverlayDetailsPane selectedOverlay={mockOverlay} />
      </section>
    </StoryFrame>
  ),
};

function DocumentControlsShowcase() {
  const [page, setPage] = useState(2);
  const [zoom, setZoom] = useState(1.25);
  const [rotation, setRotation] = useState<PreviewRotation>(0);
  const [viewMode, setViewMode] = useState<DocumentViewMode>('split');
  const [overlayMode, setOverlayMode] = useState<OverlayMode>('all');
  const [markdownEngine, setMarkdownEngine] = useState('best_available_markdown');
  const [engineVisibility, setEngineVisibility] = useState<Record<string, boolean>>({
    docling: true,
    fusion: true,
    mineru: true,
  });

  return (
    <StoryFrame
      description="Document header and preview toolbar with anonymized document labels."
      title="Document controls"
    >
      <section className="storybookSurface">
        <DocumentTopBar
          activeDocumentPath="C:\\Sample\\Corpus\\sample-research-brief.pdf"
          error={null}
          filename="sample-research-brief.pdf"
          leftCollapsed={false}
          leftPanel={null}
          loading={false}
          previewError={null}
          previewLoading={false}
          rightCollapsed={false}
          rightPanel={null}
        />
        <PdfPreviewToolbar
          annotationEngines={['fusion', 'docling', 'mineru']}
          currentPage={page}
          engineVisibility={engineVisibility}
          markdownEngine={markdownEngine}
          markdownEngines={markdownEngines}
          numPages={12}
          onEngineVisibilityChange={(engine, visible) =>
            setEngineVisibility((current) => ({ ...current, [engine]: visible }))
          }
          onMarkdownEngineChange={setMarkdownEngine}
          onOverlayModeChange={setOverlayMode}
          onPageChange={setPage}
          onPreviewRotationChange={setRotation}
          onPreviewTransformReset={() => {
            setZoom(1);
            setRotation(0);
          }}
          onPreviewZoomChange={setZoom}
          onViewModeChange={setViewMode}
          overlayMode={overlayMode}
          previewRotation={rotation}
          previewZoom={zoom}
          viewMode={viewMode}
        />
      </section>
    </StoryFrame>
  );
}
