import { useNavigate } from '@tanstack/react-router';
import { useCallback } from 'react';
import type { OverlayBox } from '../../generated/model';
import type { DocumentRouteSearch } from '../../routeSearch';
import type { ExplorerSelection, PageSelectOptions } from '../types';

interface DocumentSelectionActionsArgs {
  activeHash: string | null;
  navigateToPage: (pageNo: number, replace?: boolean) => void;
  setExplorerSelection: (selection: ExplorerSelection) => void;
}

export function useDocumentSelectionActions({
  activeHash,
  navigateToPage,
  setExplorerSelection,
}: DocumentSelectionActionsArgs) {
  const navigate = useNavigate({ from: '/' });
  const onPageSelect = usePageSelectAction(activeHash, navigateToPage, setExplorerSelection);
  const onMissingDocument = useCallback(
    () =>
      void navigate({
        replace: true,
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: undefined,
            file: undefined,
            overlay: undefined,
            page: undefined,
          }),
      }),
    [navigate],
  );
  const onRootSelect = useCallback(() => {
    setExplorerSelection({ kind: 'root' });
    void navigate({
      search: (current) =>
        clearSearchFocus(current, {
          diagnosticSpan: undefined,
          diagnostics: undefined,
          file: undefined,
          folder: undefined,
          overlay: undefined,
          page: undefined,
        }),
    });
  }, [navigate, setExplorerSelection]);
  const onDirectorySelect = useCallback(
    (pathKey: string, label: string) => {
      setExplorerSelection({ kind: 'directory', label, pathKey });
      void navigate({
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: undefined,
            file: undefined,
            folder: pathKey,
            overlay: undefined,
            page: undefined,
          }),
      });
    },
    [navigate, setExplorerSelection],
  );
  const onDocumentSelect = useCallback(
    (fileHash: string) => {
      setExplorerSelection({ kind: 'document', fileHash });
      void navigate({
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: undefined,
            file: fileHash,
            folder: undefined,
            overlay: undefined,
            page: undefined,
          }),
      });
    },
    [navigate, setExplorerSelection],
  );
  const onDocumentDiagnosticsSelect = useCallback(
    (fileHash: string) => {
      setExplorerSelection({ kind: 'diagnostics', fileHash });
      void navigate({
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: 'file',
            file: fileHash,
            folder: undefined,
            overlay: undefined,
            page: undefined,
          }),
      });
    },
    [navigate, setExplorerSelection],
  );
  const onPageDiagnosticsSelect = useCallback(
    (pageNo: number) => {
      if (!activeHash) {
        return;
      }
      setExplorerSelection({ kind: 'diagnostics', fileHash: activeHash, pageNo });
      void navigate({
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: 'page',
            file: activeHash,
            folder: undefined,
            overlay: undefined,
            page: pageNo,
          }),
      });
    },
    [activeHash, navigate, setExplorerSelection],
  );
  const onOverlaySelect = useCallback(
    (overlay: OverlayBox) => {
      setExplorerSelection({ kind: 'overlay', overlay });
      void navigate({
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: undefined,
            overlay: overlay.overlay_id,
            page: overlay.page_no,
          }),
      });
    },
    [navigate, setExplorerSelection],
  );
  const onMarkdownRegionSelect = useCallback(
    (regionId: string) => {
      const overlayId = `region:${regionId}`;
      void navigate({
        search: (current) =>
          clearSearchFocus(current, {
            diagnosticSpan: undefined,
            diagnostics: undefined,
            overlay: overlayId,
          }),
      });
    },
    [navigate],
  );

  return {
    onDirectorySelect,
    onDocumentDiagnosticsSelect,
    onDocumentSelect,
    onMarkdownRegionSelect,
    onMissingDocument,
    onOverlaySelect,
    onPageDiagnosticsSelect,
    onPageSelect,
    onRootSelect,
  };
}

export function clearSearchFocus(
  current: DocumentRouteSearch,
  update: Partial<DocumentRouteSearch>,
): DocumentRouteSearch {
  return { ...current, highlight: undefined, term: undefined, ...update };
}

function usePageSelectAction(
  activeHash: string | null,
  navigateToPage: (pageNo: number, replace?: boolean) => void,
  setExplorerSelection: (selection: ExplorerSelection) => void,
) {
  return useCallback(
    (pageNo: number, options?: PageSelectOptions) => {
      if (activeHash && options?.source !== 'scroll') {
        setExplorerSelection({ kind: 'page', fileHash: activeHash, pageNo });
      }
      navigateToPage(pageNo, options?.replace);
    },
    [activeHash, navigateToPage, setExplorerSelection],
  );
}
