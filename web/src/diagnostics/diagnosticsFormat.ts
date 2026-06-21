import type { DiagnosticRunRecord, DiagnosticWorkUnitRecord } from './types';

export function formatDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '-';
  }
  if (value < 1000) {
    return `${Math.round(value)}ms`;
  }
  const seconds = value / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = seconds / 60;
  if (minutes < 90) {
    return `${minutes.toFixed(1)}m`;
  }
  return `${(minutes / 60).toFixed(1)}h`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-';
  }
  return `${value.toFixed(value < 10 ? 1 : 0)}%`;
}

export function runLabel(run: DiagnosticRunRecord): string {
  const started = run.started_at
    ? new Date(run.started_at).toLocaleString()
    : `Run ${run.ingest_run_id}`;
  return `#${run.ingest_run_id} · ${started} · ${run.error_count} errors`;
}

export function workUnitLabel(unit: DiagnosticWorkUnitRecord): string {
  return unit.filename ?? sourcePathLabel(unit) ?? shortHash(unit.file_hash ?? 'run');
}

export function sourcePathLabel(unit: DiagnosticWorkUnitRecord | undefined): string | null {
  const sourcePath =
    unit?.source_path ??
    (typeof unit?.metadata.source_path === 'string' ? unit.metadata.source_path : null);
  if (!sourcePath) {
    return null;
  }
  return sourcePath.split(/[\\/]/).pop() ?? sourcePath;
}

export function shortHash(value: string): string {
  return value.length > 12 ? value.slice(0, 12) : value;
}

export function statusForUnits(units: DiagnosticWorkUnitRecord[]): string {
  if (units.some((unit) => unit.status === 'error')) {
    return 'error';
  }
  if (units.some((unit) => unit.status === 'running')) {
    return 'running';
  }
  if (units.length > 0 && units.every((unit) => unit.status === 'ok')) {
    return 'ok';
  }
  if (units.every((unit) => unit.status === 'skipped')) {
    return 'skipped';
  }
  return 'planned';
}
