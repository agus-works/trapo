import type { VirtualItem } from '@tanstack/react-virtual';
import type { PageInfo } from '../../generated/model';
import type { PreviewRotation } from '../types';
import { PAGE_LIST_PADDING, pageMetrics } from './pageMetrics';

export function pageIndexMap(pages: PageInfo[]): Map<number, number> {
  return new Map(pages.map((page, index) => [page.page_no, index]));
}

export function scrollElementToPage(
  scrollElement: HTMLDivElement | null,
  pages: PageInfo[],
  pageIndex: number | undefined,
  previewRotation: PreviewRotation,
  previewZoom: number,
  behavior: ScrollBehavior,
): boolean {
  if (!scrollElement || pageIndex === undefined || scrollElement.clientHeight <= 0) {
    return false;
  }
  scrollElement.scrollTo({
    behavior,
    top: pageScrollTop(pages, pageIndex, previewRotation, previewZoom, scrollElement.clientHeight),
  });
  return true;
}

export function isPageAtViewportCenter(
  scrollElement: HTMLDivElement | null,
  pages: PageInfo[],
  pageIndex: number | undefined,
  previewRotation: PreviewRotation,
  previewZoom: number,
): boolean {
  if (!scrollElement || pageIndex === undefined || scrollElement.clientHeight <= 0) {
    return false;
  }
  const center = scrollElement.scrollTop + scrollElement.clientHeight / 2;
  const row = pageRowBounds(pages, pageIndex, previewRotation, previewZoom);
  return center >= row.top && center <= row.bottom;
}

function pageScrollTop(
  pages: PageInfo[],
  pageIndex: number,
  previewRotation: PreviewRotation,
  previewZoom: number,
  viewportHeight: number,
): number {
  const row = pageRowBounds(pages, pageIndex, previewRotation, previewZoom);
  return Math.max(0, row.top + row.height / 2 - viewportHeight / 2);
}

function pageRowBounds(
  pages: PageInfo[],
  pageIndex: number,
  previewRotation: PreviewRotation,
  previewZoom: number,
): { bottom: number; height: number; top: number } {
  let pageTop = PAGE_LIST_PADDING;
  for (let index = 0; index < pageIndex; index += 1) {
    pageTop += pageMetrics(pages[index], previewRotation, previewZoom).rowHeight;
  }
  const rowHeight = pageMetrics(pages[pageIndex], previewRotation, previewZoom).rowHeight;
  return {
    bottom: pageTop + rowHeight,
    height: rowHeight,
    top: pageTop,
  };
}

export function centeredVirtualPageNo(
  virtualItems: VirtualItem[],
  scrollTop: number,
  viewportHeight: number,
  pages: PageInfo[],
): number | null {
  const center = scrollTop + viewportHeight / 2;
  let bestPage: number | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const item of virtualItems) {
    const page = pages[item.index];
    const rowCenter = item.start + item.size / 2;
    const distance = Math.abs(center - rowCenter);
    if (page && distance < bestDistance) {
      bestDistance = distance;
      bestPage = page.page_no;
    }
  }
  return bestPage;
}
