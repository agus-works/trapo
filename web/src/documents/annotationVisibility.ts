import type { DocumentRegionsPayload, OverlayBox } from '../generated/model';

const storageKey = 'trapo.annotationViewer';
const schemaVersion = 1;

export type AnnotationEngineVisibility = Record<string, boolean>;

interface StoredAnnotationViewerState {
  schemaVersion: number;
  engines: AnnotationEngineVisibility;
}

export function readAnnotationEngineVisibility(): AnnotationEngineVisibility {
  const stored = localStorage.getItem(storageKey);
  if (!stored) {
    return defaultEngineVisibility();
  }
  const parsed = parseStoredState(stored);
  if (!parsed || parsed.schemaVersion !== schemaVersion) {
    localStorage.removeItem(storageKey);
    return defaultEngineVisibility();
  }
  return parsed.engines;
}

export function writeAnnotationEngineVisibility(engines: AnnotationEngineVisibility) {
  const payload: StoredAnnotationViewerState = { engines, schemaVersion };
  localStorage.setItem(storageKey, JSON.stringify(payload));
}

export function normalizeEngineVisibility(
  regions: DocumentRegionsPayload | null,
  current: AnnotationEngineVisibility,
): AnnotationEngineVisibility {
  const next: AnnotationEngineVisibility = { ...current };
  for (const engine of annotationEnginesForRegions(regions)) {
    next[engine] = current[engine] ?? true;
  }
  return next;
}

export function annotationEnginesForRegions(regions: DocumentRegionsPayload | null): string[] {
  const engines = new Set<string>();
  for (const overlay of regions?.overlays ?? []) {
    engines.add(overlay.annotation_engine ?? 'docling');
  }
  return [...engines].sort((left, right) => left.localeCompare(right));
}

export function overlayIsVisible(
  overlay: OverlayBox,
  engineVisibility: AnnotationEngineVisibility,
): boolean {
  return !overlay.hidden && (engineVisibility[overlay.annotation_engine ?? 'docling'] ?? true);
}

function parseStoredState(value: string): StoredAnnotationViewerState | null {
  try {
    const parsed: unknown = JSON.parse(value);
    if (!isStoredState(parsed)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function isStoredState(value: unknown): value is StoredAnnotationViewerState {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Partial<StoredAnnotationViewerState>;
  return (
    candidate.schemaVersion === schemaVersion &&
    Boolean(candidate.engines) &&
    typeof candidate.engines === 'object' &&
    Object.values(candidate.engines).every((item) => typeof item === 'boolean')
  );
}

function defaultEngineVisibility(): AnnotationEngineVisibility {
  return { docling: true, docling_normalized: true, mineru: true, mineru_normalized: true };
}
