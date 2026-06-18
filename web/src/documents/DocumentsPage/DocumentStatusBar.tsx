import { WorkbenchStatusBar } from '../../components/workbench';
import { shortHash } from '../../lib/utils';
import type { DocumentsPageView } from './types';

export function DocumentStatusBar({ view }: { view: DocumentsPageView }) {
  return (
    <WorkbenchStatusBar
      items={[
        { label: 'chunks', value: view.activeDocument?.chunk_count ?? 0 },
        { label: 'regions', value: view.activeDocument?.region_count ?? 0 },
        { label: 'boxes', value: view.regions?.overlays.length ?? 0 },
        { label: 'page', value: view.activePageNo },
        { label: 'file', value: view.activeHash ? shortHash(view.activeHash) : 'none' },
      ]}
    />
  );
}
