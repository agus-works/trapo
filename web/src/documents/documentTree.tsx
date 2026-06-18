import { Activity, File, FileImage, FileScan, FileText, Folder, FolderRoot } from 'lucide-react';
import type { TreeGridNode } from '../components/workbench';
import type { DocumentRegionsPayload, DocumentSummary, OverlayBox } from '../generated/model';
import { annotationGroupNode, overlayEngine } from './annotationTree';
import type { AnnotationEngineVisibility } from './annotationVisibility';
import { overlayIsVisible } from './annotationVisibility';
import { commonDirectoryRootParts, directoryPartsForDocument } from './documentPaths';
import type { OverlayMode, OverlayPageGroup } from './types';

interface BuildDocumentTreeArgs {
  documents: DocumentSummary[];
  activeHash: string | null;
  pageGroups: OverlayPageGroup[];
  selectedNodeId: string;
  onRootSelect: () => void;
  onDirectorySelect: (pathKey: string, label: string) => void;
  onDocumentSelect: (fileHash: string) => void;
  onDocumentDiagnosticsSelect: (fileHash: string) => void;
  onPageSelect: (pageNo: number) => void;
  onPageDiagnosticsSelect: (pageNo: number) => void;
  onOverlaySelect: (overlay: OverlayBox) => void;
  onOverlayVisibilityChange: (overlay: OverlayBox, visible: boolean) => void;
  onEngineVisibilityChange: (engine: string, visible: boolean) => void;
  engineVisibility: AnnotationEngineVisibility;
}

interface DirectoryTreeBuilderNode {
  id: string;
  label: string;
  pathKey: string;
  children: Map<string, DirectoryTreeBuilderNode>;
  documents: DocumentSummary[];
}

type TreeGridArgs = Omit<BuildDocumentTreeArgs, 'documents'>;

export function buildDocumentTree(args: BuildDocumentTreeArgs): TreeGridNode[] {
  const rootParts = commonDirectoryRootParts(args.documents);
  const root: DirectoryTreeBuilderNode = {
    children: new Map(),
    documents: [],
    id: 'directory:/',
    label: 'Documents',
    pathKey: '',
  };

  for (const document of args.documents) {
    addDocumentToTree(root, document, rootParts);
  }

  return [directoryNodeToTreeGrid(root, args, true)];
}

export function overlayIdsForMode(
  regions: DocumentRegionsPayload | null,
  mode: OverlayMode,
  activeOverlay: OverlayBox | null,
  engineVisibility: AnnotationEngineVisibility,
): Set<string> {
  if (!regions || mode === 'hidden') {
    return new Set();
  }
  if (mode === 'selected') {
    return new Set(
      activeOverlay && overlayIsVisible(activeOverlay, engineVisibility)
        ? [activeOverlay.overlay_id]
        : [],
    );
  }
  return new Set(
    regions.overlays
      .filter((overlay) => overlayIsVisible(overlay, engineVisibility))
      .map((overlay) => overlay.overlay_id),
  );
}

export function documentTreeNodeId(fileHash: string): string {
  return `document:${fileHash}`;
}

export function pageTreeNodeId(fileHash: string, pageNo: number): string {
  return `document:${fileHash}:page:${pageNo}`;
}

export function diagnosticsTreeNodeId(fileHash: string, pageNo?: number): string {
  return pageNo === undefined
    ? `document:${fileHash}:diagnostics`
    : `document:${fileHash}:page:${pageNo}:diagnostics`;
}

export function directoryTreeNodeIdsForDocument(
  document: DocumentSummary,
  rootParts: readonly string[],
): string[] {
  const ids: string[] = ['directory:/'];
  let pathKey = '';
  for (const part of directoryPartsForDocument(document, rootParts)) {
    pathKey = pathKey ? `${pathKey}/${part}` : part;
    ids.push(directoryTreeNodeId(pathKey));
  }
  return ids;
}

export function scrollTreeToOverlay(overlayId: string) {
  window.setTimeout(() => {
    document.getElementById(overlayTreeNodeId(overlayId))?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
    });
  }, 0);
}

function addDocumentToTree(
  root: DirectoryTreeBuilderNode,
  document: DocumentSummary,
  rootParts: readonly string[],
) {
  let current = root;
  let pathKey = '';
  for (const part of directoryPartsForDocument(document, rootParts)) {
    pathKey = pathKey ? `${pathKey}/${part}` : part;
    current = getOrCreateDirectoryNode(current, pathKey, part);
  }
  current.documents.push(document);
}

function getOrCreateDirectoryNode(
  parent: DirectoryTreeBuilderNode,
  pathKey: string,
  label: string,
): DirectoryTreeBuilderNode {
  const existing = parent.children.get(label);
  if (existing) {
    return existing;
  }

  const next: DirectoryTreeBuilderNode = {
    children: new Map(),
    documents: [],
    id: directoryTreeNodeId(pathKey),
    label,
    pathKey,
  };
  parent.children.set(label, next);
  return next;
}

