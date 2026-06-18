import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RotateCcw,
  RotateCw,
  Scan,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import type { MarkdownEngineRecord } from '../../generated/model';
import type { AnnotationEngineVisibility } from '../annotationVisibility';
import type { DocumentViewMode, OverlayMode, PreviewRotation } from '../types';
import styles from './PdfPreviewToolbar.module.css';
import {
  clampPage,
  engineColor,
  engineLabel,
  markdownEngineLabel,
  rotated,
} from './toolbarHelpers';

const ZOOM_STEP = 0.25;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;

export function PdfPreviewToolbar({
  annotationEngines,
  currentPage,
  engineVisibility,
  markdownEngine,
  markdownEngines,
  numPages,
  overlayMode,
  previewRotation,
  previewZoom,
  viewMode,
  onEngineVisibilityChange,
  onMarkdownEngineChange,
  onPageChange,
  onOverlayModeChange,
  onPreviewRotationChange,
  onPreviewTransformReset,
  onPreviewZoomChange,
  onViewModeChange,
}: {
  annotationEngines: string[];
  currentPage: number;
  engineVisibility: AnnotationEngineVisibility;
  markdownEngine: string;
  markdownEngines: MarkdownEngineRecord[];
  numPages: number;
  overlayMode: OverlayMode;
  previewRotation: PreviewRotation;
  previewZoom: number;
  viewMode: DocumentViewMode;
  onEngineVisibilityChange: (engine: string, visible: boolean) => void;
  onMarkdownEngineChange: (engine: string) => void;
  onPageChange: (pageNo: number) => void;
  onOverlayModeChange: (mode: OverlayMode) => void;
  onPreviewRotationChange: (rotation: PreviewRotation) => void;
  onPreviewTransformReset: () => void;
  onPreviewZoomChange: (zoom: number) => void;
  onViewModeChange: (mode: DocumentViewMode) => void;
}) {
  const [pageText, setPageText] = useState(String(currentPage));
  const lastPage = Math.max(numPages, 1);
  const zoomPercent = Math.round(previewZoom * 100);
  useEffect(() => {
    setPageText(String(currentPage));
  }, [currentPage]);
  const commitPage = () => {
    const pageNo = clampPage(Number(pageText), numPages);
    setPageText(String(pageNo));
    onPageChange(pageNo);
  };
  return (
    <div className={styles.toolbar}>
      <div className={styles.pageStepper}>
        <button
          aria-label="First page"
          className={styles.iconButton}
          disabled={currentPage <= 1}
          onClick={() => onPageChange(1)}
          title="First page"
          type="button"
        >
          <ChevronsLeft size={14} />
        </button>
        <button
          aria-label="Previous page"
          className={styles.iconButton}
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
          title="Previous page"
          type="button"
        >
          <ChevronLeft size={14} />
        </button>
        <label className={styles.pageInputLabel}>
          <span>Page</span>
          <input
            inputMode="numeric"
            max={lastPage}
            min={1}
            onBlur={commitPage}
            onChange={(event) => setPageText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.currentTarget.blur();
              }
            }}
            type="number"
            value={pageText}
          />
          <span className={styles.pageTotal}>/ {lastPage}</span>
        </label>
        <button
          aria-label="Next page"
          className={styles.iconButton}
          disabled={currentPage >= lastPage}
          onClick={() => onPageChange(currentPage + 1)}
          title="Next page"
          type="button"
        >
          <ChevronRight size={14} />
        </button>
        <button
          aria-label="Last page"
          className={styles.iconButton}
          disabled={currentPage >= lastPage}
          onClick={() => onPageChange(lastPage)}
          title="Last page"
          type="button"
        >
          <ChevronsRight size={14} />
        </button>
      </div>
      <div className={styles.toolGroup}>
        <button
          aria-label="Zoom out"
          className={styles.iconButton}
          disabled={previewZoom <= MIN_ZOOM}
          onClick={() => onPreviewZoomChange(previewZoom - ZOOM_STEP)}
          title="Zoom out"
          type="button"
        >
          <ZoomOut size={14} />
        </button>
        <span className={styles.valuePill}>{zoomPercent}%</span>
        <button
          aria-label="Zoom in"
          className={styles.iconButton}
          disabled={previewZoom >= MAX_ZOOM}
          onClick={() => onPreviewZoomChange(previewZoom + ZOOM_STEP)}
          title="Zoom in"
          type="button"
        >
          <ZoomIn size={14} />
        </button>
        <button
          aria-label="Rotate counterclockwise"
          className={styles.iconButton}
          onClick={() => onPreviewRotationChange(rotated(previewRotation, -90))}
          title="Rotate counterclockwise"
          type="button"
        >
          <RotateCcw size={14} />
        </button>
        <span className={styles.valuePill}>{previewRotation}deg</span>
        <button
          aria-label="Rotate clockwise"
          className={styles.iconButton}
          onClick={() => onPreviewRotationChange(rotated(previewRotation, 90))}
          title="Rotate clockwise"
          type="button"
        >
          <RotateCw size={14} />
        </button>
        <button
          aria-label="Reset preview"
          className={styles.iconButton}
          onClick={onPreviewTransformReset}
          title="Reset preview"
          type="button"
        >
          <Scan size={14} />
        </button>
      </div>
      <details className={styles.optionsMenu}>
        <summary>View</summary>
        <div className={styles.optionsPanel}>
          <label>
            <span>Mode</span>
            <select
              aria-label="Preview mode"
              onChange={(event) => onViewModeChange(event.target.value as DocumentViewMode)}
              value={viewMode}
            >
              <option value="split">Split</option>
              <option value="preview">Preview only</option>
              <option value="markdown">Markdown only</option>
            </select>
          </label>
          <label>
            <span>Overlays</span>
            <select
              aria-label="Overlay mode"
              onChange={(event) => onOverlayModeChange(event.target.value as OverlayMode)}
              value={overlayMode}
            >
              <option value="all">All overlays</option>
              <option value="selected">Focused overlay</option>
              <option value="hidden">Hide overlays</option>
            </select>
          </label>
          <label>
            <span>Markdown</span>
            <select
              aria-label="Markdown generator"
              onChange={(event) => onMarkdownEngineChange(event.target.value)}
              value={markdownEngine}
            >
              {markdownEngines.map((engine) => (
                <option key={engine.markdown_engine} value={engine.markdown_engine}>
                  {markdownEngineLabel(engine)}
                </option>
              ))}
            </select>
          </label>
          {annotationEngines.length > 0 && (
            <div className={styles.optionGroup}>
              <div className={styles.optionGroupTitle}>Engines</div>
              {annotationEngines.map((engine) => {
                const checked = engineVisibility[engine] ?? true;
                return (
                  <label className={styles.checkboxRow} key={engine}>
                    <input
                      checked={checked}
                      onChange={(event) => onEngineVisibilityChange(engine, event.target.checked)}
                      type="checkbox"
                    />
                    <span
                      className={styles.engineSwatch}
                      style={{ background: engineColor(engine) }}
                    />
                    <span>{engineLabel(engine)}</span>
                  </label>
                );
              })}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
