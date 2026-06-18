import { SelectionDetails } from '../../components/workbench';
import type { DocumentRegionsPayload, DocumentSummary } from '../../generated/model';
import { OverlayDetailsPane } from '../OverlayDetailsPane';
import type { ExplorerSelection } from '../types';
import { AggregateStatsList, DocumentDetails, PageDetails } from './ExplorerDetailsContent';
import styles from './ExplorerDetailsPane.module.css';
import { aggregateStats, documentsForDirectory, regionsForFile } from './ExplorerDetailsStats';

interface ExplorerDetailsPaneProps {
  selection: ExplorerSelection;
  documents: DocumentSummary[];
  regions: DocumentRegionsPayload | null;
}

export function ExplorerDetailsPane({ selection, documents, regions }: ExplorerDetailsPaneProps) {
  if (selection.kind === 'overlay') {
    return <OverlayDetailsPane selectedOverlay={selection.overlay} />;
  }

  if (selection.kind === 'document') {
    const document = documents.find((item) => item.file_hash === selection.fileHash) ?? null;
    return <DocumentDetails document={document} regions={regions} />;
  }

  if (selection.kind === 'diagnostics') {
    const document = documents.find((item) => item.file_hash === selection.fileHash) ?? null;
    return <DiagnosticsSelectionDetails document={document} selection={selection} />;
  }

  if (selection.kind === 'page') {
    const document = documents.find((item) => item.file_hash === selection.fileHash) ?? null;
    const detail = regionsForFile(regions, selection.fileHash);
    const page = detail?.document.pages?.find((item) => item.page_no === selection.pageNo);
    const overlays = detail?.overlays ?? [];

    return (
      <PageDetails
        document={document}
        overlays={overlays.filter((overlay) => overlay.page_no === selection.pageNo)}
        page={page ?? null}
        pageNo={selection.pageNo}
      />
    );
  }

  const scopeDocuments =
    selection.kind === 'directory'
      ? documentsForDirectory(documents, selection.pathKey)
      : documents;
  const stats = aggregateStats(documents, scopeDocuments, selection);

  return (
    <SelectionDetails
      defaultOpenIds={['summary', 'stats']}
      empty="Select a file, folder, page, or region."
      sections={[
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Scope</dt>
              <dd>{selection.kind === 'directory' ? 'Folder' : 'Workspace root'}</dd>
              <dt>Path</dt>
              <dd>{selection.kind === 'directory' ? selection.pathKey : 'Documents'}</dd>
              <dt>Files</dt>
              <dd>{stats.files.toLocaleString()}</dd>
              <dt>Folders</dt>
              <dd>{stats.folders.toLocaleString()}</dd>
            </dl>
          ),
          id: 'summary',
          title: 'Selection',
        },
        {
          content: <AggregateStatsList stats={stats} />,
          id: 'stats',
          title: 'Statistics',
        },
      ]}
      title={selection.kind === 'directory' ? selection.label : 'Documents'}
    />
  );
}

function DiagnosticsSelectionDetails({
  document,
  selection,
}: {
  document: DocumentSummary | null;
  selection: Extract<ExplorerSelection, { kind: 'diagnostics' }>;
}) {
  return (
    <SelectionDetails
      defaultOpenIds={['summary']}
      empty="Select a diagnostics node."
      sections={[
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Document</dt>
              <dd>{document?.filename ?? 'unknown'}</dd>
              <dt>Scope</dt>
              <dd>{selection.pageNo ? `Page ${selection.pageNo}` : 'File pipeline'}</dd>
              <dt>Hash</dt>
              <dd>{selection.fileHash}</dd>
            </dl>
          ),
          id: 'summary',
          title: 'Diagnostics',
        },
      ]}
      title={selection.pageNo ? `Page ${selection.pageNo} diagnostics` : 'Pipeline diagnostics'}
    />
  );
}
