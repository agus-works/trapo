import type { Virtualizer } from '@tanstack/react-virtual';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { RefObject } from 'react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import type {
  DocumentRegionsPayload,
  DocumentSummary,
  OverlayBox,
  PageInfo,
} from '../../generated/model';
import { isDocumentPreviewSupported, previewUnsupportedMessage } from '../previewSupport';
import type { PageSelectOptions, PreviewRotation } from '../types';
import { PageNavigationZones } from './PageNavigationZones';
import styles from './PdfDocumentPreview.module.css';
import { normalizedPages, PAGE_LIST_PADDING, pageMetrics } from './pageMetrics';
import { overlayDomId, pageHeaderDomId } from './previewDom';
import { centeredVirtualPageNo, pageIndexMap } from './previewNavigation';
import { usePreviewImagePrefetch } from './usePreviewImagePrefetch';
import { useActivePageScroll, useOverlayFocus } from './usePreviewPageFocus';
import { usePreviewPan } from './usePreviewPan';
import { usePreviewWheelZoom } from './usePreviewWheelZoom';
import { VirtualPage } from './VirtualPage';

const PROGRAMMATIC_PAGE_SCROLL_SYNC_LOCK_MS = 900;

interface PageScrollSyncLock {
  expiresAt: number;
  pageNo: number;
}

function pageScrollSyncLock(pageNo: number): PageScrollSyncLock {
  return {
    expiresAt: Date.now() + PROGRAMMATIC_PAGE_SCROLL_SYNC_LOCK_MS,
    pageNo,
  };
}

