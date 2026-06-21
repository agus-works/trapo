import { Link } from '@tanstack/react-router';
import { ChevronDown, ChevronRight, Clock, FileText, Loader2 } from 'lucide-react';
import { useMemo } from 'react';
import { useDiagnosticProgressQuery } from '../queries/hooks';
import styles from './DiagnosticsProgressView.module.css';
import { formatDuration, formatPercent } from './diagnosticsFormat';
import type { ProgressNode } from './diagnosticsProgressTree';
import {
  buildProgressTree,
  toggleProgressNode,
  visibleProgressRows,
} from './diagnosticsProgressTree';
import type { DiagnosticProgressPayload } from './types';

interface DiagnosticsProgressViewProps {
  expandedIds: Set<string>;
  runId: number | null;
  selectedUnitId?: number | null;
  onExpandedChange: (expandedIds: Set<string>) => void;
  onUnitSelect: (unitId: number) => void;
}

export function DiagnosticsProgressView({
  expandedIds,
  runId,
  selectedUnitId,
  onExpandedChange,
  onUnitSelect,
}: DiagnosticsProgressViewProps) {
  const progressQuery = useDiagnosticProgressQuery(runId);
  return (
    <DiagnosticsProgressPanel
      expandedIds={expandedIds}
      isFetching={progressQuery.isFetching}
      onExpandedChange={onExpandedChange}
      onUnitSelect={onUnitSelect}
      progress={progressQuery.data}
      selectedUnitId={selectedUnitId}
    />
  );
}

export function DiagnosticsProgressPanel({
  expandedIds = new Set<string>(),
  isFetching = false,
  onExpandedChange = () => undefined,
  onUnitSelect = () => undefined,
  progress,
  selectedUnitId = null,
}: {
  expandedIds?: Set<string>;
  isFetching?: boolean;
  onExpandedChange?: (expandedIds: Set<string>) => void;
  onUnitSelect?: (unitId: number) => void;
  progress: DiagnosticProgressPayload | undefined;
  selectedUnitId?: number | null;
}) {
  const rows = useMemo(
    () => visibleProgressRows(buildProgressTree(progress), expandedIds),
    [expandedIds, progress],
  );
  if (!progress || progress.summary.total_units === 0) {
    return <EmptyProgress isFetching={isFetching} />;
  }
  return (
    <section className={styles.progressShell}>
      <ProgressSummary progress={progress} />
      <div className={styles.treeHeader}>
        <span>Work item</span>
        <span>Status</span>
        <span>Phase</span>
        <span>Engine</span>
        <span>Model</span>
        <span>Duration</span>
        <span>Open</span>
      </div>
      <div className={styles.treeBody}>
        {rows.map((row) => (
          <ProgressTreeRow
            expanded={expandedIds.has(row.id)}
            key={row.id}
            onExpandedChange={onExpandedChange}
            onUnitSelect={onUnitSelect}
            row={row}
            selected={row.unit?.work_unit_id === selectedUnitId}
            visibleExpandedIds={expandedIds}
          />
        ))}
      </div>
    </section>
  );
}

function ProgressSummary({ progress }: { progress: DiagnosticProgressPayload }) {
  return (
    <div className={styles.summaryStrip}>
      <div className={styles.meterCell}>
        <strong>{formatPercent(progress.summary.percent_complete)}</strong>
        <div className={styles.meterTrack}>
          <div
            className={styles.meterFill}
            style={{ width: `${Math.max(0, Math.min(100, progress.summary.percent_complete))}%` }}
          />
        </div>
      </div>
      <SummaryCell label="Done" value={progress.summary.completed_units} />
      <SummaryCell label="Running" value={progress.summary.running_units} />
      <SummaryCell label="Failed" value={progress.summary.failed_units} />
      <SummaryCell label="ETA" value={formatDuration(progress.summary.estimated_remaining_ms)} />
    </div>
  );
}

function SummaryCell({ label, value }: { label: string; value: number | string }) {
  return (
    <div className={styles.summaryCell}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProgressTreeRow({
  expanded,
  row,
  selected,
  visibleExpandedIds,
  onExpandedChange,
  onUnitSelect,
}: {
  expanded: boolean;
  row: ProgressNode;
  selected: boolean;
  visibleExpandedIds: Set<string>;
  onExpandedChange: (expandedIds: Set<string>) => void;
  onUnitSelect: (unitId: number) => void;
}) {
  const hasChildren = row.children.length > 0;
  return (
    <div className={styles.treeRow} data-kind={row.kind} data-selected={selected}>
      <div className={styles.nameCell} style={{ paddingLeft: 8 + row.depth * 16 }}>
        <button
          aria-label={expanded ? `Collapse ${row.label}` : `Expand ${row.label}`}
          className={styles.twisty}
          disabled={!hasChildren}
          onClick={() => onExpandedChange(toggleProgressNode(visibleExpandedIds, row.id))}
          type="button"
        >
          {hasChildren ? expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} /> : null}
        </button>
        <button
          className={styles.rowLabel}
          disabled={!row.unit}
          onClick={() => row.unit && onUnitSelect(row.unit.work_unit_id)}
          type="button"
        >
          {row.kind === 'file' ? <FileText size={13} /> : null}
          <span>{row.label}</span>
        </button>
      </div>
      <span className={styles.statusPill} data-status={row.status}>
        {row.status}
      </span>
      <span>{row.phase}</span>
      <span>{row.engine}</span>
      <span>{row.model}</span>
      <span>{formatDuration(row.durationMs)}</span>
      <ExplorerLink row={row} />
    </div>
  );
}

function ExplorerLink({ row }: { row: ProgressNode }) {
  if (!row.fileHash) {
    return <span className={styles.muted}>-</span>;
  }
  return (
    <Link
      className={styles.explorerLink}
      search={{
        diagnostics: row.pageNo ? 'page' : 'file',
        file: row.fileHash,
        page: row.pageNo ?? undefined,
      }}
      to="/"
    >
      Explorer
    </Link>
  );
}

function EmptyProgress({ isFetching }: { isFetching: boolean }) {
  return (
    <section className={styles.progressShell}>
      <div className={styles.emptyProgress}>
        {isFetching ? <Loader2 size={15} /> : <Clock size={15} />}
        <span>No planned ingest work for this run.</span>
      </div>
    </section>
  );
}
