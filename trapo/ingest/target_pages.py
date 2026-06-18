from __future__ import annotations

from pathlib import Path

from trapo.assets import image_page_info
from trapo.db import DuckConnection, table_exists
from trapo.page_orientation import read_page_rotation_degrees
from trapo.server.models import PageInfo
from trapo.server.provenance import extract_pages


def target_pages_for_regions(
    connection: DuckConnection,
    path: Path,
    file_hash: str,
) -> list[PageInfo] | None:
    rotation_degrees = read_page_rotation_degrees(connection, file_hash, page_no=1)
    image_page = image_page_info(path, rotation_degrees=rotation_degrees)
    if image_page is not None:
        return [image_page]
    if table_exists(connection, "docling_documents"):
        row = connection.execute(
            "SELECT docling_json FROM docling_documents WHERE file_hash = ? AND status = 'ok'",
            [file_hash],
        ).fetchone()
        pages = extract_pages(row[0] if row else None)
        if pages:
            return pages
    return None


def image_rotation_degrees_by_page(pages: list[PageInfo] | None) -> dict[int, int]:
    return {
        page.page_no: int(getattr(page, "_image_rotation_degrees", 0))
        for page in pages or []
        if int(getattr(page, "_image_rotation_degrees", 0)) != 0
    }
