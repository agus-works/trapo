import { useVirtualizer } from '@tanstack/react-virtual';
import { AlertTriangle, Loader2 } from 'lucide-react';
import type { CSSProperties, RefObject } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '../components/ui/resizable';
import { DiagnosticsDetailsPane } from './DiagnosticsDetailsPane';
import { DiagnosticsTimelineAxis, DiagnosticsTimelineGrid } from './DiagnosticsTimelineScale';
import styles from './DiagnosticsTimelineView.module.css';
import type { TimelineRow } from './diagnosticsTimelineRows';
import {
  buildTimelineRange,
  buildTimelineTicks,
  formatMs,
  visibleRows,
} from './diagnosticsTimelineRows';
import type { DiagnosticEventRecord, DiagnosticSpanRecord, DiagnosticTraceSummary } from './types';

interface DiagnosticsTimelinePanelsProps {
  events: DiagnosticEventRecord[];
  rows: TimelineRow[];
  selectedId: string | null;
  selectedSpan: DiagnosticSpanRecord | null;
  summary: DiagnosticTraceSummary | null;
  traceError?: string | null;
  traceLoading?: boolean;
  onSpanSelect: (spanId: string) => void;
}

export function DiagnosticsTimelinePanels({
  events,
  rows,
  selectedId,
  selectedSpan,
  summary,
  traceError = null,
  traceLoading = false,
  onSpanSelect,
}: DiagnosticsTimelinePanelsProps) {
  const [collapsedIds, setCollapsedIds] = useState(() => new Set<string>());
  const renderedRows = useMemo(() => visibleRows(rows, collapsedIds), [collapsedIds, rows]);
  const panelState = timelinePanelState(traceLoading, traceError, rows.length);
  const toggleCollapsed = (spanId: string) => {
    setCollapsedIds((current) => {
      const next = new Set(current);
      if (next.has(spanId)) {
        next.delete(spanId);
      } else {
        next.add(spanId);
      }
      return next;
    });
  };
  return (
    <ResizablePanelGroup className={styles.timelineGroup} direction="vertical">
      <ResizablePanel className={styles.timelinePanel} defaultSize={68} minSize={34}>
        <div className={styles.timelineHeader}>
          <span>Pipeline step</span>
          <span>Elapsed time · {formatMs(summary?.duration_ms ?? 0)}</span>
        </div>
        {panelState ? (
          <TimelinePanelState state={panelState} />
        ) : (
          <TimelineRowsViewport
            collapsedIds={collapsedIds}
            onSpanSelect={onSpanSelect}
            onToggleCollapsed={toggleCollapsed}
            rows={renderedRows}
            selectedId={selectedId}
          />
        )}
      </ResizablePanel>
      <ResizableHandle orientation="horizontal" />
      <ResizablePanel className={styles.detailsPanel} defaultSize={32} minSize={16}>
        <DiagnosticsDetailsPane events={events} span={selectedSpan} />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}

type TimelinePanelStateKind = 'empty' | 'error' | 'loading';

interface TimelinePanelStateRecord {
  kind: TimelinePanelStateKind;
  message: string;
}

function timelinePanelState(
  traceLoading: boolean,
  traceError: string | null,
  rowCount: number,
): TimelinePanelStateRecord | null {
  if (traceError) {
    return { kind: 'error', message: traceError };
  }
  if (traceLoading && rowCount === 0) {
    return { kind: 'loading', message: 'Loading diagnostics waterfall...' };
  }
  if (rowCount === 0) {
    return { kind: 'empty', message: 'No diagnostics found for this scope.' };
  }
  return null;
}

function TimelinePanelState({ state }: { state: TimelinePanelStateRecord }) {
  const icon =
    state.kind === 'loading' ? (
      <Loader2 className={styles.stateIconSpin} size={18} />
    ) : (
      <AlertTriangle size={18} />
    );
  return (
    <div className={styles.emptyState} data-state={state.kind}>
      {icon}
      <span>{state.message}</span>
    </div>
  );
}

function TimelineRowsViewport({
  rows,
  selectedId,
  onSpanSelect,
  collapsedIds,
  onToggleCollapsed,
}: {
  collapsedIds: ReadonlySet<string>;
  rows: TimelineRow[];
  selectedId: string | null;
  onSpanSelect: (spanId: string) => void;
  onToggleCollapsed: (spanId: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const viewportWidth = useElementWidth(viewportRef);
  const labelWidth = compactLabelWidth(viewportWidth);
  const trackWidth = Math.max(0, viewportWidth - labelWidth);
  const range = useMemo(() => buildTimelineRange(rows), [rows]);
  const ticks = useMemo(() => buildTimelineTicks(range, trackWidth), [range, trackWidth]);
  const virtualizer = useVirtualizer({
    count: rows.length,
    estimateSize: () => 24,
    getScrollElement: () => scrollerRef.current,
    overscan: 16,
  });
  const timelineStyle = { '--timeline-label-width': `${labelWidth}px` } as CSSProperties;
  return (
    <div className={styles.rowsViewport} ref={viewportRef} style={timelineStyle}>
      <DiagnosticsTimelineAxis ticks={ticks} />
      <div className={styles.rowsScroller} ref={scrollerRef}>
        <DiagnosticsTimelineGrid ticks={ticks} />
        <div className={styles.virtualRows} style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((item) => {
            const row = rows[item.index];
            return (
              <DiagnosticTimelineRow
                key={row.span.span_id}
                collapsed={collapsedIds.has(row.span.span_id)}
                onSelect={onSpanSelect}
                onToggleCollapsed={onToggleCollapsed}
                row={row}
                selected={row.span.span_id === selectedId}
                top={item.start}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function DiagnosticTimelineRow({
  collapsed,
  onSelect,
  onToggleCollapsed,
  row,
  selected,
  top,
}: {
  collapsed: boolean;
  onSelect: (spanId: string) => void;
  onToggleCollapsed: (spanId: string) => void;
  row: TimelineRow;
  selected: boolean;
  top: number;
}) {
  return (
    <div
      className={styles.row}
      data-selected={selected}
      style={{ transform: `translateY(${top}px)` }}
    >
      <div className={styles.rowLabelCell} style={{ paddingLeft: 10 + row.depth * 16 }}>
        {row.hasChildren ? (
          <button
            aria-label={collapsed ? 'Expand span' : 'Collapse span'}
            className={styles.rowTwisty}
            data-collapsed={collapsed}
            onClick={(event) => {
              event.stopPropagation();
              onToggleCollapsed(row.span.span_id);
            }}
            type="button"
          >
            ▾
          </button>
        ) : (
          <span className={styles.rowTwistySpacer} />
        )}
        <button
          className={styles.rowLabel}
          onClick={() => onSelect(row.span.span_id)}
          type="button"
        >
          <span data-status={row.span.status} />
          <strong>{row.span.pipeline_step}</strong>
          <small>{row.span.annotation_engine ?? row.span.category}</small>
        </button>
      </div>
      <div className={styles.track}>
        <button
          className={styles.bar}
          data-status={row.span.status}
          onClick={() => onSelect(row.span.span_id)}
          style={{ left: `${row.leftPct}%`, width: `${row.widthPct}%` }}
          title={`${row.span.name} · ${formatMs(row.span.duration_ms)}`}
          type="button"
        >
          {formatMs(row.span.duration_ms)}
        </button>
      </div>
    </div>
  );
}

function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return undefined;
    }

    const updateWidth = () => setWidth(element.getBoundingClientRect().width);
    updateWidth();
    const resizeObserver = new ResizeObserver((entries) => {
      setWidth(entries[0]?.contentRect.width ?? 0);
    });
    resizeObserver.observe(element);

    return () => resizeObserver.disconnect();
  }, [ref]);

  return width;
}

function compactLabelWidth(viewportWidth: number): number {
  if (viewportWidth <= 0) {
    return 220;
  }
  return Math.min(280, Math.max(168, viewportWidth * 0.3));
}
