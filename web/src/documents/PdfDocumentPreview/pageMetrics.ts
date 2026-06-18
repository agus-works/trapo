import type { PageInfo } from '../../generated/model';
import type { PreviewRotation } from '../types';
import { documentPageWidth } from './previewLayout';

export const PAGE_LIST_PADDING = 18;

const PAGE_HEADER_HEIGHT = 24;
const PAGE_VERTICAL_GAP = 22;

export interface PageMetrics {
  baseHeight: number;
  baseWidth: number;
  frameHeight: number;
  frameWidth: number;
  rowHeight: number;
  surfaceHeight: number;
  surfaceWidth: number;
}

export function pageMetrics(
  page: PageInfo,
  previewRotation: PreviewRotation,
  previewZoom: number,
): PageMetrics {
  const baseWidth = Math.min(documentPageWidth, Math.max(page.width, 1));
  const baseHeight = baseWidth * (Math.max(page.height, 1) / Math.max(page.width, 1));
  const rotationSwapsAxes = previewRotation === 90 || previewRotation === 270;
  const frameWidth = (rotationSwapsAxes ? baseHeight : baseWidth) * previewZoom;
  const frameHeight = (rotationSwapsAxes ? baseWidth : baseHeight) * previewZoom;
  return {
    baseHeight,
    baseWidth,
    frameHeight,
    frameWidth,
    rowHeight: frameHeight + PAGE_HEADER_HEIGHT + PAGE_VERTICAL_GAP,
    surfaceHeight: baseHeight * previewZoom,
    surfaceWidth: baseWidth * previewZoom,
  };
}

export function normalizedPages(pages: PageInfo[] | undefined): PageInfo[] {
  return pages?.length ? pages : [{ page_no: 1, width: documentPageWidth, height: 1 }];
}
