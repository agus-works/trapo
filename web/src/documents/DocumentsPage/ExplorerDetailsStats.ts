import type { DocumentRegionsPayload, DocumentSummary } from '../../generated/model';
import { commonDirectoryRootParts, directoryPartsForDocument } from '../documentPaths';
import type { ExplorerSelection } from '../types';

export interface AggregateStats {
  files: number;
  folders: number;
  sizeBytes: number;
  chunks: number;
  regions: number;
  ocrReady: number;
  extensions: string;
}

export function aggregateStats(
  allDocuments: DocumentSummary[],
  scopeDocuments: DocumentSummary[],
  selection: ExplorerSelection,
): AggregateStats {
  return {
    chunks: sum(scopeDocuments, (document) => document.chunk_count ?? 0),
    extensions: extensionSummary(scopeDocuments),
    files: scopeDocuments.length,
    folders: folderCount(allDocuments, selection),
    ocrReady: scopeDocuments.filter(
      (document) => document.docling_status === 'ok' || document.mineru_status === 'ok',
    ).length,
    regions: sum(scopeDocuments, (document) => document.region_count ?? 0),
    sizeBytes: sum(scopeDocuments, (document) => document.size_bytes),
  };
}

export function documentsForDirectory(
  documents: DocumentSummary[],
  pathKey: string,
): DocumentSummary[] {
  const rootParts = commonDirectoryRootParts(documents);
  const targetParts = pathKey.split('/').filter(Boolean);
  return documents.filter((document) => {
    const parts = directoryPartsForDocument(document, rootParts);
    return targetParts.every((part, index) => parts[index] === part);
  });
}

export function regionsForFile(regions: DocumentRegionsPayload | null, fileHash: string) {
  return regions?.document.file_hash === fileHash ? regions : null;
}

function folderCount(documents: DocumentSummary[], selection: ExplorerSelection): number {
  const rootParts = commonDirectoryRootParts(documents);
  const prefix = selection.kind === 'directory' ? selection.pathKey : '';
  const folders = new Set<string>();
  for (const document of documents) {
    const parts = directoryPartsForDocument(document, rootParts);
    for (let index = 0; index < parts.length; index += 1) {
      const pathKey = parts.slice(0, index + 1).join('/');
      if (prefix && pathKey !== prefix && !pathKey.startsWith(`${prefix}/`)) {
        continue;
      }
      if (pathKey !== prefix) {
        folders.add(pathKey);
      }
    }
  }
  return folders.size;
}

function extensionSummary(documents: DocumentSummary[]): string {
  if (documents.length === 0) {
    return 'none';
  }
  const counts = new Map<string, number>();
  for (const document of documents) {
    const extension = document.extension?.trim().toLowerCase() || '(none)';
    counts.set(extension, (counts.get(extension) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, 4)
    .map(([extension, count]) => `${extension} ${count}`)
    .join(', ');
}

function sum(documents: DocumentSummary[], value: (document: DocumentSummary) => number): number {
  return documents.reduce((total, document) => total + value(document), 0);
}
