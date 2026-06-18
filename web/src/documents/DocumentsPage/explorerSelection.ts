import { useEffect } from 'react';
import type { OverlayBox } from '../../generated/model';
import {
  diagnosticsTreeNodeId,
  directoryTreeNodeId,
  documentTreeNodeId,
  overlayTreeNodeId,
  pageTreeNodeId,
} from '../documentTree';
import type { ExplorerSelection } from '../types';

export function selectedTreeNodeId(selection: ExplorerSelection): string {
  switch (selection.kind) {
    case 'directory':
      return directoryTreeNodeId(selection.pathKey);
    case 'document':
      return documentTreeNodeId(selection.fileHash);
    case 'diagnostics':
      return diagnosticsTreeNodeId(selection.fileHash, selection.pageNo);
    case 'page':
      return pageTreeNodeId(selection.fileHash, selection.pageNo);
    case 'overlay':
      return overlayTreeNodeId(selection.overlay.overlay_id);
    case 'root':
      return 'directory:/';
  }
}

export function useRouteSelectionSync(
  activeHash: string | null,
  activeOverlay: OverlayBox | null,
  requestedHash: string | null,
  requestedFolder: string | undefined,
  requestedDiagnostics: 'file' | 'page' | undefined,
  requestedPage: number | undefined,
  setExplorerSelection: (selection: ExplorerSelection) => void,
) {
  useEffect(() => {
    if (activeOverlay) {
      setExplorerSelection({ kind: 'overlay', overlay: activeOverlay });
      return;
    }
    if (requestedDiagnostics === 'page' && requestedPage && activeHash) {
      setExplorerSelection({ kind: 'diagnostics', fileHash: activeHash, pageNo: requestedPage });
      return;
    }
    if (requestedDiagnostics === 'file' && activeHash) {
      setExplorerSelection({ kind: 'diagnostics', fileHash: activeHash });
      return;
    }
    if (requestedPage && activeHash) {
      setExplorerSelection({ kind: 'page', fileHash: activeHash, pageNo: requestedPage });
      return;
    }
    if (requestedHash && activeHash) {
      setExplorerSelection({ kind: 'document', fileHash: activeHash });
      return;
    }
    if (requestedFolder) {
      const parts = requestedFolder.split('/').filter(Boolean);
      setExplorerSelection({
        kind: 'directory',
        label: parts.at(-1) ?? 'Documents',
        pathKey: requestedFolder,
      });
      return;
    }
    setExplorerSelection({ kind: 'root' });
  }, [
    activeHash,
    activeOverlay,
    requestedDiagnostics,
    requestedFolder,
    requestedHash,
    requestedPage,
    setExplorerSelection,
  ]);
}
