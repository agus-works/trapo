from __future__ import annotations

from dataclasses import dataclass


DEFAULT_FUSION_PROFILE = "balanced"
PROFILE_PREFIX = "fusion_"


@dataclass(frozen=True)
class FusionProfile:
    name: str
    merge_iou_threshold: float
    merge_coverage_threshold: float
    consensus_iou_threshold: float
    consensus_area_ratio: float
    engine_weights: dict[str, float]

    @property
    def annotation_engine(self) -> str:
        return (
            "fusion"
            if self.name == DEFAULT_FUSION_PROFILE
            else f"{PROFILE_PREFIX}{self.name}"
        )

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "annotation_engine": self.annotation_engine,
            "merge_iou_threshold": self.merge_iou_threshold,
            "merge_coverage_threshold": self.merge_coverage_threshold,
            "consensus_iou_threshold": self.consensus_iou_threshold,
            "consensus_area_ratio": self.consensus_area_ratio,
            "engine_weights": self.engine_weights,
        }


FUSION_PROFILES = {
    "conservative": FusionProfile(
        name="conservative",
        merge_iou_threshold=0.55,
        merge_coverage_threshold=0.82,
        consensus_iou_threshold=0.35,
        consensus_area_ratio=2.0,
        engine_weights={
            "docling": 1.0,
            "mineru": 1.0,
            "lmstudio": 0.5,
            "infinity": 0.5,
        },
    ),
    "balanced": FusionProfile(
        name="balanced",
        merge_iou_threshold=0.45,
        merge_coverage_threshold=0.72,
        consensus_iou_threshold=0.25,
        consensus_area_ratio=3.0,
        engine_weights={
            "docling": 1.0,
            "mineru": 1.0,
            "lmstudio": 0.75,
            "infinity": 0.75,
        },
    ),
    "recall": FusionProfile(
        name="recall",
        merge_iou_threshold=0.3,
        merge_coverage_threshold=0.55,
        consensus_iou_threshold=0.15,
        consensus_area_ratio=6.0,
        engine_weights={
            "docling": 1.0,
            "mineru": 1.0,
            "lmstudio": 1.0,
            "infinity": 1.0,
        },
    ),
}


def resolve_fusion_profile(value: str) -> FusionProfile:
    normalized = value.strip().lower()
    if normalized not in FUSION_PROFILES:
        allowed = ", ".join(sorted(FUSION_PROFILES))
        raise ValueError(f"Unsupported fusion profile: {value}. Use one of: {allowed}")
    return FUSION_PROFILES[normalized]


def requested_fusion_profiles(value: str) -> list[FusionProfile]:
    raw_values = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not raw_values:
        raw_values = [DEFAULT_FUSION_PROFILE]
    profiles: list[FusionProfile] = []
    for raw_value in raw_values:
        names = sorted(FUSION_PROFILES) if raw_value == "all" else [raw_value]
        for name in names:
            profile = resolve_fusion_profile(name)
            if profile not in profiles:
                profiles.append(profile)
    return profiles
