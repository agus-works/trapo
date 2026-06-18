import type { VirtualItem } from '@tanstack/react-virtual';
import type {
  DocumentRegionsPayload,
  DocumentSummary,
  OverlayBox,
  PageInfo,
} from '../../generated/model';
import { trapoApi } from '../../services/trapoApi';
import type { PreviewRotation } from '../types';
import { OverlayLayer } from './OverlayLayer';
import styles from './PdfDocumentPreview.module.css';
import { pageMetrics } from './pageMetrics';
import { pageFrameDomId, pageHeaderDomId } from './previewDom';

export function VirtualPage({
  activeOverlay,
  activePageNo,
  document,
  onOverlaySelect,
  onRenderError,
  page,
  previewRotation,
  previewZoom,
  regions,
  virtualItem,
  visibleOverlayIds,
}: {
  activeOverlay: OverlayBox | null;
  activePageNo: number;
  document: DocumentSummary;
  onOverlaySelect: (overlay: OverlayBox) => void;
  onRenderError: (error: string | null) => void;
  page: PageInfo;
  previewRotation: PreviewRotation;
  previewZoom: number;
  regions: DocumentRegionsPayload;
  virtualItem: VirtualItem;
  visibleOverlayIds: Set<string>;
}) {
  const metrics = pageMetrics(page, previewRotation, previewZoom);
  return (
    <div
      className={styles.virtualPageRow}
      style={{
        height: `${virtualItem.size}px`,
        transform: `translateY(${virtualItem.start}px)`,
      }}
    >
      <div className={styles.pageWrap} data-active={page.page_no === activePageNo}>
        <div className={styles.pageHeader} id={pageHeaderDomId(page.page_no)}>
          Page {page.page_no}
        </div>
        <div
          className={styles.pageFrame}
          data-page-no={page.page_no}
          data-preview-page-frame="true"
          id={pageFrameDomId(page.page_no)}
          style={{ height: `${metrics.frameHeight}px`, width: `${metrics.frameWidth}px` }}
        >
          <div
            className={styles.pageSurface}
            style={{
              height: `${metrics.surfaceHeight}px`,
              transform: `translate(-50%, -50%) rotate(${previewRotation}deg)`,
              width: `${metrics.surfaceWidth}px`,
            }}
          >
            <img
              alt={`${document.filename} page ${page.page_no}`}
              className={styles.documentPreviewImage}
              onError={() =>
                onRenderError(`Failed to load cached preview for page ${page.page_no}.`)
              }
              onLoad={() => onRenderError(null)}
              src={trapoApi.documentPreviewImageUrl(document.file_hash, 'normalized', page.page_no)}
            />
            <OverlayLayer
              activeOverlay={activeOverlay}
              onSelect={onOverlaySelect}
              overlays={regions.overlays}
              pageNo={page.page_no}
              visibleOverlayIds={visibleOverlayIds}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
