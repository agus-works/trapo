import type { ColumnDef } from '@tanstack/react-table';
import { Activity, FileText, Folder, Settings } from 'lucide-react';
import type { TreeGridNode, TreeNode, WorkbenchTab } from '../../components/workbench/types';
import type { DocumentSummary, MarkdownEngineRecord, OverlayBox } from '../../generated/model';

export const anonymizedFileHash = 'anon-file-0001';

export const anonymizedDocuments: DocumentSummary[] = [
  {
    chunk_count: 42,
    created_at: '2026-01-02T10:00:00Z',
    docling_status: 'ok',
    extension: '.pdf',
    file_hash: anonymizedFileHash,
    filename: 'sample-research-brief.pdf',
    fusion_status: 'ok',
    lmstudio_status: 'error',
    mineru_status: 'ok',
    modified_at: '2026-01-03T15:30:00Z',
    path: 'C:\\Sample\\Corpus\\sample-research-brief.pdf',
    region_count: 318,
    size_bytes: 2842210,
  },
  {
    chunk_count: 18,
    created_at: '2026-01-04T09:00:00Z',
    docling_status: 'ok',
    extension: '.png',
    file_hash: 'anon-file-0002',
    filename: 'invoice-example.png',
    fusion_status: 'ok',
    mineru_status: 'ok',
    modified_at: '2026-01-04T09:10:00Z',
    path: 'C:\\Sample\\Corpus\\invoice-example.png',
    region_count: 79,
    size_bytes: 824112,
  },
];

export const mockOverlay: OverlayBox = {
  annotation_engine: 'fusion',
  annotation_model: 'trapo-region-fusion-v1',
  annotation_provider: 'local-fusion',
  bbox: { height_pct: 10.4, left_pct: 18.2, top_pct: 22.6, width_pct: 54.8 },
  chunk_id: 104,
  chunk_index: 7,
  file_hash: anonymizedFileHash,
  hidden: false,
  label: 'paragraph',
  overlay_id: 'region:anon-region-0001',
  page_no: 2,
  raw_bbox: { bottom: 676, coord_origin: 'BOTTOMLEFT', left: 112, right: 488, top: 598 },
  region_kind: 'text',
  source_ref: 'docling:r-17 + mineru:r-22',
  style: {
    fill_color: '#3994bc',
    fill_opacity: 0.14,
    stroke_color: '#3994bc',
    stroke_opacity: 0.82,
    stroke_width: 2,
  },
  text_preview: 'An anonymized paragraph extracted from a sample document page.',
};

export const markdownEngines: MarkdownEngineRecord[] = [
  {
    is_virtual: true,
    label: 'Best available',
    markdown_engine: 'best_available_markdown',
    page_count: 12,
    status: 'ok',
  },
  {
    label: 'LM Studio',
    markdown_engine: 'lmstudio_markdown',
    markdown_model: 'example-vision-model',
    markdown_provider: 'local-lmstudio',
    page_count: 3,
    status: 'error',
  },
  {
    label: 'MarkItDown',
    markdown_engine: 'markitdown',
    markdown_model: 'markitdown-ocr',
    markdown_provider: 'local-markitdown',
    page_count: 12,
    status: 'ok',
  },
];

export const treeNodes: TreeNode[] = [
  {
    badge: '2 files',
    children: [
      {
        badge: 'ok',
        children: [
          { icon: <Activity size={14} />, id: 'diag:file', label: 'Pipeline diagnostics' },
          { badge: '3 regions', icon: <FileText size={14} />, id: 'page:1', label: 'Page 1' },
        ],
        icon: <FileText size={14} />,
        id: 'file:1',
        label: 'sample-research-brief.pdf',
        selected: true,
      },
    ],
    icon: <Folder size={14} />,
    id: 'folder:sample',
    label: 'Sample Corpus',
  },
];

export const treeGridNodes: TreeGridNode[] = [
  {
    badge: 'visible',
    checked: true,
    children: [
      { badge: '318', checked: true, id: 'engine:fusion', label: 'Fusion overlays' },
      { badge: '142', checked: 'indeterminate', id: 'engine:docling', label: 'Docling overlays' },
    ],
    id: 'overlays',
    label: 'Annotation overlays',
  },
];

export const workbenchTabs: WorkbenchTab[] = [
  { icon: <FileText size={13} />, id: 'preview', label: 'Preview' },
  { icon: <Activity size={13} />, id: 'diagnostics', label: 'Diagnostics' },
  { icon: <Settings size={13} />, id: 'settings', label: 'Settings' },
];

export interface ExampleRow {
  id: string;
  name: string;
  engine: string;
  status: string;
  duration: string;
}

export const tableRows: ExampleRow[] = [
  { duration: '37.7s', engine: 'Docling', id: 'r1', name: 'Read source', status: 'ok' },
  { duration: '9.1s', engine: 'Preview', id: 'r2', name: 'Render pages', status: 'ok' },
  { duration: '61.0s', engine: 'LM Studio', id: 'r3', name: 'Page Markdown', status: 'error' },
];

export const tableColumns: Array<ColumnDef<ExampleRow>> = [
  { accessorKey: 'name', header: 'Step' },
  { accessorKey: 'engine', header: 'Engine' },
  { accessorKey: 'status', header: 'Status' },
  { accessorKey: 'duration', header: 'Duration' },
];
