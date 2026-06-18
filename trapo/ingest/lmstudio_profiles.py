from __future__ import annotations

from dataclasses import dataclass

from trapo.ingest.lmstudio_models import LMSTUDIO_ENGINE


DEFAULT_LMSTUDIO_PROFILE = "balanced"
ALL_LMSTUDIO_PROFILES = ("balanced", "strict", "recall")


@dataclass(frozen=True)
class LmStudioPromptProfile:
    name: str
    annotation_engine: str
    instructions: str

    def metadata(self) -> dict[str, str]:
        return {
            "name": self.name,
            "annotation_engine": self.annotation_engine,
            "instructions": self.instructions,
        }


@dataclass(frozen=True)
class LmStudioProfileRunSummary:
    region_count: int
    error_count: int


LMSTUDIO_PROMPT_PROFILES = {
    "balanced": LmStudioPromptProfile(
        name="balanced",
        annotation_engine=LMSTUDIO_ENGINE,
        instructions=(
            "Balanced profile: return tight logical document regions. Preserve "
            "important content while avoiding duplicates and broad page-level boxes."
        ),
    ),
    "strict": LmStudioPromptProfile(
        name="strict",
        annotation_engine="lmstudio_strict",
        instructions=(
            "Strict profile: return only clearly visible, high-confidence regions "
            "with crisp boundaries. Prefer fewer boxes over uncertain boxes."
        ),
    ),
    "recall": LmStudioPromptProfile(
        name="recall",
        annotation_engine="lmstudio_recall",
        instructions=(
            "Recall profile: include every plausible visible document region, "
            "including small captions, stamps, marks, and isolated text blocks."
        ),
    ),
}


def requested_lmstudio_profiles(value: str) -> list[LmStudioPromptProfile]:
    raw_profiles = [part.strip().lower() for part in value.split(",") if part.strip()]
    requested = raw_profiles or [DEFAULT_LMSTUDIO_PROFILE]
    profiles: list[LmStudioPromptProfile] = []
    for name in requested:
        if name == "all":
            for profile_name in ALL_LMSTUDIO_PROFILES:
                _append_profile(profiles, profile_name)
            continue
        _append_profile(profiles, name)
    return profiles


def _append_profile(profiles: list[LmStudioPromptProfile], name: str) -> None:
    profile = LMSTUDIO_PROMPT_PROFILES.get(name)
    if profile is None:
        supported = ", ".join((*ALL_LMSTUDIO_PROFILES, "all"))
        raise ValueError(
            f"Unsupported LM Studio profile '{name}'. Supported values: {supported}."
        )
    if profile not in profiles:
        profiles.append(profile)
