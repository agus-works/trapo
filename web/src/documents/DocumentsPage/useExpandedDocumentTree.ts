import { useCallback, useEffect, useState } from 'react';
import type { DocumentSummary } from '../../generated/model';
import {
  annotationEngineTreeNodeId,
  annotationsTreeNodeId,
  overlayEngine,
} from '../annotationTree';
import { commonDirectoryRootParts } from '../documentPaths';
import {
  diagnosticsTreeNodeId,
  directoryTreeNodeIdsForDocument,
  documentTreeNodeId,
  pageTreeNodeId,
} from '../documentTree';
import type { ExplorerSelection } from '../types';

export function useExpandedDocumentTree(
  activeHash: string | null,
  activeDocument: DocumentSummary | null,
  documents: DocumentSummary[],
  explorerSelection: ExplorerSelection,
) {
  const [expandedTreeNodeIds, setExpandedTreeNodeIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!activeHash || documents.length === 0) {
      return;
    }
    setExpandedTreeNodeIds(
      defaultExpandedNodeIds(activeHash, activeDocument, documents, explorerSelection),
    );
  }, [activeDocument, activeHash, documents, explorerSelection]);

  const onTreeToggle = useCallback((nodeId: string) => {
    setExpandedTreeNodeIds((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  return { expandedTreeNodeIds, onTreeToggle };
}

function defaultExpandedNodeIds(
  activeHash: string,
  activeDocument: DocumentSummary | null,
  documents: DocumentSummary[],
  explorerSelection: ExplorerSelection,
): Set<string> {
  const next = new Set<string>();
  next.add(documentTreeNodeId(activeHash));
  if (activeDocument) {
    const rootParts = commonDirectoryRootParts(documents);
    for (const nodeId of directoryTreeNodeIdsForDocument(activeDocument, rootParts)) {
      next.add(nodeId);
    }
  }
  addSelectionExpandedNodeIds(next, activeHash, explorerSelection);
  return next;
}

function addSelectionExpandedNodeIds(
  nodeIds: Set<string>,
  activeHash: string,
  selection: ExplorerSelection,
) {
  if (selection.kind === 'page' && selection.fileHash === activeHash) {
    addPageAnnotationNodes(nodeIds, activeHash, selection.pageNo);
    return;
  }
  if (selection.kind === 'diagnostics' && selection.fileHash === activeHash) {
    nodeIds.add(diagnosticsTreeNodeId(activeHash, selection.pageNo));
    if (selection.pageNo) {
      nodeIds.add(pageTreeNodeId(activeHash, selection.pageNo));
    }
    return;
  }
  if (selection.kind === 'overlay' && selection.overlay.file_hash === activeHash) {
    addPageAnnotationNodes(nodeIds, activeHash, selection.overlay.page_no);
    nodeIds.add(
      annotationEngineTreeNodeId(
        activeHash,
        selection.overlay.page_no,
        overlayEngine(selection.overlay),
      ),
    );
  }
}

function addPageAnnotationNodes(nodeIds: Set<string>, activeHash: string, pageNo: number) {
  nodeIds.add(pageTreeNodeId(activeHash, pageNo));
  nodeIds.add(annotationsTreeNodeId(activeHash, pageNo));
}
