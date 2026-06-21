from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from trapo.assets import image_page_info, is_image_path
from trapo.db import DuckConnection
from trapo.ingest.options import IngestOptions
from trapo.page_orientation import (
    read_page_orientation_overrides,
    upsert_page_orientation_override,
)
from trapo.page_orientation_heuristics import infer_docling_image_rotation


def process_docling_orientation_heuristic(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
    options: IngestOptions,
    log: Callable[[str], None],
) -> int:
    del options
    stored = 0
    if is_image_path(path):
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
