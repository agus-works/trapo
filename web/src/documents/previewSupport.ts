import type { DocumentSummary } from '../generated/model';

const imageExtensions = new Set(['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff', 'gif']);
const supportedPreviewExtensions = new Set(['pdf', ...imageExtensions]);

export function documentPreviewExtension(
  document: DocumentSummary | null | undefined,
): string | null {
  if (!document) {
    return null;
  }
  const storedExtension = normalizeExtensionValue(document.extension ?? null);
  return (
    storedExtension || extensionFromPath(document.filename) || extensionFromPath(document.path)
  );
}

export function isDocumentPreviewSupported(document: DocumentSummary | null | undefined): boolean {
  return supportedPreviewExtensions.has(documentPreviewExtension(document) ?? '');
}

export function previewUnsupportedMessage(document: DocumentSummary | null | undefined): string {
  const extension = documentPreviewExtension(document);
  const suffix = extension ? `.${extension}` : 'this file type';
  return `Preview is not supported for ${suffix}. Metadata, OCR status, and file location are still available.`;
}

function normalizeExtensionValue(extension: string | null): string {
  return extension?.trim().toLowerCase().replace(/^\./, '') ?? '';
}

function extensionFromPath(path: string | null | undefined): string | null {
  const filename = path?.replace(/\\/g, '/').split('/').filter(Boolean).at(-1) ?? '';
  const lastDot = filename.lastIndexOf('.');
  return lastDot < 0 || lastDot === filename.length - 1
    ? null
    : normalizeExtensionValue(filename.slice(lastDot + 1));
}
