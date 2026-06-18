import { Bot, BoxSelect, FileScan, Layers3 } from 'lucide-react';
import type { TreeGridNode } from '../components/workbench';
import type { DocumentSummary, OverlayBox } from '../generated/model';
import { compactText } from '../lib/utils';
import type { AnnotationEngineVisibility } from './annotationVisibility';
import type { OverlayPageGroup } from './types';

interface AnnotationTreeArgs {
  selectedNodeId: string;
  engineVisibility: AnnotationEngineVisibility;
  onOverlaySelect: (overlay: OverlayBox) => void;
  onOverlayVisibilityChange: (overlay: OverlayBox, visible: boolean) => void;
  onEngineVisibilityChange: (engine: string, visible: boolean) => void;
}

export function annotationGroupNode(
  document: DocumentSummary,
  page: OverlayPageGroup,
  args: AnnotationTreeArgs,
): TreeGridNode {
  return {
    badge: page.overlays.length,
    children: annotationEngineGroups(page.overlays).map(([engine, overlays]) =>
      annotationEngineNode(document, page.pageNo, engine, overlays, args),
    ),
    icon: <Layers3 size={13} />,
    id: annotationsTreeNodeId(document.file_hash, page.pageNo),
    label: 'Annotations',
  };
}

export function annotationsTreeNodeId(fileHash: string, pageNo: number): string {
  return `document:${fileHash}:page:${pageNo}:annotations`;
}

export function annotationEngineTreeNodeId(
  fileHash: string,
  pageNo: number,
  engine: string,
): string {
  return `${annotationsTreeNodeId(fileHash, pageNo)}:${engine}`;
}

export function overlayEngine(overlay: OverlayBox): string {
  return overlay.annotation_engine ?? 'docling';
}

function annotationEngineNode(
  document: DocumentSummary,
  pageNo: number,
  engine: string,
  overlays: OverlayBox[],
  args: AnnotationTreeArgs,
): TreeGridNode {
  const visible = args.engineVisibility[engine] ?? true;
  return {
    badge: overlays.length,
    checked: visible,
    children: overlays.map((overlay) => ({
      badge: overlay.region_kind ?? overlay.label ?? `chunk ${overlay.chunk_id}`,
      checked: !overlay.hidden,
      icon: overlayIcon(overlay),
      id: overlayTreeNodeId(overlay.overlay_id),
      label: overlayTreeTitle(overlay),
      onCheckedChange: (checked) => args.onOverlayVisibilityChange(overlay, checked),
      onSelect: () => args.onOverlaySelect(overlay),
      selected: args.selectedNodeId === overlayTreeNodeId(overlay.overlay_id),
    })),
    icon: annotationEngineIcon(engine, overlays[0]),
    id: annotationEngineTreeNodeId(document.file_hash, pageNo, engine),
    label: annotationEngineLabel(engine),
    onCheckedChange: (checked) => args.onEngineVisibilityChange(engine, checked),
  };
}

function annotationEngineGroups(overlays: OverlayBox[]): Array<[string, OverlayBox[]]> {
  const groups = new Map<string, OverlayBox[]>();
  for (const overlay of overlays) {
    const engine = overlayEngine(overlay);
    const pageOverlays = groups.get(engine) ?? [];
    pageOverlays.push(overlay);
    groups.set(engine, pageOverlays);
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
}

function annotationEngineLabel(engine: string): string {
  if (engine === 'docling') {
    return 'Docling';
  }
  if (engine === 'docling_normalized') {
    return 'Docling normalized';
  }
  if (engine === 'mineru') {
    return 'MinerU';
  }
  if (engine === 'mineru_normalized') {
    return 'MinerU normalized';
  }
  return engine;
}

function annotationEngineIcon(engine: string, overlay: OverlayBox | undefined) {
  const color = overlay?.style.stroke_color ?? annotationEngineColor(engine);
  if (engine === 'mineru' || engine === 'mineru_normalized') {
    return <Bot color={color} size={13} />;
  }
  return <FileScan color={color} size={13} />;
}

function annotationEngineColor(engine: string): string {
  if (engine === 'docling_normalized') {
    return '#f07d5f';
  }
  if (engine === 'mineru') {
    return '#36cfd1';
  }
  if (engine === 'mineru_normalized') {
    return '#43b39f';
  }
  return '#d55344';
}

function overlayIcon(overlay: OverlayBox) {
  return <BoxSelect color={overlay.style.stroke_color} size={13} />;
}

function overlayTreeTitle(overlay: OverlayBox): string {
  const text = overlay.text_preview.trim();
  return text
    ? compactText(text, 58)
    : (overlay.label ?? overlay.source_ref ?? `Segment ${overlay.chunk_index}`);
}

function overlayTreeNodeId(overlayId: string): string {
  return `overlay-tree:${overlayId}`;
}