function directoryNodeToTreeGrid(
  node: DirectoryTreeBuilderNode,
  args: TreeGridArgs,
  root = false,
): TreeGridNode {
  const directoryChildren = [...node.children.values()]
    .sort((left, right) => left.label.localeCompare(right.label))
    .map((child) => directoryNodeToTreeGrid(child, args));
  const documentChildren = [...node.documents]
    .sort((left, right) => left.filename.localeCompare(right.filename))
    .map((document) => documentNodeToTreeGrid(document, args));

  return {
    badge: directoryChildCount(node),
    children: [...directoryChildren, ...documentChildren],
    icon: root ? <FolderRoot size={13} /> : <Folder size={13} />,
    id: node.id,
    label: node.label,
    onSelect: root ? args.onRootSelect : () => args.onDirectorySelect(node.pathKey, node.label),
    selected: args.selectedNodeId === node.id,
  };
}

function documentNodeToTreeGrid(document: DocumentSummary, args: TreeGridArgs): TreeGridNode {
  const isActive = document.file_hash === args.activeHash;
  const nodeId = documentTreeNodeId(document.file_hash);
  return {
    badge: document.chunk_count,
    children: isActive
      ? [
          documentDiagnosticsNode(document, args),
          ...args.pageGroups.map((page) => pageNodeToTreeGrid(document, page, args)),
        ]
      : [],
    hasChildren: isActive ? args.pageGroups.length > 0 : (document.region_count ?? 0) > 0,
    icon: fileIcon(document),
    id: nodeId,
    label: document.filename,
    onExpand: () => args.onDocumentSelect(document.file_hash),
    onSelect: () => args.onDocumentSelect(document.file_hash),
    selected: args.selectedNodeId === nodeId,
  };
}

function documentDiagnosticsNode(document: DocumentSummary, args: TreeGridArgs): TreeGridNode {
  const nodeId = diagnosticsTreeNodeId(document.file_hash);
  return {
    badge: 'trace',
    icon: <Activity size={13} />,
    id: nodeId,
    label: 'Pipeline diagnostics',
    onSelect: () => args.onDocumentDiagnosticsSelect(document.file_hash),
    selected: args.selectedNodeId === nodeId,
  };
}

function pageNodeToTreeGrid(
  document: DocumentSummary,
  page: OverlayPageGroup,
  args: TreeGridArgs,
): TreeGridNode {
  return {
    badge: page.overlays.length,
    children: [
      pageDiagnosticsNode(document, page, args),
      annotationGroupNode(document, page, args),
    ],
    icon: <FileScan size={13} />,
    id: pageTreeNodeId(document.file_hash, page.pageNo),
    label: `Page ${page.pageNo}`,
    onSelect: () => args.onPageSelect(page.pageNo),
    selected: args.selectedNodeId === pageTreeNodeId(document.file_hash, page.pageNo),
  };
}

function pageDiagnosticsNode(
  document: DocumentSummary,
  page: OverlayPageGroup,
  args: TreeGridArgs,
): TreeGridNode {
  const nodeId = diagnosticsTreeNodeId(document.file_hash, page.pageNo);
  return {
    badge: 'trace',
    icon: <Activity size={13} />,
    id: nodeId,
    label: 'Page diagnostics',
    onSelect: () => args.onPageDiagnosticsSelect(page.pageNo),
    selected: args.selectedNodeId === nodeId,
  };
}

export function overlayPageGroups(regions: DocumentRegionsPayload | null): OverlayPageGroup[] {
  if (!regions) {
    return [];
  }

  const groups = new Map<number, OverlayBox[]>();
  for (const page of regions.document.pages ?? []) {
    groups.set(page.page_no, []);
  }
  for (const overlay of regions.overlays) {
    const pageOverlays = groups.get(overlay.page_no) ?? [];
    pageOverlays.push(overlay);
    groups.set(overlay.page_no, pageOverlays);
  }

  return [...groups.entries()]
    .sort(([left], [right]) => left - right)
    .map(([pageNo, overlays]) => ({
      overlays: [...overlays].sort(compareOverlaysForTree),
      pageNo,
    }));
}

function directoryChildCount(node: DirectoryTreeBuilderNode): number {
  let count = node.documents.length;
  for (const child of node.children.values()) {
    count += directoryChildCount(child);
  }
  return count;
}

function compareOverlaysForTree(left: OverlayBox, right: OverlayBox): number {
  return (
    overlayEngine(left).localeCompare(overlayEngine(right)) ||
    left.bbox.top_pct - right.bbox.top_pct ||
    left.bbox.left_pct - right.bbox.left_pct ||
    left.chunk_index - right.chunk_index ||
    left.overlay_id.localeCompare(right.overlay_id)
  );
}

export function directoryTreeNodeId(pathKey: string): string {
  return `directory:${pathKey}`;
}

export function overlayTreeNodeId(overlayId: string): string {
  return `overlay-tree:${overlayId}`;
}

function fileIcon(document: DocumentSummary) {
  const extension = document.extension?.trim().toLowerCase().replace(/^\./, '') ?? '';
  if (['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff', 'gif'].includes(extension)) {
    return <FileImage size={13} />;
  }
  if (extension === 'pdf') {
    return <FileText size={13} />;
  }
  return <File size={13} />;
}
