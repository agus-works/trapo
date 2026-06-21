import { Archive, Code2, File, FileImage, FileSpreadsheet, FileText } from 'lucide-react';
import type { ReactNode } from 'react';
import type { DocumentSummary } from '../../generated/model';
import { commonDirectoryRootParts, directoryPartsForDocument } from '../documentPaths';
import { documentPreviewExtension } from '../previewSupport';
import type { ExplorerSelection, ExplorerSortBy, SortDirection } from '../types';

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function documentsForSelection(
  documents: DocumentSummary[],
  selection: ExplorerSelection,
): DocumentSummary[] {
  if (selection.kind !== 'directory') {
    return documents;
  }
  const rootParts = commonDirectoryRootParts(documents);
  const targetParts = selection.pathKey.split('/').filter(Boolean);
  return documents.filter((document) => {
    const parts = directoryPartsForDocument(document, rootParts);
    return targetParts.every((part, index) => parts[index] === part);
  });
}

export function sortedDocuments(
  documents: DocumentSummary[],
  sortBy: ExplorerSortBy,
  sortDir: SortDirection,
): DocumentSummary[] {
  const direction = sortDir === 'asc' ? 1 : -1;
  return [...documents].sort((left, right) => compareDocuments(left, right, sortBy, direction));
}

export function fileIcon(document: DocumentSummary, size: number): ReactNode {
  const extension = documentPreviewExtension(document) ?? '';
  if (['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff', 'gif'].includes(extension)) {
    return <FileImage size={size} />;
  }
  if (extension === 'pdf') {
    return <FileText size={size} />;
  }
  if (['zip', '7z', 'rar', 'gz'].includes(extension)) {
    return <Archive size={size} />;
  }
  if (['csv', 'xls', 'xlsx'].includes(extension)) {
    return <FileSpreadsheet size={size} />;
  }
  if (['js', 'jsx', 'ts', 'tsx', 'py', 'html', 'css', 'json', 'md'].includes(extension)) {
    return <Code2 size={size} />;
  }
  return <File size={size} />;
}

export function fileTypeLabel(document: DocumentSummary): string {
  const extension = documentPreviewExtension(document);
  return extension ? extension.toUpperCase() : 'File';
}

export function ocrStatus(document: DocumentSummary): string {
  if (
    document.docling_status === 'ok' ||
    document.mineru_status === 'ok' ||
    document.infinity_status === 'ok'
  ) {
    return 'OCR ready';
  }
  if (
    document.docling_status === 'error' ||
    document.mineru_status === 'error' ||
    document.infinity_status === 'error'
  ) {
    return 'OCR error';
  }
  return 'Pending';
}

export function oppositeDirection(direction: SortDirection): SortDirection {
  return direction === 'asc' ? 'desc' : 'asc';
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

export function formatDateTime(value: string | null | undefined): string {
  const timestamp = timestampValue(value);
  return timestamp === null ? '-' : dateTimeFormatter.format(timestamp);
}

function compareDocuments(
  left: DocumentSummary,
  right: DocumentSummary,
  sortBy: ExplorerSortBy,
  direction: number,
): number {
  if (sortBy === 'size') {
    return direction * (left.size_bytes - right.size_bytes) || direction * nameCompare(left, right);
  }
  if (sortBy === 'type') {
    return (
      direction * fileTypeLabel(left).localeCompare(fileTypeLabel(right)) ||
      direction * nameCompare(left, right)
    );
  }
  if (sortBy === 'status') {
    return (
      direction * ocrStatus(left).localeCompare(ocrStatus(right)) ||
      direction * nameCompare(left, right)
    );
  }
  if (sortBy === 'modified') {
    return (
      compareDates(left.modified_at, right.modified_at, direction) ||
      direction * nameCompare(left, right)
    );
  }
  if (sortBy === 'created') {
    return (
      compareDates(left.created_at, right.created_at, direction) ||
      direction * nameCompare(left, right)
    );
  }
  return direction * nameCompare(left, right);
}

function nameCompare(left: DocumentSummary, right: DocumentSummary): number {
  return left.filename.localeCompare(right.filename);
}

function compareDates(
  left: string | null | undefined,
  right: string | null | undefined,
  direction: number,
): number {
  const leftTimestamp = timestampValue(left);
  const rightTimestamp = timestampValue(right);
  if (leftTimestamp === null && rightTimestamp === null) {
    return 0;
  }
  if (leftTimestamp === null) {
    return 1;
  }
  if (rightTimestamp === null) {
    return -1;
  }
  return direction * (leftTimestamp - rightTimestamp);
}

function timestampValue(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}
