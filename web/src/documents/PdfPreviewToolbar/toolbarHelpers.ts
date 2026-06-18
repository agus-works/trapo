import type { MarkdownEngineRecord } from '../../generated/model';
import type { PreviewRotation } from '../types';

export function markdownEngineLabel(engine: MarkdownEngineRecord): string {
  const pageCount = engine.page_count ?? 0;
  const count = pageCount > 0 ? ` (${pageCount})` : '';
  const status = engine.status === 'error' ? ' !' : '';
  return `${engine.label}${count}${status}`;
}

export function clampPage(value: number, numPages: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.max(1, Math.min(Math.max(numPages, 1), Math.round(value)));
}

export function rotated(current: PreviewRotation, delta: -90 | 90): PreviewRotation {
  const normalized = (((current + delta) % 360) + 360) % 360;
  if (normalized === 90 || normalized === 180 || normalized === 270) {
    return normalized;
  }
  return 0;
}

export function engineLabel(engine: string): string {
  if (engine === 'docling') {
    return 'Docling';
  }
  if (engine === 'docling_normalized') {
    return 'Docling normalized';
  }
  if (engine === 'mineru') {
    return 'MinerU';
  }
  if (engine === 'mineru_normalized') {
    return 'MinerU normalized';
  }
  return engine;
}

export function engineColor(engine: string): string {
  if (engine.startsWith('fusion')) {
    return '#7c8cf8';
  }
  if (engine.startsWith('lmstudio')) {
    return '#d7b84f';
  }
  if (engine === 'docling_normalized') {
    return '#f07d5f';
  }
  if (engine === 'mineru') {
    return '#36cfd1';
  }
  if (engine === 'mineru_normalized') {
    return '#43b39f';
  }
  return '#d55344';
}
