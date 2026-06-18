import type {
  DiagnosticRunRecord,
  DiagnosticTraceParams,
  DiagnosticTracePayload,
} from '../diagnostics/types';
import type {
  AnnotationSettingsPayload,
  AnnotationVisibilityResponse,
  AnnotationVisibilityUpdate,
  CommandSearchResultRecord,
  DocumentDetail,
  DocumentMarkdownPayload,
  DocumentRegionsPayload,
  DocumentSummary,
  GlobalSearchResultRecord,
} from '../generated/model';
import { getDocumentAssetApiDocumentsFileHashAssetGetUrl } from '../generated/trapo';
import { buildApiUrl, getBlob, getJson, putJson } from './http';

export interface CommandSearchParams {
  limit?: number;
  q?: string | null;
}

export interface GlobalSearchParams {
  limit?: number;
  q?: string | null;
}

export const trapoApi = {
  listDocuments(signal?: AbortSignal): Promise<DocumentSummary[]> {
    return getJson<DocumentSummary[]>(buildApiUrl('/api/documents'), signal);
  },

  getDocument(fileHash: string, signal?: AbortSignal): Promise<DocumentDetail> {
    return getJson<DocumentDetail>(
      buildApiUrl(`/api/documents/${encodeURIComponent(fileHash)}`),
      signal,
    );
  },

  getDocumentRegions(fileHash: string, signal?: AbortSignal): Promise<DocumentRegionsPayload> {
    return getJson<DocumentRegionsPayload>(
      buildApiUrl(`/api/documents/${encodeURIComponent(fileHash)}/regions`),
      signal,
    );
  },

  getDocumentMarkdown(
    fileHash: string,
    markdownEngine = 'lmstudio_markdown',
    pageNo?: number,
    signal?: AbortSignal,
  ): Promise<DocumentMarkdownPayload> {
    return getJson<DocumentMarkdownPayload>(
      buildApiUrl(`/api/documents/${encodeURIComponent(fileHash)}/markdown`, {
        markdown_engine: markdownEngine,
        page_no: pageNo,
      }),
      signal,
    );
  },

  getDocumentAsset(fileHash: string, signal?: AbortSignal): Promise<Blob> {
    return getBlob(getDocumentAssetApiDocumentsFileHashAssetGetUrl(fileHash), signal);
  },

  getAnnotationSettings(signal?: AbortSignal): Promise<AnnotationSettingsPayload> {
    return getJson<AnnotationSettingsPayload>(buildApiUrl('/api/annotation-settings'), signal);
  },

  listDiagnosticRuns(signal?: AbortSignal): Promise<DiagnosticRunRecord[]> {
    return getJson<DiagnosticRunRecord[]>(buildApiUrl('/api/diagnostics/runs'), signal);
  },

  getDiagnosticTrace(
    params: DiagnosticTraceParams,
    signal?: AbortSignal,
  ): Promise<DiagnosticTracePayload> {
    return getJson<DiagnosticTracePayload>(
      buildApiUrl('/api/diagnostics/trace', {
        file_hash: params.fileHash,
        ingest_run_id: params.ingestRunId,
        limit: params.limit ?? 5000,
        page_no: params.pageNo,
        q: params.q,
        status: params.status === 'all' ? undefined : params.status,
      }),
      signal,
    );
  },

  updateAnnotationSettings(
    payload: AnnotationSettingsPayload,
    signal?: AbortSignal,
  ): Promise<AnnotationSettingsPayload> {
    return putJson<AnnotationSettingsPayload, AnnotationSettingsPayload>(
      buildApiUrl('/api/annotation-settings'),
      payload,
      signal,
    );
  },

  updateAnnotationVisibility(
    fileHash: string,
    payload: AnnotationVisibilityUpdate,
    signal?: AbortSignal,
  ): Promise<AnnotationVisibilityResponse> {
    return putJson<AnnotationVisibilityResponse, AnnotationVisibilityUpdate>(
      buildApiUrl(`/api/documents/${encodeURIComponent(fileHash)}/annotations/visibility`),
      payload,
      signal,
    );
  },

  documentAssetUrl(fileHash: string): string {
    return getDocumentAssetApiDocumentsFileHashAssetGetUrl(fileHash);
  },

  documentPreviewImageUrl(fileHash: string, variant: string, pageNo = 1): string {
    return buildApiUrl(
      `/api/documents/${encodeURIComponent(fileHash)}/preview-images/${encodeURIComponent(
        variant,
      )}/${pageNo}`,
    );
  },

  searchCommands(
    params: CommandSearchParams = {},
    signal?: AbortSignal,
  ): Promise<CommandSearchResultRecord[]> {
    return getJson<CommandSearchResultRecord[]>(
      buildApiUrl('/api/commands/search', { limit: params.limit ?? 20, q: params.q }),
      signal,
    );
  },

  globalSearch(
    params: GlobalSearchParams = {},
    signal?: AbortSignal,
  ): Promise<GlobalSearchResultRecord[]> {
    return getJson<GlobalSearchResultRecord[]>(
      buildApiUrl('/api/search', { limit: params.limit ?? 30, q: params.q }),
      signal,
    );
  },
};
