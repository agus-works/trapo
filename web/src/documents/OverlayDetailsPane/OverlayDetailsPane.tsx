import { SelectionDetails } from '../../components/workbench';
import type { OverlayBox } from '../../generated/model';
import { compactText } from '../../lib/utils';
import styles from './OverlayDetailsPane.module.css';

export function OverlayDetailsPane({ selectedOverlay }: { selectedOverlay: OverlayBox | null }) {
  if (!selectedOverlay) {
    return <SelectionDetails empty="Select a region overlay." sections={[]} />;
  }

  return (
    <SelectionDetails
      defaultOpenIds={['summary', 'text']}
      empty="Select a region overlay."
      sections={[
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Page</dt>
              <dd>{selectedOverlay.page_no}</dd>
              <dt>Engine</dt>
              <dd>{selectedOverlay.annotation_engine}</dd>
              <dt>Kind</dt>
              <dd>{selectedOverlay.region_kind}</dd>
              <dt>Chunk</dt>
              <dd>{selectedOverlay.chunk_id}</dd>
              <dt>Source</dt>
              <dd>{selectedOverlay.source_ref ?? 'chunk'}</dd>
              <dt>Label</dt>
              <dd>{selectedOverlay.label ?? 'none'}</dd>
              <dt>Hidden</dt>
              <dd>{selectedOverlay.hidden ? 'yes' : 'no'}</dd>
            </dl>
          ),
          id: 'summary',
          title: 'Overlay',
        },
        {
          content: (
            <p className={styles.detailTextBlock}>{selectedOverlay.text_preview || 'none'}</p>
          ),
          id: 'text',
          title: 'Text',
        },
        {
          content: <pre className={styles.rawJson}>{JSON.stringify(selectedOverlay, null, 2)}</pre>,
          id: 'raw',
          title: 'Raw JSON',
        },
      ]}
      title={compactText(selectedOverlay.text_preview || selectedOverlay.overlay_id, 80)}
    />
  );
}
