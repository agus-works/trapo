from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trapo.assets import image_page_info, is_image_path
from trapo.db import DuckConnection
from trapo.ingest.lmstudio_models import LmStudioOptions
from trapo.ingest.lmstudio_orientation import (
    LmStudioOrientationRequest,
    detect_lmstudio_page_orientations,
)
from trapo.ingest.options import IngestOptions
from trapo.observability import span_set_attributes, traced_span
from trapo.page_orientation import (
    PageOrientationOverride,
    read_page_orientation_overrides,
    upsert_page_orientation_override,
)
from trapo.page_orientation_heuristics import infer_docling_image_rotation


def process_lmstudio_orientation(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    existing_overrides = read_page_orientation_overrides(connection, file_hash)
    manual_pages = _manual_orientation_pages(existing_overrides)
    lmstudio_options = LmStudioOptions(
        base_url=options.lmstudio_base_url,
        model=options.lmstudio_model,
        timeout_seconds=options.lmstudio_timeout_seconds,
        render_dpi=options.lmstudio_render_dpi,
        image_max_side=options.lmstudio_image_max_side,
        max_tokens=options.lmstudio_max_tokens,
        box_origin=options.lmstudio_box_origin,
        include_evidence=False,
    )
    with traced_span(
        "trapo.ingest.lmstudio_orientation",
        attributes={
            "file.hash": file_hash,
            "lmstudio.model": options.lmstudio_model,
            "lmstudio.orientation.mode": options.lmstudio_orientation,
            "lmstudio.orientation.min_confidence": options.lmstudio_orientation_min_confidence,
        },
    ) as orientation_span:
        result = detect_lmstudio_page_orientations(
            path,
            request=LmStudioOrientationRequest(
                file_hash=file_hash,
                options=lmstudio_options,
                min_confidence=options.lmstudio_orientation_min_confidence,
                max_side=options.lmstudio_orientation_max_side,
                max_tokens=options.lmstudio_orientation_max_tokens,
                skip_pages=manual_pages,
            ),
            log=log,
        )
        for override in result.overrides:
            upsert_page_orientation_override(connection, override=override)
        span_set_attributes(
            orientation_span,
            {
                "lmstudio.orientation.page_count": len(result.data.get("pages", [])),
                "lmstudio.orientation.override_count": len(result.overrides),
            },
        )
    if result.overrides:
        log(f"Stored LM Studio orientation overrides: count={len(result.overrides)}")
    return len(result.overrides)


def process_docling_orientation_heuristic(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    stored = 0
    mode = options.lmstudio_orientation.strip().lower()
    if mode in {"auto", "docling", "lmstudio"} and is_image_path(path):
        page = image_page_info(path, rotation_degrees=0)
        has_exif_orientation = (
            page is not None and getattr(page, "_image_orientation", None) is not None
        )
        if (
            page is not None
            and not has_exif_orientation
            and not read_page_orientation_overrides(connection, file_hash)
        ):
            override = infer_docling_image_rotation(
                connection, file_hash=file_hash, page=page
            )
            if override is not None:
                upsert_page_orientation_override(connection, override=override)
                log(
                    "Stored Docling layout orientation override: "
                    f"page={override.page_no} clockwise={override.clockwise_degrees} "
                    f"confidence={override.confidence or 0.0:.2f}"
                )
                stored = 1
    return stored


def should_run_lmstudio_orientation(
    path: Path,
    pending_engines: list[str],
    options: IngestOptions,
) -> bool:
    mode = options.lmstudio_orientation.strip().lower()
    return (
        mode in {"auto", "lmstudio"}
        and is_image_path(path)
        and "lmstudio" in pending_engines
    )


def _manual_orientation_pages(
    overrides: dict[int, PageOrientationOverride],
) -> set[int]:
    return {
        page_no
        for page_no, override in overrides.items()
        if override.source.strip().lower() == "manual"
    }
