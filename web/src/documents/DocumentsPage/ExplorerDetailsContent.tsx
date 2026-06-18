import { SelectionDetails } from '../../components/workbench';
import type {
  DocumentRegionsPayload,
  DocumentSummary,
  OverlayBox,
  PageInfo,
} from '../../generated/model';
import { compactText, shortHash } from '../../lib/utils';
import styles from './ExplorerDetailsPane.module.css';
import type { AggregateStats } from './ExplorerDetailsStats';
import { regionsForFile } from './ExplorerDetailsStats';

export function DocumentDetails({
  document,
  regions,
}: {
  document: DocumentSummary | null;
  regions: DocumentRegionsPayload | null;
}) {
  if (!document) {
    return <SelectionDetails empty="Document metadata is not available." sections={[]} />;
  }
  const detail = regionsForFile(regions, document.file_hash);
  const pages = detail?.document.pages ?? [];

  return (
    <SelectionDetails
      defaultOpenIds={['summary', 'path']}
      empty="Select a file."
      sections={[
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Type</dt>
              <dd>{document.extension ?? 'unknown'}</dd>
              <dt>Size</dt>
              <dd>{formatBytesWithRaw(document.size_bytes)}</dd>
              <dt>OCR</dt>
              <dd>{ocrStatus(document)}</dd>
              {document.docling_error && (
                <>
                  <dt>Docling error</dt>
                  <dd>{compactText(document.docling_error, 240)}</dd>
                </>
              )}
              {document.mineru_error && (
                <>
                  <dt>MinerU error</dt>
                  <dd>{compactText(document.mineru_error, 240)}</dd>
                </>
              )}
              <dt>Pages</dt>
              <dd>{pages.length > 0 ? pages.length.toLocaleString() : 'pending'}</dd>
              <dt>Chunks</dt>
              <dd>{(document.chunk_count ?? 0).toLocaleString()}</dd>
              <dt>Regions</dt>
              <dd>{(document.region_count ?? 0).toLocaleString()}</dd>
            </dl>
          ),
          id: 'summary',
          title: 'File',
        },
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Filename</dt>
              <dd>{document.filename}</dd>
              <dt>Path</dt>
              <dd>{document.path ?? 'unknown'}</dd>
              <dt>Hash</dt>
              <dd>{document.file_hash}</dd>
            </dl>
          ),
          id: 'path',
          title: 'Location',
        },
        {
          content: (
            <pre className={styles.rawJson}>{JSON.stringify({ ...document, pages }, null, 2)}</pre>
          ),
          id: 'raw',
          title: 'Raw JSON',
        },
      ]}
      title={compactText(document.filename, 80)}
    />
  );
}

export function PageDetails({
  document,
  page,
  pageNo,
  overlays,
}: {
  document: DocumentSummary | null;
  page: PageInfo | null;
  pageNo: number;
  overlays: OverlayBox[];
}) {
  const averageArea =
    overlays.length > 0
      ? overlays.reduce(
          (sum, overlay) => sum + overlay.bbox.width_pct * overlay.bbox.height_pct,
          0,
        ) /
        overlays.length /
        100
      : 0;

  return (
    <SelectionDetails
      defaultOpenIds={['summary', 'regions']}
      empty="Select a page."
      sections={[
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Document</dt>
              <dd>{document?.filename ?? 'unknown'}</dd>
              <dt>Page</dt>
              <dd>{pageNo.toLocaleString()}</dd>
              <dt>Dimensions</dt>
              <dd>{page ? `${page.width} x ${page.height}` : 'pending'}</dd>
              <dt>Regions</dt>
              <dd>{overlays.length.toLocaleString()}</dd>
            </dl>
          ),
          id: 'summary',
          title: 'Page',
        },
        {
          content: (
            <dl className={styles.detailList}>
              <dt>Avg. box area</dt>
              <dd>{averageArea > 0 ? `${averageArea.toFixed(2)}%` : 'none'}</dd>
              <dt>Labels</dt>
              <dd>{labelSummary(overlays)}</dd>
              <dt>Largest</dt>
              <dd>{largestOverlayLabel(overlays)}</dd>
            </dl>
          ),
          id: 'regions',
          title: 'Regions',
        },
        {
          content: (
            <pre className={styles.rawJson}>{JSON.stringify({ page, overlays }, null, 2)}</pre>
          ),
          id: 'raw',
          title: 'Raw JSON',
        },
      ]}
      title={`${document ? compactText(document.filename, 56) : 'Document'} / Page ${pageNo}`}
    />
  );
}

export function AggregateStatsList({ stats }: { stats: AggregateStats }) {
  return (
    <dl className={styles.detailList}>
      <dt>Total size</dt>
      <dd>{formatBytesWithRaw(stats.sizeBytes)}</dd>
      <dt>Chunks</dt>
      <dd>{stats.chunks.toLocaleString()}</dd>
      <dt>Regions</dt>
      <dd>{stats.regions.toLocaleString()}</dd>
      <dt>OCR ready</dt>
      <dd>{stats.ocrReady.toLocaleString()}</dd>
      <dt>Extensions</dt>
      <dd>{stats.extensions}</dd>
    </dl>
  );
}

function ocrStatus(document: DocumentSummary): string {
  return `Docling ${document.docling_status ?? 'unknown'} / MinerU ${
    document.mineru_status ?? 'unknown'
  }`;
}

function labelSummary(overlays: OverlayBox[]): string {
  if (overlays.length === 0) {
    return 'none';
  }
  const counts = new Map<string, number>();
  for (const overlay of overlays) {
    const label = overlay.label ?? 'unlabeled';
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([label, count]) => `${label} ${count}`)
    .join(', ');
}

function largestOverlayLabel(overlays: OverlayBox[]): string {
  const largest = overlays.reduce<OverlayBox | null>((current, overlay) => {
    if (!current) {
      return overlay;
    }
    const currentArea = current.bbox.width_pct * current.bbox.height_pct;
    const nextArea = overlay.bbox.width_pct * overlay.bbox.height_pct;
    return nextArea > currentArea ? overlay : current;
  }, null);
  return largest ? `${largest.label ?? 'region'} (${shortHash(largest.overlay_id, 16)})` : 'none';
}

function formatBytesWithRaw(bytes: number): string {
  return `${formatBytes(bytes)} (${bytes.toLocaleString()} bytes)`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}
