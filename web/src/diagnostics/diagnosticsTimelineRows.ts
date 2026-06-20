import type { DiagnosticSpanRecord } from './types';

export interface TimelineRow {
  depth: number;
  hasChildren: boolean;
  leftPct: number;
  span: DiagnosticSpanRecord;
  widthPct: number;
}

export interface TimelineRange {
  durationMs: number;
  endMs: number;
  startMs: number;
}

export interface TimelineTick {
  edge: 'start' | 'middle' | 'end';
  elapsedMs: number;
  label: string;
  leftPct: number;
}

export function buildRows(spans: DiagnosticSpanRecord[]): TimelineRow[] {
  const sorted = [...spans].sort(
    (left, right) =>
      Date.parse(left.started_at) - Date.parse(right.started_at) ||
      right.duration_ms - left.duration_ms,
  );
  const start = minTimestamp(sorted, 'started_at');
  const end = Math.max(start + 1, minTimestamp(sorted, 'ended_at', Math.max));
  const total = Math.max(1, end - start);
  const byId = new Map(sorted.map((span) => [span.span_id, span]));
  const childParentIds = new Set(
    sorted
      .map((span) => span.parent_span_id)
      .filter((parentId): parentId is string => Boolean(parentId)),
  );
  const depthCache = new Map<string, number>();

  return sorted.map((span) => {
    const leftPct = clampPercent(((Date.parse(span.started_at) - start) / total) * 100);
    const rawWidthPct = Math.max(0.35, (span.duration_ms / total) * 100);
    const widthPct = Math.min(rawWidthPct, Math.max(0.35, 100 - leftPct));
    return {
      depth: depthFor(span, byId, depthCache),
      hasChildren: childParentIds.has(span.span_id),
      leftPct,
      span,
      widthPct,
    };
  });
}

export function visibleRows(rows: TimelineRow[], collapsedIds: ReadonlySet<string>): TimelineRow[] {
  const hiddenParentIds = new Set<string>();
  return rows.filter((row) => {
    const parentId = row.span.parent_span_id;
    if (parentId && hiddenParentIds.has(parentId)) {
      if (row.hasChildren) {
        hiddenParentIds.add(row.span.span_id);
      }
      return false;
    }
    if (collapsedIds.has(row.span.span_id)) {
      hiddenParentIds.add(row.span.span_id);
    }
    return true;
  });
}

export function buildTimelineRange(rows: readonly TimelineRow[]): TimelineRange {
  const startMs = minTimestamp(
    rows.map((row) => row.span),
    'started_at',
  );
  const endMs = Math.max(
    startMs + 1,
    minTimestamp(
      rows.map((row) => row.span),
      'ended_at',
      Math.max,
    ),
  );
  return { durationMs: Math.max(1, endMs - startMs), endMs, startMs };
}

export function buildTimelineTicks(range: TimelineRange, trackWidthPx: number): TimelineTick[] {
  if (trackWidthPx <= 0) {
    return [{ edge: 'start', elapsedMs: 0, label: formatMs(0), leftPct: 0 }];
  }
  const targetIntervalCount = clamp(Math.floor(trackWidthPx / 92), 3, 10);
  const intervalMs = niceInterval(range.durationMs / targetIntervalCount);
  const ticks: TimelineTick[] = [{ edge: 'start', elapsedMs: 0, label: formatMs(0), leftPct: 0 }];

  for (let elapsedMs = intervalMs; elapsedMs < range.durationMs; elapsedMs += intervalMs) {
    ticks.push({
      edge: 'middle',
      elapsedMs,
      label: formatMs(elapsedMs),
      leftPct: (elapsedMs / range.durationMs) * 100,
    });
  }

  const last = ticks.at(-1);
  if (!last || range.durationMs - last.elapsedMs > intervalMs * 0.28) {
    ticks.push({
      edge: 'end',
      elapsedMs: range.durationMs,
      label: formatMs(range.durationMs),
      leftPct: 100,
    });
  }

  return ticks;
}

export function firstErrorId(rows: TimelineRow[]): string | null {
  return rows.find((row) => row.span.status === 'error')?.span.span_id ?? null;
}

export function formatMs(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value.toFixed(1)}ms`;
}

function depthFor(
  span: DiagnosticSpanRecord,
  byId: Map<string, DiagnosticSpanRecord>,
  depthCache: Map<string, number>,
): number {
  const cached = depthCache.get(span.span_id);
  if (cached !== undefined) {
    return cached;
  }
  const parent = span.parent_span_id ? byId.get(span.parent_span_id) : null;
  const depth = parent ? depthFor(parent, byId, depthCache) + 1 : 0;
  depthCache.set(span.span_id, depth);
  return depth;
}

function minTimestamp(
  spans: DiagnosticSpanRecord[],
  key: 'started_at' | 'ended_at',
  aggregate: (...values: number[]) => number = Math.min,
): number {
  const values = spans.map((span) => Date.parse(span[key])).filter(Number.isFinite);
  return values.length > 0 ? aggregate(...values) : Date.now();
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function clampPercent(value: number): number {
  return clamp(value, 0, 100);
}

function niceInterval(value: number): number {
  if (value <= 0) {
    return 1;
  }
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const multiplier = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 2.5 ? 2.5 : scaled <= 5 ? 5 : 10;
  return multiplier * magnitude;
}
