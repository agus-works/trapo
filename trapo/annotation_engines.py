from __future__ import annotations

ACTIVE_REGION_ENGINES = (
    "docling",
    "mineru",
    "infinity",
    "docling_normalized",
    "mineru_normalized",
)
ACTIVE_REGION_ENGINE_SQL_LIST = ", ".join(
    f"'{engine}'" for engine in ACTIVE_REGION_ENGINES
)


def is_active_region_engine(annotation_engine: str) -> bool:
    return annotation_engine.strip().lower() in ACTIVE_REGION_ENGINES
