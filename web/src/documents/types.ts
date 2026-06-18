import type { OverlayBox } from '../generated/model';

export type OverlayMode = 'all' | 'selected' | 'hidden';

export type DocumentViewMode = 'preview' | 'markdown' | 'split';

export type MarkdownEngine =
  | 'best_available_markdown'
  | 'lmstudio_markdown'
  | 'markitdown'
  | 'markitdown_cu';

export type ExplorerViewMode = 'tiles' | 'details';

export type ExplorerTileSize = 'small' | 'medium' | 'large' | 'xlarge';

export type ExplorerSortBy = 'name' | 'type' | 'size' | 'status' | 'modified' | 'created';

export type SortDirection = 'asc' | 'desc';

export type PreviewRotation = 0 | 90 | 180 | 270;

export interface PageSelectOptions {
  replace?: boolean;
  source?: 'scroll';
}

export type ExplorerSelection =
  | { kind: 'root' }
  | { kind: 'directory'; pathKey: string; label: string }
  | { kind: 'document'; fileHash: string }
  | { kind: 'diagnostics'; fileHash: string; pageNo?: number }
  | { kind: 'page'; fileHash: string; pageNo: number }
  | { kind: 'overlay'; overlay: OverlayBox };

export interface OverlayPageGroup {
  pageNo: number;
  overlays: OverlayBox[];
}
