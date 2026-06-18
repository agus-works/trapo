from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from trapo.annotation.fusion.geometry import (
    absolute_bbox,
    bbox_area,
    bbox_intersection_area,
    bbox_iou,
)
from trapo.annotation.fusion.profiles import FusionProfile
from trapo.annotation.fusion.metrics import agreement_level, fusion_agreement_summary
from trapo.annotation.fusion.models import (
    FUSION_ENGINE,
    FUSION_MODEL,
    FUSION_PROVIDER,
    SOURCE_ENGINES,
    FusedRegion,
    FusionCandidate,
)
from trapo.server.models import OverlayBox, PageInfo, RawBBox


def candidates_from_overlays(
    overlays: list[OverlayBox],
    pages_by_no: dict[int, PageInfo],
) -> list[FusionCandidate]:
    candidates: list[FusionCandidate] = []
    for overlay in overlays:
        if overlay.annotation_engine not in SOURCE_ENGINES:
            continue
        page = pages_by_no.get(overlay.page_no)
        if page is None:
            continue
        raw_bbox = absolute_bbox(overlay.bbox, page)
        area = bbox_area(raw_bbox)
        if area <= 0:
            continue
        candidates.append(
            FusionCandidate(
                region_id=overlay.overlay_id.removeprefix("region:"),
                overlay_id=overlay.overlay_id,
                annotation_engine=overlay.annotation_engine,
                page_no=overlay.page_no,
                label=overlay.label or overlay.region_kind,
                region_kind=region_kind(overlay.region_kind),
                text=overlay.text_preview.strip(),
                raw_bbox=raw_bbox,
                area=area,
            )
        )
    return candidates


def fuse_candidates(
    candidates: list[FusionCandidate],
    profile: FusionProfile,
) -> list[FusedRegion]:
    clusters: list[list[FusionCandidate]] = []
    for candidate in sorted(candidates, key=candidate_sort_key):
        cluster = matching_cluster(candidate, clusters, profile)
        if cluster is None:
            clusters.append([candidate])
        else:
            cluster.append(candidate)
    return [
        fused_region(index, cluster, profile) for index, cluster in enumerate(clusters)
    ]


def fusion_data(
    file_hash: str,
    candidates: list[FusionCandidate],
    fused_regions: list[FusedRegion],
    profile: FusionProfile,
) -> dict[str, Any]:
    return {
        "engine": FUSION_ENGINE,
        "provider": FUSION_PROVIDER,
        "model": FUSION_MODEL,
        "profile": profile.metadata(),
        "file_hash": file_hash,
        "source_engines": sorted(SOURCE_ENGINES),
        "source_region_count": len(candidates),
        "region_count": len(fused_regions),
        "agreement_summary": fusion_agreement_summary(candidates, fused_regions),
        "regions": [
            {
                "source_ref": region.source_ref,
                "page_no": region.page_no,
                "label": region.label,
                "region_kind": region.region_kind,
                "text": region.text,
                "raw_bbox": region.raw_bbox.model_dump(),
                "metadata": region.metadata,
            }
            for region in fused_regions
        ],
    }


