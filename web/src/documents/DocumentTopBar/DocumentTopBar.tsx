import { PanelLeft, PanelRight } from 'lucide-react';
import type { ReactNode } from 'react';
import type { ImperativePanelHandle } from '../../components/ui/resizable';
import styles from './DocumentTopBar.module.css';

export function DocumentTopBar({
  activeDocumentPath,
  error,
  filename,
  leftCollapsed,
  leftPanel,
  loading,
  previewError,
  previewLoading,
  rightCollapsed,
  rightPanel,
}: {
  activeDocumentPath: string | null;
  error: string | null;
  filename: string | null;
  leftCollapsed: boolean;
  leftPanel: ImperativePanelHandle | null;
  loading: boolean;
  previewError: string | null;
  previewLoading: boolean;
  rightCollapsed: boolean;
  rightPanel: ImperativePanelHandle | null;
}) {
  return (
    <div className={styles.topBar}>
      <div className={styles.topTitle}>
        <h2>{filename ?? 'No document'}</h2>
        <p>{activeDocumentPath ?? 'Open a Trapo DuckDB file with ingested documents.'}</p>
      </div>
      <div className={styles.topStatus}>
        {loading && <span className={styles.statusPill}>Loading</span>}
        {previewLoading && <span className={styles.statusPill}>Loading preview</span>}
        {error && <span className={styles.errorPill}>{error}</span>}
        {previewError && <span className={styles.errorPill}>{previewError}</span>}
        <span className={styles.topActions}>
          <PanelToggleButton
            collapsed={leftCollapsed}
            icon={<PanelLeft size={16} />}
            label="Toggle explorer"
            panel={leftPanel}
          />
          <PanelToggleButton
            collapsed={rightCollapsed}
            icon={<PanelRight size={16} />}
            label="Toggle details"
            panel={rightPanel}
          />
        </span>
      </div>
    </div>
  );
}

export function PanelToggleButton({
  collapsed,
  icon,
  label,
  panel,
}: {
  collapsed: boolean;
  icon: ReactNode;
  label: string;
  panel: ImperativePanelHandle | null;
}) {
  return (
    <button
      aria-label={label}
      onClick={() => togglePanel(panel, collapsed)}
      title={label}
      type="button"
    >
      {icon}
    </button>
  );
}

function togglePanel(panel: ImperativePanelHandle | null, collapsed: boolean) {
  if (!panel) {
    return;
  }
  if (collapsed) {
    panel.expand();
  } else {
    panel.collapse();
  }
}
