export interface DocumentRouteSearch {
  diagnosticSpan?: string;
  diagnostics?: 'file' | 'page';
  file?: string;
  folder?: string;
  page?: number;
  overlay?: string;
  term?: string;
  highlight?: string;
  markdown?:
    | 'best_available_markdown'
    | 'lmstudio_markdown'
    | 'infinity_markdown'
    | 'markitdown'
    | 'markitdown_cu';
  overlays?: 'all' | 'selected' | 'hidden';
  view?: 'preview' | 'markdown' | 'split';
  explorerView?: 'tiles' | 'details';
  tileSize?: 'small' | 'medium' | 'large' | 'xlarge';
  sortBy?: 'name' | 'type' | 'size' | 'status' | 'modified' | 'created';
  sortDir?: 'asc' | 'desc';
  zoom?: number;
  rotation?: 0 | 90 | 180 | 270;
}

export interface DiagnosticsRouteSearch {
  q?: string;
  run?: number;
  span?: string;
  status?: 'all' | 'ok' | 'error' | 'skipped';
}

export function validateDocumentSearch(search: Record<string, unknown>): DocumentRouteSearch {
  return {
    diagnosticSpan: stringValue(search.diagnosticSpan),
    diagnostics: diagnosticsModeValue(search.diagnostics),
    explorerView: explorerViewValue(search.explorerView),
    file: stringValue(search.file),
    folder: stringValue(search.folder),
    highlight: stringValue(search.highlight),
    markdown: markdownEngineValue(search.markdown),
    overlay: stringValue(search.overlay),
    overlays: overlayModeValue(search.overlays),
    page: numberValue(search.page),
    sortBy: sortByValue(search.sortBy),
    sortDir: sortDirectionValue(search.sortDir),
    term: stringValue(search.term),
    tileSize: tileSizeValue(search.tileSize),
    view: viewModeValue(search.view),
    zoom: zoomValue(search.zoom),
    rotation: rotationValue(search.rotation),
  };
}

export function validateDiagnosticsSearch(search: Record<string, unknown>): DiagnosticsRouteSearch {
  return {
    q: stringValue(search.q),
    run: numberValue(search.run),
    span: stringValue(search.span),
    status: diagnosticStatusValue(search.status),
  };
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function numberValue(value: unknown): number | undefined {
  const parsed =
    typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : undefined;
}

function overlayModeValue(value: unknown): 'all' | 'selected' | 'hidden' | undefined {
  return value === 'all' || value === 'selected' || value === 'hidden' ? value : undefined;
}

function viewModeValue(value: unknown): 'preview' | 'markdown' | 'split' | undefined {
  return value === 'preview' || value === 'markdown' || value === 'split' ? value : undefined;
}

function markdownEngineValue(
  value: unknown,
):
  | 'best_available_markdown'
  | 'lmstudio_markdown'
  | 'infinity_markdown'
  | 'markitdown'
  | 'markitdown_cu'
  | undefined {
  return value === 'best_available_markdown' ||
    value === 'lmstudio_markdown' ||
    value === 'infinity_markdown' ||
    value === 'markitdown' ||
    value === 'markitdown_cu'
    ? value
    : undefined;
}

function explorerViewValue(value: unknown): 'tiles' | 'details' | undefined {
  return value === 'tiles' || value === 'details' ? value : undefined;
}

function tileSizeValue(value: unknown): 'small' | 'medium' | 'large' | 'xlarge' | undefined {
  return value === 'small' || value === 'medium' || value === 'large' || value === 'xlarge'
    ? value
    : undefined;
}

function sortByValue(
  value: unknown,
): 'name' | 'type' | 'size' | 'status' | 'modified' | 'created' | undefined {
  return value === 'name' ||
    value === 'type' ||
    value === 'size' ||
    value === 'status' ||
    value === 'modified' ||
    value === 'created'
    ? value
    : undefined;
}

function sortDirectionValue(value: unknown): 'asc' | 'desc' | undefined {
  return value === 'asc' || value === 'desc' ? value : undefined;
}

function zoomValue(value: unknown): number | undefined {
  const parsed = numberValue(value);
  if (parsed === undefined || parsed <= 0) {
    return undefined;
  }
  return Math.min(3, Math.max(0.25, Math.round(parsed * 100) / 100));
}

function rotationValue(value: unknown): 0 | 90 | 180 | 270 | undefined {
  const parsed = numberValue(value);
  if (parsed === undefined) {
    return undefined;
  }
  const normalized = (((Math.round(parsed / 90) * 90) % 360) + 360) % 360;
  if (normalized === 90 || normalized === 180 || normalized === 270) {
    return normalized;
  }
  return 0;
}

function diagnosticsModeValue(value: unknown): 'file' | 'page' | undefined {
  return value === 'file' || value === 'page' ? value : undefined;
}

function diagnosticStatusValue(value: unknown): 'all' | 'ok' | 'error' | 'skipped' | undefined {
  return value === 'all' || value === 'ok' || value === 'error' || value === 'skipped'
    ? value
    : undefined;
}
