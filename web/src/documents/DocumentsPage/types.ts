import type { RefObject } from 'react';
import type { ImperativePanelHandle } from '../../components/ui/resizable';
import type { TreeGridNode } from '../../components/workbench';
import type {
  DocumentMarkdownPayload,
  DocumentRegionsPayload,
  DocumentSummary,
  MarkdownEngineRecord,
  OverlayBox,
} from '../../generated/model';
import type { AnnotationEngineVisibility } from '../annotationVisibility';
import type {
  DocumentViewMode,
  ExplorerSelection,
  ExplorerSortBy,
  ExplorerTileSize,
  ExplorerViewMode,
  OverlayMode,
  PageSelectOptions,
  PreviewRotation,
  SortDirection,
} from '../types';

export interface DocumentsPageView {
  activeDocument: DocumentSummary | null;
  activeHash: string | null;
  activeOverlay: OverlayBox | null;
  activePageNo: number;
  annotationEngines: string[];
  diagnosticSpanId: string | null;
  documentTree: TreeGridNode[];
  documents: DocumentSummary[];
  engineVisibility: AnnotationEngineVisibility;
  explorerSortBy: ExplorerSortBy;
  explorerSortDir: SortDirection;
  explorerSelection: ExplorerSelection;
  explorerTileSize: ExplorerTileSize;
  explorerViewMode: ExplorerViewMode;
  expandedTreeNodeIds: Set<string>;
  leftCollapsed: boolean;
  leftPanelRef: RefObject<ImperativePanelHandle | null>;
  loading: boolean;
  loadError: string | null;
  markdownHighlight: string | null;
  markdownEngine: string;
  markdownEngines: MarkdownEngineRecord[];
  numPages: number;
  overlayMode: OverlayMode;
  viewMode: DocumentViewMode;
  previewError: string | null;
  previewLoading: boolean;
  previewRotation: PreviewRotation;
  previewZoom: number;
  assetObjectUrl: string | null;
  markdown: DocumentMarkdownPayload | null;
  markdownError: string | null;
  markdownLoading: boolean;
  regions: DocumentRegionsPayload | null;
  rightCollapsed: boolean;
  rightPanelRef: RefObject<ImperativePanelHandle | null>;
  selectedOverlay: OverlayBox | null;
  visibleOverlays: Set<string>;
  onDiagnosticSpanSelect: (spanId: string) => void;
  onDocumentDiagnosticsSelect: (fileHash: string) => void;
  onDocumentSelect: (fileHash: string) => void;
  onEngineVisibilityChange: (engine: string, visible: boolean) => void;
  onExplorerSortChange: (sortBy: ExplorerSortBy, sortDir: SortDirection) => void;
  onExplorerTileSizeChange: (size: ExplorerTileSize) => void;
  onExplorerViewModeChange: (mode: ExplorerViewMode) => void;
  onLeftCollapsedChange: (collapsed: boolean) => void;
  onMarkdownRegionSelect: (regionId: string) => void;
  onMarkdownEngineChange: (engine: string) => void;
  onOverlayModeChange: (mode: OverlayMode) => void;
  onOverlaySelect: (overlay: OverlayBox) => void;
  onOverlayVisibilityChange: (overlay: OverlayBox, visible: boolean) => void;
  onPageDiagnosticsSelect: (pageNo: number) => void;
  onPageSelect: (pageNo: number, options?: PageSelectOptions) => void;
  onPreviewRenderErrorChange: (error: string | null) => void;
  onPreviewRenderSuccess: (numPages: number) => void;
  onPreviewRotationChange: (rotation: PreviewRotation) => void;
  onPreviewTransformReset: () => void;
  onPreviewZoomChange: (zoom: number) => void;
  onRightCollapsedChange: (collapsed: boolean) => void;
  onTreeToggle: (nodeId: string) => void;
  onViewModeChange: (mode: DocumentViewMode) => void;
}