export function PdfDocumentPreview({
  activeOverlay,
  activePageNo,
  document,
  onOverlaySelect,
  onPageSelect,
  onPreviewZoomChange,
  onRenderError,
  onRenderSuccess,
  previewRotation,
  previewZoom,
  regions,
  visibleOverlayIds,
}: {
  regions: DocumentRegionsPayload | null;
  document: DocumentSummary | null;
  extension: string | null;
  assetObjectUrl: string | null;
  visibleOverlayIds: Set<string>;
  activeOverlay: OverlayBox | null;
  activePageNo: number;
  onOverlaySelect: (overlay: OverlayBox) => void;
  onPageSelect: (pageNo: number, options?: PageSelectOptions) => void;
  onPreviewZoomChange: (zoom: number) => void;
  onRenderError: (error: string | null) => void;
  onRenderSuccess: (numPages: number) => void;
  previewRotation: PreviewRotation;
  previewZoom: number;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const activePageNoRef = useRef(activePageNo);
  const activePageScrollRequestRef = useRef(0);
  const suppressNextActiveScrollRef = useRef<number | null>(null);
  const pageScrollSyncLockRef = useRef<PageScrollSyncLock | null>(pageScrollSyncLock(activePageNo));
  const previewSupported = isDocumentPreviewSupported(document);
  const pages = useMemo(() => normalizedPages(regions?.document.pages), [regions]);
  const pageIndexByNo = useMemo(() => pageIndexMap(pages), [pages]);
  const canvasWidth = useMemo(
    () =>
      Math.max(
        ...pages.map((page) => pageMetrics(page, previewRotation, previewZoom).frameWidth + 64),
      ),
    [pages, previewRotation, previewZoom],
  );
  const measurementKey = `${pages.length}:${previewRotation}:${previewZoom}:${canvasWidth}`;
  const panHandlers = usePreviewPan(scrollRef);
  usePreviewWheelZoom({
    enabled: previewSupported && Boolean(regions && document),
    onPreviewZoomChange,
    previewZoom,
    scrollRef,
  });
  const lockPageScrollSync = useCallback((pageNo: number) => {
    pageScrollSyncLockRef.current = pageScrollSyncLock(pageNo);
  }, []);

  if (activePageNoRef.current !== activePageNo) {
    pageScrollSyncLockRef.current = pageScrollSyncLock(activePageNo);
    activePageNoRef.current = activePageNo;
    activePageScrollRequestRef.current += 1;
  }
  usePreviewImagePrefetch(document, activePageNo, pages);

  const virtualizer = useVirtualizer({
    count: pages.length,
    estimateSize: (index) => pageMetrics(pages[index], previewRotation, previewZoom).rowHeight,
    getItemKey: (index) => pages[index]?.page_no ?? index,
    getScrollElement: () => scrollRef.current,
    onChange: (instance, sync) => {
      if (sync) {
        return;
      }
      if (!instance.scrollRect || instance.scrollOffset === null) {
        return;
      }
      const pageNo = centeredVirtualPageNo(
        instance.getVirtualItems(),
        instance.scrollOffset,
        instance.scrollRect.height,
        pages,
      );
      if (pageNo === null) {
        return;
      }
      const lock = pageScrollSyncLockRef.current;
      if (lock) {
        const lockActive = Date.now() <= lock.expiresAt;
        if (!lockActive || pageNo === lock.pageNo) {
          pageScrollSyncLockRef.current = null;
        }
        if (lockActive && pageNo !== lock.pageNo) {
          return;
        }
      }
      if (pageNo !== activePageNoRef.current) {
        suppressNextActiveScrollRef.current = pageNo;
        onPageSelect(pageNo, { replace: true, source: 'scroll' });
      }
    },
    overscan: 3,
    paddingEnd: PAGE_LIST_PADDING,
    paddingStart: PAGE_LIST_PADDING,
  });

  useEffect(() => {
    onRenderSuccess(pages.length);
  }, [onRenderSuccess, pages.length]);

  useEffect(() => {
    if (measurementKey) {
      virtualizer.measure();
    }
  }, [measurementKey, virtualizer]);
  useActivePageScroll({
    activePageNo,
    activePageScrollRequestKey: activePageScrollRequestRef.current,
    pageIndexByNo,
    pages,
    previewRotation,
    previewZoom,
    scrollRef,
    suppressNextActiveScrollRef,
    onProgrammaticPageScroll: lockPageScrollSync,
  });
  useOverlayFocus({
    activeOverlay,
    onPreviewZoomChange,
    pageIndexByNo,
    pages,
    previewRotation,
    previewZoom,
    scrollRef,
  });

  if (!previewSupported) {
    return <div className={styles.emptyState}>{previewUnsupportedMessage(document)}</div>;
  }
  if (!regions || !document) {
    return <div className={styles.emptyState}>No document loaded.</div>;
  }

  const activeIndex = pageIndexByNo.get(activePageNo) ?? 0;
  const previousPage = pages[Math.max(activeIndex - 1, 0)]?.page_no ?? activePageNo;
  const nextPage = pages[Math.min(activeIndex + 1, pages.length - 1)]?.page_no ?? activePageNo;

  return (
    <div className={styles.pdfViewportShell}>
      <PreviewScrollSurface
        activeOverlay={activeOverlay}
        activePageNo={activePageNo}
        canvasWidth={canvasWidth}
        document={document}
        onOverlaySelect={onOverlaySelect}
        onRenderError={onRenderError}
        pages={pages}
        panHandlers={panHandlers}
        previewRotation={previewRotation}
        previewZoom={previewZoom}
        regions={regions}
        scrollRef={scrollRef}
        virtualizer={virtualizer}
        visibleOverlayIds={visibleOverlayIds}
      />
      <PageNavigationZones
        activePageNo={activePageNo}
        nextPage={nextPage}
        onPageSelect={onPageSelect}
        previousPage={previousPage}
      />
    </div>
  );
}

function PreviewScrollSurface({
  activeOverlay,
  activePageNo,
  canvasWidth,
  document,
  onOverlaySelect,
  onRenderError,
  pages,
  panHandlers,
  previewRotation,
  previewZoom,
  regions,
  scrollRef,
  virtualizer,
  visibleOverlayIds,
}: {
  activeOverlay: OverlayBox | null;
  activePageNo: number;
  canvasWidth: number;
  document: DocumentSummary;
  onOverlaySelect: (overlay: OverlayBox) => void;
  onRenderError: (error: string | null) => void;
  pages: PageInfo[];
  panHandlers: ReturnType<typeof usePreviewPan>;
  previewRotation: PreviewRotation;
  previewZoom: number;
  regions: DocumentRegionsPayload;
  scrollRef: RefObject<HTMLDivElement | null>;
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  visibleOverlayIds: Set<string>;
}) {
  return (
    <section
      aria-label="Document page preview"
      className={styles.pdfVirtualScroll}
      data-dragging={panHandlers.dragging ? 'true' : 'false'}
      data-space-pan={panHandlers.spacePressed ? 'true' : 'false'}
      onPointerCancel={panHandlers.onPointerUp}
      onPointerDown={panHandlers.onPointerDown}
      onPointerMove={panHandlers.onPointerMove}
      onPointerUp={panHandlers.onPointerUp}
      ref={scrollRef}
    >
      <div
        className={styles.virtualCanvas}
        style={{ height: `${virtualizer.getTotalSize()}px`, minWidth: `${canvasWidth}px` }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => (
          <VirtualPage
            activeOverlay={activeOverlay}
            activePageNo={activePageNo}
            document={document}
            key={virtualItem.key}
            onOverlaySelect={onOverlaySelect}
            onRenderError={onRenderError}
            page={pages[virtualItem.index]}
            previewRotation={previewRotation}
            previewZoom={previewZoom}
            regions={regions}
            virtualItem={virtualItem}
            visibleOverlayIds={visibleOverlayIds}
          />
        ))}
      </div>
    </section>
  );
}

export function scrollToOverlay(overlay: OverlayBox) {
  window.setTimeout(() => {
    document.getElementById(overlayDomId(overlay))?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
      inline: 'center',
    });
  }, 0);
}

export function scrollToPage(pageNo: number) {
  window.setTimeout(() => {
    document.getElementById(pageHeaderDomId(pageNo))?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
      inline: 'center',
    });
  }, 0);
}
