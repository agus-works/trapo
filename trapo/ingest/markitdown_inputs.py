from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trapo.assets import is_image_path
from trapo.ingest.options import IngestOptions
from trapo.ingest.page_markdown_images import (
    MarkdownRenderOptions,
    iter_markdown_page_images,
)


@dataclass(frozen=True)
class MarkItDownInput:
    path: Path
    page_no: int | None
    metadata: dict[str, Any]


def markitdown_inputs_for_path(
    path: Path,
    *,
    file_hash: str,
    options: IngestOptions,
    image_rotation_degrees_by_page: dict[int, int],
    log: Callable[[str], None] | None,
) -> list[MarkItDownInput]:
    """Return local files MarkItDown should consume for this source."""
    if not is_image_path(path):
        return [
            MarkItDownInput(
                path=path,
                page_no=None,
                metadata={
                    "input_kind": "source",
                    "source_path": str(path),
                    "normalized_image": False,
                },
            )
        ]

    render_options = MarkdownRenderOptions(
        file_hash=file_hash,
        render_dpi=options.page_markdown_render_dpi,
        image_max_side=options.page_markdown_image_max_side,
        image_format=options.page_markdown_image_format,
        jpeg_quality=options.page_markdown_jpeg_quality,
        cache_enabled=True,
        cache_root=options.page_markdown_cache_root,
        image_rotation_degrees_by_page=image_rotation_degrees_by_page,
    )
    inputs: list[MarkItDownInput] = []
    for page_image in iter_markdown_page_images(path, options=render_options, log=log):
        if page_image.image_path is None:
            raise RuntimeError(
                "MarkItDown normalized image cache did not produce a path."
            )
        inputs.append(
            MarkItDownInput(
                path=page_image.image_path,
                page_no=page_image.page.page_no,
                metadata={
                    "input_kind": "normalized_image",
                    "source_path": str(path),
                    "normalized_image": True,
                    "normalized_image_path": str(page_image.image_path),
                    "page_no": page_image.page.page_no,
                    "render_width": page_image.page.render_width,
                    "render_height": page_image.page.render_height,
                    "render_mime_type": page_image.page.mime_type,
                    "render_sha256": page_image.page.image_sha256,
                    "cache_hit": page_image.cache_hit,
                    "cache_metadata_path": str(page_image.metadata_path)
                    if page_image.metadata_path is not None
                    else None,
                },
            )
        )
    if not inputs:
        raise ValueError(f"No raster pages could be rendered for MarkItDown: {path}")
    return inputs
