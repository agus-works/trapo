import type { DocumentSummary } from '../generated/model';

export function commonDirectoryRootParts(documents: readonly DocumentSummary[]): string[] {
  const directories = documents
    .map(directoryPathPartsForDocument)
    .filter((parts) => parts.length > 0);
  if (directories.length === 0) {
    return [];
  }

  const root: string[] = [];
  const shortest = Math.min(...directories.map((parts) => parts.length));
  for (let index = 0; index < shortest; index += 1) {
    const first = directories[0][index];
    if (!directories.every((parts) => samePathPart(parts[index], first))) {
      break;
    }
    root.push(first);
  }
  return root;
}

export function directoryPartsForDocument(
  document: DocumentSummary,
  rootParts: readonly string[],
): string[] {
  const directoryParts = directoryPathPartsForDocument(document);
  const relativeParts = commonPrefixMatches(directoryParts, rootParts)
    ? directoryParts.slice(rootParts.length)
    : directoryParts;
  return relativeParts.length > 0 ? relativeParts : ['(root)'];
}

export function directoryPathPartsForDocument(document: DocumentSummary): string[] {
  const pathParts = normalizePathSeparators(document.path ?? document.filename)
    .split('/')
    .filter(Boolean);
  return pathParts.length > 1 ? pathParts.slice(0, -1) : [];
}

export function normalizePathSeparators(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+/g, '/');
}

export function samePathPart(left: string, right: string): boolean {
  return left.localeCompare(right, undefined, { sensitivity: 'accent' }) === 0;
}

function commonPrefixMatches(parts: readonly string[], rootParts: readonly string[]): boolean {
  return (
    rootParts.length <= parts.length &&
    rootParts.every((part, index) => samePathPart(parts[index], part))
  );
}
