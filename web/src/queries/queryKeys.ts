import type { DiagnosticTraceParams } from '../diagnostics/types';
import type { CommandSearchParams, GlobalSearchParams } from '../services/trapoApi';

export const queryKeys = {
  annotationSettings: ['annotation-settings'] as const,
  documents: ['documents'] as const,
  documentDetail: (fileHash: string) => ['documents', fileHash, 'detail'] as const,
  documentRegions: (fileHash: string) => ['documents', fileHash, 'regions'] as const,
  documentMarkdown: (fileHash: string, markdownEngine: string, pageNo?: number) =>
    ['documents', fileHash, 'markdown', markdownEngine, pageNo ?? 'all'] as const,
  documentAsset: (fileHash: string) => ['documents', fileHash, 'asset'] as const,
  diagnosticRuns: ['diagnostics', 'runs'] as const,
  diagnosticProgress: (ingestRunId?: number | null) =>
    ['diagnostics', 'progress', ingestRunId ?? 'latest'] as const,
  diagnosticAnalytics: (ingestRunId?: number | null) =>
    ['diagnostics', 'analytics', ingestRunId ?? 'latest'] as const,
  diagnosticModels: (ingestRunId?: number | null) =>
    ['diagnostics', 'models', ingestRunId ?? 'latest'] as const,
  diagnosticTrace: (params: DiagnosticTraceParams) =>
    [
      'diagnostics',
      'trace',
      {
        fileHash: params.fileHash ?? null,
        ingestRunId: params.ingestRunId ?? null,
        pageNo: params.pageNo ?? null,
        q: params.q ?? null,
        status: params.status ?? 'all',
      },
    ] as const,
  commandSearch: (params: CommandSearchParams) =>
    [
      'commands',
      'search',
      {
        limit: params.limit ?? 20,
        q: params.q ?? null,
      },
    ] as const,
  globalSearch: (params: GlobalSearchParams) =>
    [
      'search',
      'global',
      {
        limit: params.limit ?? 30,
        q: params.q ?? null,
      },
    ] as const,
};
