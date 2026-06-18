from __future__ import annotations

from collections import Counter
from typing import Any

from trapo.annotation.fusion.models import SOURCE_ENGINES, FusedRegion, FusionCandidate


def fusion_agreement_summary(
    candidates: list[FusionCandidate],
    fused_regions: list[FusedRegion],
) -> dict[str, Any]:
    """Summarize source coverage and agreement for fused annotation output."""
    single_engine_regions = [
        region for region in fused_regions if len(fused_region_engines(region)) == 1
    ]
    multi_engine_regions = [
        region for region in fused_regions if len(fused_region_engines(region)) > 1
    ]
    return {
        "source_engine_region_counts": _known_engine_counts(
            Counter(candidate.annotation_engine for candidate in candidates)
        ),
        "source_region_count_by_page": _page_counts(candidates),
        "fused_region_count_by_page": _page_counts(fused_regions),
        "support_combination_counts": _support_combination_counts(fused_regions),
        "single_engine_region_count": len(single_engine_regions),
        "single_engine_region_count_by_engine": _single_engine_counts(
            single_engine_regions
        ),
        "multi_engine_region_count": len(multi_engine_regions),
        "all_source_engines_region_count": sum(
            1
            for region in fused_regions
            if SOURCE_ENGINES.issubset(fused_region_engines(region))
        ),
    }


def fused_region_engines(region: FusedRegion) -> set[str]:
    raw_counts = region.metadata.get("source_engine_counts")
    if not isinstance(raw_counts, dict):
        return set()
    return {
        str(engine)
        for engine, count in raw_counts.items()
        if isinstance(count, int | float) and count > 0
    }


def agreement_level(source_engines: set[str]) -> str:
    if len(source_engines) <= 1:
        return "single_engine"
    if SOURCE_ENGINES.issubset(source_engines):
        return "all_source_engines"
    return "multi_engine"


def _known_engine_counts(counter: Counter[str]) -> dict[str, int]:
    return {engine: int(counter.get(engine, 0)) for engine in sorted(SOURCE_ENGINES)}


def _page_counts(items: list[FusionCandidate] | list[FusedRegion]) -> dict[str, int]:
    counts = Counter(str(item.page_no) for item in items)
    return dict(sorted(counts.items(), key=lambda item: int(item[0])))


def _support_combination_counts(regions: list[FusedRegion]) -> dict[str, int]:
    counts = Counter(_support_key(fused_region_engines(region)) for region in regions)
    return dict(sorted(counts.items()))


def _single_engine_counts(regions: list[FusedRegion]) -> dict[str, int]:
    counts = Counter(next(iter(fused_region_engines(region))) for region in regions)
    return {engine: int(counts.get(engine, 0)) for engine in sorted(SOURCE_ENGINES)}


def _support_key(source_engines: set[str]) -> str:
    return "+".join(sorted(source_engines)) if source_engines else "none"
