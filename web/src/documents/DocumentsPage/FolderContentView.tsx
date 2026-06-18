import { ArrowDownAZ, ArrowUpAZ, Grid2X2, List } from 'lucide-react';
import type { CSSProperties } from 'react';
import { Button } from '../../components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../../components/ui/table';
import type { DocumentSummary } from '../../generated/model';
import { cn } from '../../lib/utils';
import { trapoApi } from '../../services/trapoApi';
import { isDocumentPreviewSupported } from '../previewSupport';
import type { ExplorerSortBy, ExplorerTileSize } from '../types';
import styles from './FolderContentView.module.css';
import {
  documentsForSelection,
  fileIcon,
  fileTypeLabel,
  formatBytes,
  formatDateTime,
  ocrStatus,
  oppositeDirection,
  sortedDocuments,
} from './folderContentHelpers';
import type { DocumentsPageView } from './types';

const tilePixels = {
  small: 72,
  medium: 112,
  large: 156,
  xlarge: 220,
};

const thumbnailVariant = {
  small: 'thumb_sm',
  medium: 'thumb_md',
  large: 'thumb_lg',
  xlarge: 'thumb_xl',
};

export function FolderContentView({ view }: { view: DocumentsPageView }) {
  const documents = sortedDocuments(
    documentsForSelection(view.documents, view.explorerSelection),
    view.explorerSortBy,
    view.explorerSortDir,
  );
  const title =
    view.explorerSelection.kind === 'directory' ? view.explorerSelection.label : 'Documents';

  return (
    <div className={styles.folderView}>
      <FolderToolbar documentCount={documents.length} title={title} view={view} />
      {view.explorerViewMode === 'details' ? (
        <DetailsGrid documents={documents} view={view} />
      ) : (
        <TileGrid documents={documents} view={view} />
      )}
    </div>
  );
}

function FolderToolbar({
  documentCount,
  title,
  view,
}: {
  documentCount: number;
  title: string;
  view: DocumentsPageView;
}) {
  const directionIcon =
    view.explorerSortDir === 'asc' ? <ArrowUpAZ size={15} /> : <ArrowDownAZ size={15} />;
  return (
    <div className={styles.folderToolbar}>
      <div className={styles.folderTitle}>
        <strong>{title}</strong>
        <span>{documentCount.toLocaleString()} files</span>
      </div>
      <div className={styles.folderControls}>
        <Button
          aria-label="Tile view"
          className={cn(view.explorerViewMode === 'tiles' && styles.activeButton)}
          onClick={() => view.onExplorerViewModeChange('tiles')}
          size="icon"
          variant="ghost"
        >
          <Grid2X2 size={15} />
        </Button>
        <Button
          aria-label="Details view"
          className={cn(view.explorerViewMode === 'details' && styles.activeButton)}
          onClick={() => view.onExplorerViewModeChange('details')}
          size="icon"
          variant="ghost"
        >
          <List size={15} />
        </Button>
        <select
          aria-label="Tile size"
          disabled={view.explorerViewMode !== 'tiles'}
          onChange={(event) =>
            view.onExplorerTileSizeChange(event.target.value as ExplorerTileSize)
          }
          value={view.explorerTileSize}
        >
          <option value="small">Small</option>
          <option value="medium">Medium</option>
          <option value="large">Large</option>
          <option value="xlarge">Extra large</option>
        </select>
        <select
          aria-label="Sort files"
          onChange={(event) =>
            view.onExplorerSortChange(event.target.value as ExplorerSortBy, view.explorerSortDir)
          }
          value={view.explorerSortBy}
        >
          <option value="name">Name</option>
          <option value="type">Type</option>
          <option value="size">Size</option>
          <option value="status">OCR status</option>
          <option value="modified">Date modified</option>
          <option value="created">Date created</option>
        </select>
        <Button
          aria-label="Reverse sort direction"
          onClick={() =>
            view.onExplorerSortChange(view.explorerSortBy, oppositeDirection(view.explorerSortDir))
          }
          size="icon"
          variant="ghost"
        >
          {directionIcon}
        </Button>
      </div>
    </div>
  );
}

