import { useSearch } from '@tanstack/react-router';
import { useEffect, useMemo, useState } from 'react';
import type { DocumentSummary, MarkdownEngineRecord, OverlayBox } from '../../generated/model';
import { errorText } from '../../lib/utils';
import {
  useDocumentAssetQuery,
  useDocumentMarkdownPrefetch,
  useDocumentMarkdownQuery,
  useDocumentRegionsQuery,
  useDocumentsQuery,
  useUpdateAnnotationVisibilityMutation,
} from '../../queries/hooks';
import type { DocumentRouteSearch } from '../../routeSearch';
import type { AnnotationEngineVisibility } from '../annotationVisibility';
import {
  annotationEnginesForRegions,
  readAnnotationEngineVisibility,
} from '../annotationVisibility';
import {
  buildDocumentTree,
  overlayIdsForMode,
  overlayPageGroups,
  scrollTreeToOverlay,
} from '../documentTree';
import { scrollToMarkdownRegion } from '../MarkdownDocumentView';
import type { ExplorerSelection, PreviewRotation } from '../types';
import { selectedTreeNodeId, useRouteSelectionSync } from './explorerSelection';
import type { DocumentsPageView } from './types';
import {
  useDocumentsPageActions,
  useEngineVisibilitySync,
  usePanelState,
  usePreviewAssetState,
} from './useDocumentsPageUiState';
import { useExpandedDocumentTree } from './useExpandedDocumentTree';

// Stable empty reference so effects that depend on `documents` do not re-run on
// every render while the documents query is still pending. A fresh `[]` here
// would change the dependency identity each render and, when `activeHash` is
// seeded from a deep-link `?file=` param before documents load, drive the
// tree-expand effect into an infinite update loop.
const EMPTY_DOCUMENTS: DocumentSummary[] = [];
const DEFAULT_MARKDOWN_ENGINES: MarkdownEngineRecord[] = [
  {
    is_virtual: true,
    label: 'Best available',
    markdown_engine: 'best_available_markdown',
    page_count: 0,
  },
  {
    label: 'LM Studio',
    markdown_engine: 'lmstudio_markdown',
    page_count: 0,
  },
  {
    label: 'Infinity Parser2',
    markdown_engine: 'infinity_markdown',
    page_count: 0,
  },
  {
    label: 'MarkItDown',
    markdown_engine: 'markitdown',
    page_count: 0,
  },
  {
    label: 'MarkItDown CU',
    markdown_engine: 'markitdown_cu',
    page_count: 0,
  },
];

type RouteViewState = Pick<
  DocumentsPageView,
  | 'explorerSortBy'
  | 'explorerSortDir'
  | 'explorerTileSize'
  | 'explorerViewMode'
  | 'markdownEngine'
  | 'overlayMode'
  | 'previewRotation'
  | 'previewZoom'
  | 'viewMode'
>;

export function useDocumentsPageState(): DocumentsPageView {
  const search = useSearch({ from: '/' }) as DocumentRouteSearch;
  const documentsQuery = useDocumentsQuery();
  const documents = documentsQuery.data ?? EMPTY_DOCUMENTS;
  const requestedHash = search.file ?? null;
  const activeHash = requestedHash ?? null;
  const activeDocument = documents.find((item) => item.file_hash === activeHash) ?? null;
  const regionsQuery = useDocumentRegionsQuery(activeHash);
  const assetQuery = useDocumentAssetQuery(activeHash, false);
  const regions = regionsQuery.data ?? null;
  const annotationEngines = useMemo(() => annotationEnginesForRegions(regions), [regions]);
  const previewState = usePreviewAssetState(assetQuery.data);
  const panelState = usePanelState();
  const [explorerSelection, setExplorerSelection] = useState<ExplorerSelection>({ kind: 'root' });
  const [engineVisibility, setEngineVisibility] = useState(() => readAnnotationEngineVisibility());
  const visibilityMutation = useUpdateAnnotationVisibilityMutation(activeHash);
  const routeView = routeViewState(search);
  const pageGroups = useMemo(() => overlayPageGroups(regions), [regions]);
  const activeOverlay =
    regions?.overlays.find((item) => item.overlay_id === search.overlay) ?? null;
  const activePageNo =
    activeOverlay?.page_no ?? search.page ?? regions?.document.pages?.[0]?.page_no ?? 1;
  const markdownQuery = useDocumentMarkdownQuery(
    activeHash,
    activePageNo,
    routeView.markdownEngine,
  );
  const markdown = markdownQuery.data ?? null;
  const treeState = useExpandedDocumentTree(
    activeHash,
    activeDocument,
    documents,
    explorerSelection,
  );
  const actions = useDocumentsPageActions({
    activeHash,
    setEngineVisibility,
    setExplorerSelection,
    visibilityMutation,
  });

  useSelectedDocumentSync(documents, requestedHash, actions.onMissingDocument);
  useEngineVisibilitySync(regions, engineVisibility, setEngineVisibility);
  useRouteSelectionSync(
    activeHash,
    activeOverlay,
    requestedHash,
    search.folder,
    search.diagnostics,
    search.page,
    setExplorerSelection,
  );
  useSelectedRegionScroll(activeOverlay);
  useDocumentMarkdownPrefetch(
    activeHash,
    activePageNo,
    regions?.document.pages ?? [],
    routeView.markdownEngine,
  );

  const selectedNodeId = selectedTreeNodeId(explorerSelection);

  const documentTree = useDocumentTree({
    activeHash,
    actions,
    documents,
    engineVisibility,
    pageGroups,
    selectedNodeId,
  });

  return {
    activeDocument,
    activeHash,
    activeOverlay,
    activePageNo,
    annotationEngines,
    diagnosticSpanId: search.diagnosticSpan ?? null,
    documentTree,
    documents,
    explorerSelection,
    expandedTreeNodeIds: treeState.expandedTreeNodeIds,
    engineVisibility,
    loading: documentsQuery.isLoading || regionsQuery.isFetching,
    loadError: errorMessage(documentsQuery.error ?? regionsQuery.error),
    markdown,
    markdownEngines: markdown?.available_engines ?? DEFAULT_MARKDOWN_ENGINES,
    markdownError: errorMessage(markdownQuery.error),
    markdownHighlight: search.highlight ?? null,
    markdownLoading: markdownQuery.isFetching,
    previewError: previewState.previewRenderError ?? errorMessage(assetQuery.error),
    previewLoading: assetQuery.isFetching,
    regions,
    selectedOverlay: activeOverlay,
    visibleOverlays: overlayIdsForMode(
      regions,
      routeView.overlayMode,
      activeOverlay,
      engineVisibility,
    ),
    ...panelState,
    ...previewState,
    ...routeView,
    onDiagnosticSpanSelect: actions.onDiagnosticSpanSelect,
    onDocumentDiagnosticsSelect: actions.onDocumentDiagnosticsSelect,
    onEngineVisibilityChange: actions.onEngineVisibilityChange,
    onDocumentSelect: actions.onDocumentSelect,
    onExplorerSortChange: actions.onExplorerSortChange,
    onExplorerTileSizeChange: actions.onExplorerTileSizeChange,
    onExplorerViewModeChange: actions.onExplorerViewModeChange,
    onMarkdownEngineChange: actions.onMarkdownEngineChange,
    onMarkdownRegionSelect: actions.onMarkdownRegionSelect,
    onOverlayModeChange: actions.onOverlayModeChange,
    onOverlaySelect: actions.onOverlaySelect,
    onOverlayVisibilityChange: actions.onOverlayVisibilityChange,
    onPageDiagnosticsSelect: actions.onPageDiagnosticsSelect,
    onPageSelect: actions.onPageSelect,
    onPreviewRotationChange: actions.onPreviewRotationChange,
    onPreviewTransformReset: actions.onPreviewTransformReset,
    onPreviewZoomChange: actions.onPreviewZoomChange,
    onTreeToggle: treeState.onTreeToggle,
    onViewModeChange: actions.onViewModeChange,
  };
}

