import { statusForUnits, workUnitLabel } from './diagnosticsFormat';
import type { DiagnosticProgressPayload, DiagnosticWorkUnitRecord } from './types';

export interface ProgressNode {
  id: string;
  label: string;
  kind: 'file' | 'page' | 'phase' | 'unit' | 'detail';
  status: string;
  phase: string;
  engine: string;
  model: string;
  durationMs: number | null;
  fileHash?: string | null;
  pageNo?: number | null;
  unit?: DiagnosticWorkUnitRecord;
  children: ProgressNode[];
  depth: number;
}

export function buildProgressTree(progress: DiagnosticProgressPayload | undefined): ProgressNode[] {
  if (!progress) {
    return [];
  }
  const byFile = new Map<string, DiagnosticWorkUnitRecord[]>();
  for (const unit of progress.work_units) {
    const key = unit.file_hash ?? 'run';
    byFile.set(key, [...(byFile.get(key) ?? []), unit]);
  }
  return [...byFile.entries()].map(([fileHash, units]) => fileNode(fileHash, units));
}

export function visibleProgressRows(
  nodes: ProgressNode[],
  expandedIds: Set<string>,
): ProgressNode[] {
  const rows: ProgressNode[] = [];
  const visit = (items: ProgressNode[], depth: number) => {
    for (const item of items) {
      const row = { ...item, depth };
      rows.push(row);
      if (item.children.length > 0 && expandedIds.has(item.id)) {
        visit(item.children, depth + 1);
      }
    }
  };
  visit(nodes, 0);
  return rows;
}

export function toggleProgressNode(current: Set<string>, id: string): Set<string> {
  const next = new Set(current);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  return next;
}

function fileNode(fileHash: string, units: DiagnosticWorkUnitRecord[]): ProgressNode {
  const fileUnit = units[0];
  const pageGroups = groupUnits(units, (unit) => String(unit.page_no ?? 'document'));
  return node({
    children: [...pageGroups.entries()].map(([pageKey, pageUnits]) =>
      pageNode(pageKey, pageUnits, fileHash),
    ),
    durationMs: sumDuration(units),
    fileHash: fileUnit.file_hash,
    id: `file:${fileHash}`,
    kind: 'file',
    label: workUnitLabel(fileUnit),
    status: statusForUnits(units),
  });
}

function pageNode(
  pageKey: string,
  units: DiagnosticWorkUnitRecord[],
  fileHash: string,
): ProgressNode {
  const pageNo = pageKey === 'document' ? null : Number(pageKey);
  const phaseGroups = groupUnits(units, (unit) => unit.phase);
  return node({
    children: [...phaseGroups.entries()].map(([phase, phaseUnits]) =>
      phaseNode(fileHash, pageNo, phase, phaseUnits),
    ),
    durationMs: sumDuration(units),
    fileHash,
    id: `page:${fileHash}:${pageKey}`,
    kind: pageNo === null ? 'phase' : 'page',
    label: pageNo === null ? 'Document-level tasks' : `Page ${pageNo}`,
    pageNo,
    status: statusForUnits(units),
  });
}

function phaseNode(
  fileHash: string,
  pageNo: number | null,
  phase: string,
  units: DiagnosticWorkUnitRecord[],
): ProgressNode {
  return node({
    children: units.map(unitNode),
    durationMs: sumDuration(units),
    fileHash,
    id: `phase:${fileHash}:${pageNo ?? 'document'}:${phase}`,
    kind: 'phase',
    label: phase,
    pageNo,
    phase,
    status: statusForUnits(units),
  });
}

function unitNode(unit: DiagnosticWorkUnitRecord): ProgressNode {
  return node({
    children: unitDetailNodes(unit),
    durationMs: unit.duration_ms ?? null,
    engine: unit.engine,
    fileHash: unit.file_hash,
    id: `unit:${unit.work_unit_id}`,
    kind: 'unit',
    label: `${unit.engine} · ${unit.work_key}`,
    model: unit.model,
    pageNo: unit.page_no,
    phase: unit.phase,
    status: unit.status,
    unit,
  });
}

function unitDetailNodes(unit: DiagnosticWorkUnitRecord): ProgressNode[] {
  const rows: ProgressNode[] = [];
  if (unit.error) {
    rows.push(detailNode(unit, 'error', unit.error));
  }
  if (unit.attempt_count > 1) {
    rows.push(detailNode(unit, 'attempts', `${unit.attempt_count} attempts`));
  }
  const resultKeys = Object.keys(unit.result);
  if (resultKeys.length > 0) {
    rows.push(detailNode(unit, 'result', `result: ${resultKeys.slice(0, 4).join(', ')}`));
  }
  return rows;
}

function detailNode(unit: DiagnosticWorkUnitRecord, key: string, label: string): ProgressNode {
  return node({
    children: [],
    fileHash: unit.file_hash,
    id: `unit:${unit.work_unit_id}:${key}`,
    kind: 'detail',
    label,
    pageNo: unit.page_no,
    phase: unit.phase,
    status: unit.status,
  });
}

function node(value: Partial<ProgressNode> & Pick<ProgressNode, 'id' | 'kind' | 'label'>) {
  return {
    children: value.children ?? [],
    depth: 0,
    durationMs: value.durationMs ?? null,
    engine: value.engine ?? '-',
    fileHash: value.fileHash ?? null,
    id: value.id,
    kind: value.kind,
    label: value.label,
    model: value.model ?? '-',
    pageNo: value.pageNo ?? null,
    phase: value.phase ?? '-',
    status: value.status ?? 'planned',
    unit: value.unit,
  } satisfies ProgressNode;
}

function groupUnits(
  units: DiagnosticWorkUnitRecord[],
  key: (unit: DiagnosticWorkUnitRecord) => string,
) {
  const groups = new Map<string, DiagnosticWorkUnitRecord[]>();
  for (const unit of units) {
    const groupKey = key(unit);
    groups.set(groupKey, [...(groups.get(groupKey) ?? []), unit]);
  }
  return groups;
}

function sumDuration(units: DiagnosticWorkUnitRecord[]): number {
  return units.reduce((total, unit) => total + (unit.duration_ms ?? 0), 0);
}
