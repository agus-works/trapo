import { useNavigate } from '@tanstack/react-router';
import { useCallback } from 'react';
import type { PreviewRotation } from '../types';

const DEFAULT_PREVIEW_ZOOM = 1;
const MIN_PREVIEW_ZOOM = 0.25;
const MAX_PREVIEW_ZOOM = 3;

export function usePreviewTransformActions() {
  const navigate = useNavigate({ from: '/' });
  const onPreviewZoomChange = useCallback(
    (zoom: number) => {
      const normalized = normalizePreviewZoom(zoom);
      void navigate({
        search: (current) => ({
          ...current,
          zoom: normalized === DEFAULT_PREVIEW_ZOOM ? undefined : normalized,
        }),
      });
    },
    [navigate],
  );
  const onPreviewRotationChange = useCallback(
    (rotation: PreviewRotation) =>
      void navigate({
        search: (current) => ({
          ...current,
          rotation: rotation === 0 ? undefined : rotation,
        }),
      }),
    [navigate],
  );
  const onPreviewTransformReset = useCallback(
    () =>
      void navigate({
        search: (current) => ({ ...current, rotation: undefined, zoom: undefined }),
      }),
    [navigate],
  );
  return { onPreviewRotationChange, onPreviewTransformReset, onPreviewZoomChange };
}

function normalizePreviewZoom(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_PREVIEW_ZOOM;
  }
  return Math.min(MAX_PREVIEW_ZOOM, Math.max(MIN_PREVIEW_ZOOM, Math.round(value * 100) / 100));
}