def fused_region_id(file_hash: str, region: FusedRegion, profile: FusionProfile) -> str:
    key = "|".join(
        str(part)
        for part in (
            file_hash,
            profile.annotation_engine,
            region.source_ref,
            region.page_no,
            round(region.raw_bbox.left, 3),
            round(region.raw_bbox.top, 3),
            round(region.raw_bbox.right, 3),
            round(region.raw_bbox.bottom, 3),
        )
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def matching_cluster(
    candidate: FusionCandidate,
    clusters: list[list[FusionCandidate]],
    profile: FusionProfile,
) -> list[FusionCandidate] | None:
    for cluster in clusters:
        if any(should_cluster(candidate, other, profile) for other in cluster):
            return cluster
    return None


def should_cluster(
    left: FusionCandidate, right: FusionCandidate, profile: FusionProfile
) -> bool:
    if left.page_no != right.page_no or kind_group(left.region_kind) != kind_group(
        right.region_kind
    ):
        return False
    iou = bbox_iou(left.raw_bbox, right.raw_bbox)
    coverage = bbox_intersection_area(left.raw_bbox, right.raw_bbox) / max(
        min(left.area, right.area),
        1.0,
    )
    return (
        iou >= profile.merge_iou_threshold
        or coverage >= profile.merge_coverage_threshold
    )


def fused_region(
    index: int,
    cluster: list[FusionCandidate],
    profile: FusionProfile,
) -> FusedRegion:
    anchor = anchor_candidate(cluster, profile)
    contributors = contributors_for(anchor, cluster, profile)
    source_regions = [
        source_metadata(candidate, contributed=candidate in contributors)
        for candidate in cluster
    ]
    source_engine_counts = dict(
        Counter(candidate.annotation_engine for candidate in cluster)
    )
    source_engines = set(source_engine_counts)
    return FusedRegion(
        source_ref=f"fusion:cluster:{index}",
        page_no=anchor.page_no,
        label=most_common([candidate.label for candidate in cluster], anchor.label),
        region_kind=most_common(
            [candidate.region_kind for candidate in cluster], anchor.region_kind
        ),
        text=best_text(cluster, anchor),
        raw_bbox=weighted_bbox(contributors, profile),
        metadata={
            "source": "deterministic_region_fusion",
            "model": FUSION_MODEL,
            "fusion_profile": profile.metadata(),
            "anchor_region_id": anchor.region_id,
            "contributing_region_ids": [
                candidate.region_id for candidate in contributors
            ],
            "source_regions": source_regions,
            "source_engine_counts": source_engine_counts,
            "source_engine_count": len(source_engines),
            "agreement_level": agreement_level(source_engines),
        },
    )


def anchor_candidate(
    cluster: list[FusionCandidate], profile: FusionProfile
) -> FusionCandidate:
    return min(
        cluster, key=lambda candidate: anchor_sort_key(candidate, cluster, profile)
    )


def contributors_for(
    anchor: FusionCandidate,
    cluster: list[FusionCandidate],
    profile: FusionProfile,
) -> list[FusionCandidate]:
    contributors = [
        candidate
        for candidate in cluster
        if can_contribute_to_consensus(anchor, candidate, profile)
    ]
    return contributors or [anchor]


def can_contribute_to_consensus(
    anchor: FusionCandidate,
    candidate: FusionCandidate,
    profile: FusionProfile,
) -> bool:
    if candidate is anchor:
        return True
    area_ratio = max(anchor.area, candidate.area) / max(
        min(anchor.area, candidate.area), 1.0
    )
    return (
        area_ratio <= profile.consensus_area_ratio
        and bbox_iou(anchor.raw_bbox, candidate.raw_bbox)
        >= profile.consensus_iou_threshold
    )


def weighted_bbox(candidates: list[FusionCandidate], profile: FusionProfile) -> RawBBox:
    total_weight = sum(
        engine_weight(candidate.annotation_engine, profile) for candidate in candidates
    )
    return RawBBox(
        left=weighted_coordinate(candidates, total_weight, "left", profile),
        top=weighted_coordinate(candidates, total_weight, "top", profile),
        right=weighted_coordinate(candidates, total_weight, "right", profile),
        bottom=weighted_coordinate(candidates, total_weight, "bottom", profile),
        coord_origin="TOPLEFT",
    )


def weighted_coordinate(
    candidates: list[FusionCandidate],
    total_weight: float,
    field: str,
    profile: FusionProfile,
) -> float:
    divisor = total_weight if total_weight > 0 else 1.0
    return (
        sum(
            getattr(candidate.raw_bbox, field)
            * engine_weight(candidate.annotation_engine, profile)
            for candidate in candidates
        )
        / divisor
    )


def source_metadata(candidate: FusionCandidate, *, contributed: bool) -> dict[str, Any]:
    return {
        "region_id": candidate.region_id,
        "overlay_id": candidate.overlay_id,
        "annotation_engine": candidate.annotation_engine,
        "label": candidate.label,
        "region_kind": candidate.region_kind,
        "text": candidate.text,
        "raw_bbox": candidate.raw_bbox.model_dump(),
        "contributed_to_bbox": contributed,
    }


def candidate_sort_key(
    candidate: FusionCandidate,
) -> tuple[int, str, float, float, float]:
    return (
        candidate.page_no,
        kind_group(candidate.region_kind),
        candidate.raw_bbox.top,
        candidate.raw_bbox.left,
        candidate.area,
    )


def anchor_sort_key(
    candidate: FusionCandidate,
    cluster: list[FusionCandidate],
    profile: FusionProfile,
) -> tuple[int, float, float]:
    support = sum(
        1
        for other in cluster
        if other is not candidate and should_cluster(candidate, other, profile)
    )
    return (-support, engine_priority(candidate.annotation_engine), candidate.area)


def most_common(values: list[str], fallback: str) -> str:
    normalized = [value for value in values if value.strip()]
    if not normalized:
        return fallback
    return Counter(normalized).most_common(1)[0][0]


def best_text(cluster: list[FusionCandidate], anchor: FusionCandidate) -> str:
    values = [candidate.text for candidate in cluster if candidate.text.strip()]
    if anchor.text.strip():
        return anchor.text
    return max(values, key=len) if values else anchor.label


def kind_group(value: str) -> str:
    kind = region_kind(value)
    if kind in {"other", "title", "header", "footer", "footnote", "page_number"}:
        return "text"
    return kind


def region_kind(value: str) -> str:
    return value.strip().lower() or "other"


def engine_priority(annotation_engine: str) -> int:
    return {"docling": 0, "mineru": 1, "lmstudio": 2}.get(annotation_engine, 9)


def engine_weight(annotation_engine: str, profile: FusionProfile) -> float:
    return profile.engine_weights.get(annotation_engine, 1.0)