function TileGrid({ documents, view }: { documents: DocumentSummary[]; view: DocumentsPageView }) {
  const tileSize = tilePixels[view.explorerTileSize];
  const style = { '--tile-size': `${tileSize}px` } as CSSProperties;
  return (
    <div className={styles.tileGrid} style={style}>
      {documents.map((document) => (
        <button
          className={cn(
            styles.fileTile,
            document.file_hash === view.activeHash && styles.selectedTile,
          )}
          key={document.file_hash}
          onClick={() => view.onDocumentSelect(document.file_hash)}
          type="button"
        >
          <Thumbnail document={document} size={view.explorerTileSize} />
          <span className={styles.tileName}>{document.filename}</span>
          <span className={styles.tileMeta}>
            {fileTypeLabel(document)} · {formatBytes(document.size_bytes)}
          </span>
        </button>
      ))}
    </div>
  );
}

function DetailsGrid({
  documents,
  view,
}: {
  documents: DocumentSummary[];
  view: DocumentsPageView;
}) {
  return (
    <div className={styles.detailsGrid}>
      <Table>
        <TableHeader>
          <TableRow>
            <SortableHead label="Name" sortBy="name" view={view} />
            <SortableHead label="Date modified" sortBy="modified" view={view} />
            <SortableHead label="Date created" sortBy="created" view={view} />
            <SortableHead label="Type" sortBy="type" view={view} />
            <SortableHead label="Size" sortBy="size" view={view} />
            <SortableHead label="OCR" sortBy="status" view={view} />
            <TableHead>Chunks</TableHead>
            <TableHead>Regions</TableHead>
            <TableHead>Path</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((document) => (
            <TableRow
              className={document.file_hash === view.activeHash ? styles.selectedRow : undefined}
              key={document.file_hash}
              onClick={() => view.onDocumentSelect(document.file_hash)}
            >
              <TableCell>
                <span className={styles.nameCell}>
                  {fileIcon(document, 15)}
                  {document.filename}
                </span>
              </TableCell>
              <TableCell className={styles.dateCell}>
                {formatDateTime(document.modified_at)}
              </TableCell>
              <TableCell className={styles.dateCell}>
                {formatDateTime(document.created_at)}
              </TableCell>
              <TableCell>{fileTypeLabel(document)}</TableCell>
              <TableCell>{formatBytes(document.size_bytes)}</TableCell>
              <TableCell>{ocrStatus(document)}</TableCell>
              <TableCell>{(document.chunk_count ?? 0).toLocaleString()}</TableCell>
              <TableCell>{(document.region_count ?? 0).toLocaleString()}</TableCell>
              <TableCell className={styles.pathCell}>{document.path ?? ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function SortableHead({
  label,
  sortBy,
  view,
}: {
  label: string;
  sortBy: ExplorerSortBy;
  view: DocumentsPageView;
}) {
  const active = view.explorerSortBy === sortBy;
  const nextDirection = active ? oppositeDirection(view.explorerSortDir) : 'asc';
  return (
    <TableHead>
      <button
        className={styles.sortHeader}
        onClick={() => view.onExplorerSortChange(sortBy, nextDirection)}
        type="button"
      >
        {label}
        {active ? (view.explorerSortDir === 'asc' ? ' ↑' : ' ↓') : ''}
      </button>
    </TableHead>
  );
}

function Thumbnail({
  document,
  size,
}: {
  document: DocumentSummary;
  size: keyof typeof thumbnailVariant;
}) {
  const supported = isDocumentPreviewSupported(document);
  return (
    <span className={styles.thumbnail}>
      <span className={styles.thumbnailIcon}>{fileIcon(document, 34)}</span>
      {supported && (
        <img
          alt=""
          loading="lazy"
          src={trapoApi.documentPreviewImageUrl(document.file_hash, thumbnailVariant[size])}
        />
      )}
    </span>
  );
}