type DocumentPageActions = ReturnType<typeof useDocumentsPageActions>;
type DocumentPageGroups = ReturnType<typeof overlayPageGroups>;

function useDocumentTree({
  activeHash,
  actions,
  documents,
  engineVisibility,
  pageGroups,
  selectedNodeId,
}: {
  activeHash: string | null;
  actions: DocumentPageActions;
  documents: DocumentSummary[];
  engineVisibility: AnnotationEngineVisibility;
  pageGroups: DocumentPageGroups;
  selectedNodeId: string | null;
}) {
  return useMemo(
    () =>
      buildDocumentTree({
        activeHash,
        documents,
        engineVisibility,
        onDirectorySelect: actions.onDirectorySelect,
        onDocumentDiagnosticsSelect: actions.onDocumentDiagnosticsSelect,
        onDocumentSelect: actions.onDocumentSelect,
        onEngineVisibilityChange: actions.onEngineVisibilityChange,
        onOverlaySelect: actions.onOverlaySelect,
        onOverlayVisibilityChange: actions.onOverlayVisibilityChange,
        onPageDiagnosticsSelect: actions.onPageDiagnosticsSelect,
        onPageSelect: actions.onPageSelect,
        onRootSelect: actions.onRootSelect,
        pageGroups,
        selectedNodeId: selectedNodeId ?? '',
      }),
    [activeHash, actions, documents, engineVisibility, pageGroups, selectedNodeId],
  );
}

function routeViewState(search: DocumentRouteSearch): RouteViewState {
  return {
    explorerSortBy: search.sortBy ?? 'name',
    explorerSortDir: search.sortDir ?? 'asc',
    explorerTileSize: search.tileSize ?? 'medium',
    explorerViewMode: search.explorerView ?? 'tiles',
    markdownEngine: search.markdown ?? 'best_available_markdown',
    overlayMode: search.overlays ?? 'all',
    previewRotation: (search.rotation ?? 0) as PreviewRotation,
    previewZoom: search.zoom ?? 1,
    viewMode: search.view ?? 'split',
  };
}

function useSelectedDocumentSync(
  documents: DocumentSummary[],
  requestedHash: string | null,
  onMissingDocument: () => void,
) {
  useEffect(() => {
    if (documents.length === 0) {
      return;
    }
    if (requestedHash && !documents.some((item) => item.file_hash === requestedHash)) {
      onMissingDocument();
    }
  }, [documents, onMissingDocument, requestedHash]);
}

function useSelectedRegionScroll(activeOverlay: OverlayBox | null) {
  useEffect(() => {
    if (activeOverlay) {
      scrollToMarkdownRegion(activeOverlay.overlay_id.replace(/^region:/, ''));
      scrollTreeToOverlay(activeOverlay.overlay_id);
    }
  }, [activeOverlay]);
}

function errorMessage(cause: unknown): string | null {
  return cause ? errorText(cause) : null;
}
