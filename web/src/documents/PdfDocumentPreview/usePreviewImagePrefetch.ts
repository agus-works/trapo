import { useEffect } from 'react';
import type { DocumentSummary, PageInfo } from '../../generated/model';
import { trapoApi } from '../../services/trapoApi';

const PREFETCH_RADIUS = 10;
const MAX_PREFETCH_WORKERS = 2;

export function usePreviewImagePrefetch(
  document: DocumentSummary | null,
  activePageNo: number,
  pages: PageInfo[],
) {
  useEffect(() => {
    if (!document || pages.length === 0) {
      return;
    }
    const queue = prefetchPageNumbers(activePageNo, pages);
    let cancelled = false;
    let nextIndex = 0;
    const prefetchNext = async () => {
      while (!cancelled && nextIndex < queue.length) {
        const pageNo = queue[nextIndex];
        nextIndex += 1;
        await preloadImage(
          trapoApi.documentPreviewImageUrl(document.file_hash, 'normalized', pageNo),
        );
      }
    };
    for (let worker = 0; worker < Math.min(MAX_PREFETCH_WORKERS, queue.length); worker += 1) {
      void prefetchNext();
    }
    return () => {
      cancelled = true;
    };
  }, [activePageNo, document, pages]);
}

function prefetchPageNumbers(activePageNo: number, pages: PageInfo[]): number[] {
  const available = new Set(pages.map((page) => page.page_no));
  const results: number[] = [];
  for (let distance = 1; distance <= PREFETCH_RADIUS; distance += 1) {
    for (const pageNo of [activePageNo - distance, activePageNo + distance]) {
      if (available.has(pageNo)) {
        results.push(pageNo);
      }
    }
  }
  return results;
}

function preloadImage(src: string): Promise<void> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve();
    image.onerror = () => resolve();
    image.src = src;
  });
}
