import type { MutableRefObject, RefObject } from 'react';
import { useEffect, useLayoutEffect, useRef } from 'react';
import type { OverlayBox, PageInfo } from '../../generated/model';
import type { PreviewRotation } from '../types';
import { overlayDomId } from './previewDom';
import { isPageAtViewportCenter, scrollElementToPage } from './previewNavigation';

const FOCUS_ZOOM = 1.6;

export function useActivePageScroll({
  activePageNo,
  activePageScrollRequestKey,
  pageIndexByNo,
  pages,
  previewRotation,
  previewZoom,
  scrollRef,
  suppressNextActiveScrollRef,
  onProgrammaticPageScroll,
}: {
  activePageNo: number;
  activePageScrollRequestKey: number;
  pageIndexByNo: Map<number, number>;
  pages: PageInfo[];
  previewRotation: PreviewRotation;
  previewZoom: number;
  scrollRef: RefObject<HTMLDivElement | null>;
  suppressNextActiveScrollRef: MutableRefObject<number | null>;
  onProgrammaticPageScroll: (pageNo: number) => void;
}) {
  const lastHandledScrollRequestKeyRef = useRef<number | null>(null);
  const lastScrollKeyRef = useRef<string | null>(null);

  useLayoutEffect(() => {
    const scrollKey = activePageScrollKey(activePageNo, pages, previewRotation);
    const pageIndex = pageIndexByNo.get(activePageNo);
    const suppressedPageNo = suppressNextActiveScrollRef.current;
    if (suppressedPageNo !== null) {
      const activePageIsCentered = isPageAtViewportCenter(
        scrollRef.current,
        pages,
        pageIndex,
        previewRotation,
        previewZoom,
      );
      if (suppressedPageNo === activePageNo && activePageIsCentered) {
        suppressNextActiveScrollRef.current = null;
        lastScrollKeyRef.current = scrollKey;
        lastHandledScrollRequestKeyRef.current = activePageScrollRequestKey;
        return;
      }
      suppressNextActiveScrollRef.current = null;
    }
    const activePageChanged = lastHandledScrollRequestKeyRef.current !== activePageScrollRequestKey;
    if (lastScrollKeyRef.current === scrollKey && !activePageChanged) {
      return;
    }
    lastScrollKeyRef.current = scrollKey;
    lastHandledScrollRequestKeyRef.current = activePageScrollRequestKey;
    const didScroll = scrollElementToPage(
      scrollRef.current,
      pages,
      pageIndex,
      previewRotation,
      previewZoom,
      'auto',
    );
    if (didScroll) {
      onProgrammaticPageScroll(activePageNo);
      window.requestAnimationFrame(() => {
        scrollElementToPage(
          scrollRef.current,
          pages,
          pageIndex,
          previewRotation,
          previewZoom,
          'auto',
        );
      });
    }
  }, [
    activePageNo,
    activePageScrollRequestKey,
    onProgrammaticPageScroll,
    pageIndexByNo,
    pages,
    previewRotation,
    previewZoom,
    scrollRef,
    suppressNextActiveScrollRef,
  ]);
}

function activePageScrollKey(
  activePageNo: number,
  pages: PageInfo[],
  previewRotation: PreviewRotation,
): string {
  const firstPageNo = pages[0]?.page_no ?? 0;
  const lastPageNo = pages.at(-1)?.page_no ?? 0;
  const activePage = pages.find((page) => page.page_no === activePageNo);
  const activeSize = activePage ? `${activePage.width}:${activePage.height}` : '0:0';
  return `${activePageNo}:${previewRotation}:${pages.length}:${firstPageNo}:${lastPageNo}:${activeSize}`;
}

export function useOverlayFocus({
  activeOverlay,
  onPreviewZoomChange,
  pageIndexByNo,
  pages,
  previewRotation,
  previewZoom,
  scrollRef,
}: {
  activeOverlay: OverlayBox | null;
  onPreviewZoomChange: (zoom: number) => void;
  pageIndexByNo: Map<number, number>;
  pages: PageInfo[];
  previewRotation: PreviewRotation;
  previewZoom: number;
  scrollRef: RefObject<HTMLDivElement | null>;
}) {
  const lastFocusedOverlayRef = useRef<string | null>(null);

  useEffect(() => {
    if (!activeOverlay || lastFocusedOverlayRef.current === activeOverlay.overlay_id) {
      return;
    }
    lastFocusedOverlayRef.current = activeOverlay.overlay_id;
    if (previewZoom < FOCUS_ZOOM) {
      onPreviewZoomChange(FOCUS_ZOOM);
    } else {
      scrollElementToPage(
        scrollRef.current,
        pages,
        pageIndexByNo.get(activeOverlay.page_no),
        previewRotation,
        previewZoom,
        'smooth',
      );
    }
    window.setTimeout(
      () => {
        globalThis.document.getElementById(overlayDomId(activeOverlay))?.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'center',
        });
      },
      previewZoom < FOCUS_ZOOM ? 180 : 0,
    );
  }, [
    activeOverlay,
    onPreviewZoomChange,
    pageIndexByNo,
    pages,
    previewRotation,
    previewZoom,
    scrollRef,
  ]);
}
