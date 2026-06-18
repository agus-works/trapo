import { useNavigate } from '@tanstack/react-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ImperativePanelHandle } from '../../components/ui/resizable';
import type {
  AnnotationVisibilityUpdate,
  DocumentRegionsPayload,
  OverlayBox,
} from '../../generated/model';
import type { DocumentRouteSearch } from '../../routeSearch';
import {
  normalizeEngineVisibility,
  writeAnnotationEngineVisibility,
} from '../annotationVisibility';
import type {
  DocumentViewMode,
  ExplorerSelection,
  ExplorerSortBy,
  ExplorerTileSize,
  ExplorerViewMode,
  OverlayMode,
  SortDirection,
} from '../types';
import { clearSearchFocus, useDocumentSelectionActions } from './useDocumentSelectionActions';
import { usePreviewTransformActions } from './usePreviewTransformActions';

interface DocumentsPageActionsArgs {
  activeHash: string | null;
  setEngineVisibility: (
    update: (current: Record<string, boolean>) => Record<string, boolean>,
  ) => void;
  setExplorerSelection: (selection: ExplorerSelection) => void;
  visibilityMutation: {
    mutate: (payload: AnnotationVisibilityUpdate) => void;
  };
}

export function useDocumentsPageActions({
  activeHash,
  setEngineVisibility,
  setExplorerSelection,
  visibilityMutation,
}: DocumentsPageActionsArgs) {
  const navigate = useNavigate({ from: '/' });
  const previewTransformActions = usePreviewTransformActions();
  const routePreferenceActions = useRoutePreferenceActions();
  const navigateToPage = useCallback(
    (pageNo: number, replace?: boolean) => {
      void navigate({
        replace,
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: undefined,
            overlay: undefined,
            page: pageNo,
          }),
      });
    },
    [navigate],
  );
  const selectionActions = useDocumentSelectionActions({
    activeHash,
    navigateToPage,
    setExplorerSelection,
  });
  const onEngineVisibilityChange = useCallback(
    (engine: string, visible: boolean) => {
      setEngineVisibility((current) => {
        const next = { ...current, [engine]: visible };
        writeAnnotationEngineVisibility(next);
        return next;
      });
    },
    [setEngineVisibility],
  );
  const onOverlayVisibilityChange = useCallback(
    (overlay: OverlayBox, visible: boolean) => {
      if (!activeHash) {
        return;
      }
      visibilityMutation.mutate({
        overrides: [{ hidden: !visible, overlay_id: overlay.overlay_id }],
      });
    },
    [activeHash, visibilityMutation],
  );

  return {
    onEngineVisibilityChange,
    onOverlayVisibilityChange,
    ...selectionActions,
    ...previewTransformActions,
    ...routePreferenceActions,
  };
}

function useRoutePreferenceActions() {
  const navigate = useNavigate({ from: '/' });
  const onOverlayModeChange = useCallback(
    (mode: OverlayMode) => void navigate({ search: (current) => ({ ...current, overlays: mode }) }),
    [navigate],
  );
  const onViewModeChange = useCallback(
    (mode: DocumentViewMode) =>
      void navigate({ search: (current) => ({ ...current, view: mode }) }),
    [navigate],
  );
  const onMarkdownEngineChange = useCallback(
    (engine: string) =>
      void navigate({
        search: (current) => ({ ...current, markdown: engine as DocumentRouteSearch['markdown'] }),
      }),
    [navigate],
  );
  const onExplorerViewModeChange = useCallback(
    (mode: ExplorerViewMode) =>
      void navigate({ search: (current) => ({ ...current, explorerView: mode }) }),
    [navigate],
  );
  const onExplorerTileSizeChange = useCallback(
    (size: ExplorerTileSize) =>
      void navigate({ search: (current) => ({ ...current, tileSize: size }) }),
    [navigate],
  );
  const onExplorerSortChange = useCallback(
    (sortBy: ExplorerSortBy, sortDir: SortDirection) =>
      void navigate({ search: (current) => ({ ...current, sortBy, sortDir }) }),
    [navigate],
  );
  const onDiagnosticSpanSelect = useCallback(
    (spanId: string) =>
      void navigate({ search: (current) => ({ ...current, diagnosticSpan: spanId }) }),
    [navigate],
  );
  return {
    onDiagnosticSpanSelect,
    onExplorerSortChange,
    onExplorerTileSizeChange,
    onExplorerViewModeChange,
    onMarkdownEngineChange,
    onOverlayModeChange,
    onViewModeChange,
  };
}

export function usePreviewAssetState(_assetData: Blob | null | undefined) {
  const [numPages, setNumPages] = useState<number>(0);
  const [previewRenderError, setPreviewRenderError] = useState<string | null>(null);

  return {
    numPages,
    assetObjectUrl: null,
    previewRenderError,
    onPreviewRenderErrorChange: setPreviewRenderError,
    onPreviewRenderSuccess: setNumPages,
  };
}

export function usePanelState() {
  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  return {
    leftCollapsed,
    leftPanelRef,
    rightCollapsed,
    rightPanelRef,
    onLeftCollapsedChange: setLeftCollapsed,
    onRightCollapsedChange: setRightCollapsed,
  };
}

export function useEngineVisibilitySync(
  regions: DocumentRegionsPayload | null,
  engineVisibility: Record<string, boolean>,
  setEngineVisibility: (value: Record<string, boolean>) => void,
) {
  useEffect(() => {
    const normalized = normalizeEngineVisibility(regions, engineVisibility);
    if (JSON.stringify(normalized) === JSON.stringify(engineVisibility)) {
      return;
    }
    setEngineVisibility(normalized);
    writeAnnotationEngineVisibility(normalized);
  }, [engineVisibility, regions, setEngineVisibility]);
}
