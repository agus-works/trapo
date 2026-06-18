import type { RefObject } from 'react';
import { useEffect, useLayoutEffect, useRef } from 'react';
import { pageFrameDomId } from './previewDom';

const DOM_DELTA_LINE = 1;
const DOM_DELTA_PAGE = 2;
const MAX_ZOOM = 3;
const MIN_ZOOM = 0.25;
const WHEEL_ZOOM_SENSITIVITY = 500;

interface ZoomAnchor {
  localX: number;
  localY: number;
  pageNo: number | null;
  pageXRatio: number | null;
  pageYRatio: number | null;
  scrollHeight: number;
  scrollLeft: number;
  scrollTop: number;
  scrollWidth: number;
  zoom: number;
}

export function usePreviewWheelZoom({
  enabled,
  onPreviewZoomChange,
  previewZoom,
  scrollRef,
}: {
  enabled: boolean;
  onPreviewZoomChange: (zoom: number) => void;
  previewZoom: number;
  scrollRef: RefObject<HTMLDivElement | null>;
}) {
  const onPreviewZoomChangeRef = useRef(onPreviewZoomChange);
  const zoomAnchorRef = useRef<ZoomAnchor | null>(null);
  const targetZoomRef = useRef(previewZoom);

  useLayoutEffect(() => {
    onPreviewZoomChangeRef.current = onPreviewZoomChange;
  }, [onPreviewZoomChange]);

  useLayoutEffect(() => {
    targetZoomRef.current = previewZoom;
    const anchor = zoomAnchorRef.current;
    const scrollElement = scrollRef.current;
    if (!anchor || !scrollElement || anchor.zoom !== previewZoom) {
      return;
    }
    zoomAnchorRef.current = null;
    restoreZoomAnchor(scrollElement, anchor);
  }, [previewZoom, scrollRef]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const scrollElement = scrollRef.current;
    if (!scrollElement) {
      return;
    }

    const onNativeWheel = (event: WheelEvent) => {
      if (!event.ctrlKey || event.deltaY === 0) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const nextZoom = wheelZoomValue(targetZoomRef.current, event, scrollElement);
      if (nextZoom === targetZoomRef.current) {
        return;
      }
      targetZoomRef.current = nextZoom;
      zoomAnchorRef.current = captureZoomAnchor(scrollElement, event, nextZoom);
      onPreviewZoomChangeRef.current(nextZoom);
    };

    scrollElement.addEventListener('wheel', onNativeWheel, { capture: true, passive: false });
    return () => {
      scrollElement.removeEventListener('wheel', onNativeWheel, { capture: true });
    };
  }, [enabled, scrollRef]);
}

function captureZoomAnchor(
  scrollElement: HTMLDivElement,
  event: WheelEvent,
  zoom: number,
): ZoomAnchor {
  const scrollRect = scrollElement.getBoundingClientRect();
  const pageFrame = pageFrameAtPoint(event.clientX, event.clientY);
  const pageNo = pageFrame ? Number(pageFrame.dataset.pageNo) : Number.NaN;
  const pageRect = pageFrame?.getBoundingClientRect();
  const hasPageAnchor =
    pageFrame && pageRect && Number.isFinite(pageNo) && pageRect.width > 0 && pageRect.height > 0;

  return {
    localX: event.clientX - scrollRect.left,
    localY: event.clientY - scrollRect.top,
    pageNo: hasPageAnchor ? pageNo : null,
    pageXRatio: hasPageAnchor ? (event.clientX - pageRect.left) / pageRect.width : null,
    pageYRatio: hasPageAnchor ? (event.clientY - pageRect.top) / pageRect.height : null,
    scrollHeight: scrollElement.scrollHeight,
    scrollLeft: scrollElement.scrollLeft,
    scrollTop: scrollElement.scrollTop,
    scrollWidth: scrollElement.scrollWidth,
    zoom,
  };
}

function restoreZoomAnchor(scrollElement: HTMLDivElement, anchor: ZoomAnchor) {
  if (restorePageZoomAnchor(scrollElement, anchor)) {
    return;
  }
  scrollElement.scrollLeft = scaledScrollOffset(
    anchor.scrollLeft,
    anchor.localX,
    anchor.scrollWidth,
    scrollElement.scrollWidth,
  );
  scrollElement.scrollTop = scaledScrollOffset(
    anchor.scrollTop,
    anchor.localY,
    anchor.scrollHeight,
    scrollElement.scrollHeight,
  );
}

function restorePageZoomAnchor(scrollElement: HTMLDivElement, anchor: ZoomAnchor): boolean {
  if (anchor.pageNo === null || anchor.pageXRatio === null || anchor.pageYRatio === null) {
    return false;
  }
  const pageFrame = document.getElementById(pageFrameDomId(anchor.pageNo));
  if (!(pageFrame instanceof HTMLElement)) {
    return false;
  }
  const scrollRect = scrollElement.getBoundingClientRect();
  const pageRect = pageFrame.getBoundingClientRect();
  scrollElement.scrollLeft +=
    pageRect.left + pageRect.width * anchor.pageXRatio - (scrollRect.left + anchor.localX);
  scrollElement.scrollTop +=
    pageRect.top + pageRect.height * anchor.pageYRatio - (scrollRect.top + anchor.localY);
  return true;
}

function scaledScrollOffset(
  currentOffset: number,
  localPointerOffset: number,
  previousSize: number,
  nextSize: number,
): number {
  if (previousSize <= 0 || nextSize <= 0) {
    return currentOffset;
  }
  return ((currentOffset + localPointerOffset) / previousSize) * nextSize - localPointerOffset;
}

function pageFrameAtPoint(clientX: number, clientY: number): HTMLElement | null {
  for (const element of document.elementsFromPoint(clientX, clientY)) {
    if (!(element instanceof HTMLElement)) {
      continue;
    }
    const pageFrame = element.closest<HTMLElement>('[data-preview-page-frame="true"]');
    if (pageFrame) {
      return pageFrame;
    }
  }
  return null;
}

function wheelZoomValue(
  currentZoom: number,
  event: WheelEvent,
  scrollElement: HTMLDivElement,
): number {
  const normalizedDelta = normalizedWheelDelta(event, scrollElement);
  const nextZoom = currentZoom * Math.exp(-normalizedDelta / WHEEL_ZOOM_SENSITIVITY);
  return clampZoom(nextZoom);
}

function normalizedWheelDelta(event: WheelEvent, scrollElement: HTMLDivElement): number {
  if (event.deltaMode === DOM_DELTA_LINE) {
    return event.deltaY * 16;
  }
  if (event.deltaMode === DOM_DELTA_PAGE) {
    return event.deltaY * scrollElement.clientHeight;
  }
  return event.deltaY;
}

function clampZoom(value: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(value * 100) / 100));
}
