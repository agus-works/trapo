from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.ingest.page_images import RenderedPageImage
from trapo.migrations import apply_migrations
from trapo.preview_cache import (
    ensure_document_preview_page,
    read_document_preview_images,
)


def test_ensure_document_preview_page_renders_only_requested_page(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "trapo.duckdb"
    source_path = tmp_path / "scan.pdf"
    source_path.write_bytes(b"%PDF-1.4\n% test pdf\n%%EOF\n")
    config = RuntimeConfig.from_env(db_path=str(db_path))
    render_requests: list[set[int] | None] = []

    def fake_iter_rendered_pages(
        _path: Path,
        **kwargs: Any,
    ):
        page_numbers = kwargs.get("page_numbers")
        render_requests.append(page_numbers)
        for page_no in sorted(page_numbers or {1, 2, 3}):
            yield RenderedPageImage(
                page_no=page_no,
                width=100,
                height=200,
                render_width=50,
                render_height=100,
                mime_type="image/jpeg",
                image_bytes=_jpeg_bytes(),
                image_sha256=f"sha-{page_no}",
            )

    monkeypatch.setattr(
        "trapo.preview_cache.iter_rendered_pages",
        fake_iter_rendered_pages,
    )

    with connect(db_path) as connection:
        apply_migrations(connection, config, create_backup=False)
        images = ensure_document_preview_page(connection, source_path, "hash1", 2)
        stored = read_document_preview_images(connection, "hash1")

    assert render_requests == [{2}]
    assert {image.page_no for image in images} == {2}
    assert {image.page_no for image in stored} == {2}
    assert {image.variant for image in images} >= {"normalized", "thumb_sm"}


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 40), color=(255, 255, 255)).save(output, format="JPEG")
    return output.getvalue()
