import type { OverlayBox } from '../../generated/model';

export function overlayDomId(overlay: OverlayBox): string {
  return `overlay-${overlay.overlay_id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
}

export function pageHeaderDomId(pageNo: number): string {
  return `pdf-page-${pageNo}`;
}

export function pageFrameDomId(pageNo: number): string {
  return `pdf-page-frame-${pageNo}`;
}
