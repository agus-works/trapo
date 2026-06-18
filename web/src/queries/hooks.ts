import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import type { DiagnosticTraceParams } from '../diagnostics/types';
import type {
  AnnotationSettingsPayload,
  AnnotationVisibilityUpdate,
  PageInfo,
} from '../generated/model';
import type { CommandSearchParams, GlobalSearchParams } from '../services/trapoApi';
import { trapoApi } from '../services/trapoApi';
import { queryKeys } from './queryKeys';

export function useDocumentsQuery() {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: ({ signal }) => trapoApi.listDocuments(signal),
  });
}

export function useDocumentRegionsQuery(fileHash: string | null) {
  return useQuery({
    queryKey: fileHash ? queryKeys.documentRegions(fileHash) : ['documents', 'none', 'regions'],
    queryFn: ({ signal }) => trapoApi.getDocumentRegions(fileHash ?? '', signal),
    enabled: fileHash !== null,
  });
}

export function useDocumentMarkdownQuery(
  fileHash: string | null,
  pageNo?: number,
  markdownEngine = 'lmstudio_markdown',
) {
  return useQuery({
    queryKey: fileHash
      ? queryKeys.documentMarkdown(fileHash, markdownEngine, pageNo)
      : ['documents', 'none', 'markdown', markdownEngine, pageNo ?? 'all'],
    queryFn: ({ signal }) =>
      trapoApi.getDocumentMarkdown(fileHash ?? '', markdownEngine, pageNo, signal),
    enabled: fileHash !== null,
  });
}

export function useDocumentMarkdownPrefetch(
  fileHash: string | null,
  activePageNo: number,
  pages: PageInfo[],
  markdownEngine = 'lmstudio_markdown',
) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!fileHash || pages.length === 0) {
      return;
    }
    const pageNumbers = prefetchPageNumbers(activePageNo, pages);
    let cancelled = false;
    let nextIndex = 0;
    const prefetchNext = async () => {
      while (!cancelled && nextIndex < pageNumbers.length) {
        const pageNo = pageNumbers[nextIndex];
        nextIndex += 1;
        await queryClient.prefetchQuery({
          queryKey: queryKeys.documentMarkdown(fileHash, markdownEngine, pageNo),
          queryFn: ({ signal }) =>
            trapoApi.getDocumentMarkdown(fileHash, markdownEngine, pageNo, signal),
          staleTime: 30_000,
        });
      }
    };
    for (let worker = 0; worker < Math.min(2, pageNumbers.length); worker += 1) {
      void prefetchNext();
    }
    return () => {
      cancelled = true;
    };
  }, [activePageNo, fileHash, markdownEngine, pages, queryClient]);
}

export function useDocumentAssetQuery(fileHash: string | null, enabled = true) {
  return useQuery({
    queryKey: fileHash ? queryKeys.documentAsset(fileHash) : ['documents', 'none', 'asset'],
    queryFn: ({ signal }) => trapoApi.getDocumentAsset(fileHash ?? '', signal),
    enabled: fileHash !== null && enabled,
  });
}

export function useAnnotationSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.annotationSettings,
    queryFn: ({ signal }) => trapoApi.getAnnotationSettings(signal),
  });
}

export function useDiagnosticRunsQuery() {
  return useQuery({
    queryKey: queryKeys.diagnosticRuns,
    queryFn: ({ signal }) => trapoApi.listDiagnosticRuns(signal),
  });
}

export function useDiagnosticTraceQuery(params: DiagnosticTraceParams) {
  return useQuery({
    queryKey: queryKeys.diagnosticTrace(params),
    queryFn: ({ signal }) => trapoApi.getDiagnosticTrace(params, signal),
    enabled: params.ingestRunId !== null && params.ingestRunId !== undefined,
  });
}

export function useUpdateAnnotationSettingsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AnnotationSettingsPayload) => trapoApi.updateAnnotationSettings(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.annotationSettings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
  });
}

export function useUpdateAnnotationVisibilityMutation(fileHash: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AnnotationVisibilityUpdate) =>
      trapoApi.updateAnnotationVisibility(fileHash ?? '', payload),
    onSuccess: () => {
      if (fileHash) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.documentRegions(fileHash) });
      }
    },
  });
}

export function useCommandSearchQuery(params: CommandSearchParams = {}) {
  return useQuery({
    queryKey: queryKeys.commandSearch(params),
    queryFn: ({ signal }) => trapoApi.searchCommands(params, signal),
  });
}

export function useGlobalSearchQuery(params: GlobalSearchParams = {}) {
  return useQuery({
    queryKey: queryKeys.globalSearch(params),
    queryFn: ({ signal }) => trapoApi.globalSearch(params, signal),
    enabled: (params.q?.trim().length ?? 0) > 0,
  });
}

function prefetchPageNumbers(activePageNo: number, pages: PageInfo[]): number[] {
  const available = new Set(pages.map((page) => page.page_no));
  const results: number[] = [];
  for (let distance = 1; distance <= 10; distance += 1) {
    for (const pageNo of [activePageNo - distance, activePageNo + distance]) {
      if (available.has(pageNo)) {
        results.push(pageNo);
      }
    }
  }
  return results;
}
