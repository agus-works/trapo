import type { OverlayBox } from '../../generated/model';
import { cn } from '../../lib/utils';
import styles from './PdfDocumentPreview.module.css';
import { overlayDomId } from './previewDom';

export function OverlayLayer({
  overlays,
  pageNo,
  activeOverlay,
  visibleOverlayIds,
  onSelect,
}: {
  overlays: OverlayBox[];
  pageNo: number;
  activeOverlay: OverlayBox | null;
  visibleOverlayIds: Set<string>;
  onSelect: (overlay: OverlayBox) => void;
}) {
  const pageOverlays = overlays.filter(
    (overlay) => overlay.page_no === pageNo && visibleOverlayIds.has(overlay.overlay_id),
  );

  return (
    <div className={styles.overlayLayer}>
      {pageOverlays.map((overlay) => {
        const active = overlay.overlay_id === activeOverlay?.overlay_id;
        return (
          <button
            aria-label={`${overlay.label ?? 'region'} on page ${overlay.page_no}`}
            className={cn(styles.overlayBox, active && styles.overlayBoxActive)}
            id={overlayDomId(overlay)}
            key={overlay.overlay_id}
            onClick={() => onSelect(overlay)}
            style={{
              backgroundColor: rgba(overlay.style.fill_color, overlay.style.fill_opacity ?? 0.14),
              borderColor: rgba(overlay.style.stroke_color, overlay.style.stroke_opacity ?? 0.82),
              borderWidth: `${overlay.style.stroke_width ?? 2}px`,
              height: `${Math.max(overlay.bbox.height_pct, 0.4)}%`,
              left: `${overlay.bbox.left_pct}%`,
              top: `${overlay.bbox.top_pct}%`,
              width: `${overlay.bbox.width_pct}%`,
            }}
            title={overlay.text_preview || overlay.label || `chunk ${overlay.chunk_id}`}
            type="button"
          />
        );
      })}
    </div>
  );
}

function rgba(hexColor: string, opacity: number): string {
  const normalized = hexColor.trim().replace(/^#/, '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `rgb(213 83 68 / ${Math.round(opacity * 100)}%)`;
  }
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgb(${red} ${green} ${blue} / ${Math.round(opacity * 100)}%)`;
}
