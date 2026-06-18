from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from trapo.assets import (
    image_page_info,
    image_preview_content,
    is_image_path,
    is_preview_path,
    media_type_for_path,
)
from trapo.server.models import RawBBox
from trapo.server.provenance import _normalize_bbox


IMAGE_CASES = [
    ("sample.png", "PNG", "image/png"),
    ("sample.jpg", "JPEG", "image/jpeg"),
    ("sample.jpeg", "JPEG", "image/jpeg"),
    ("sample.bmp", "BMP", "image/bmp"),
    ("sample.webp", "WEBP", "image/webp"),
    ("sample.tiff", "TIFF", "image/tiff"),
    ("sample.gif", "GIF", "image/gif"),
]
IMAGE_WIDTH = 64
IMAGE_HEIGHT = 32
ROTATED_BOX_LEFT_PCT = 15.625
MANUAL_ROTATED_BOX_LEFT_PCT = 37.5
ROTATED_BOX_TOP_PCT = 15.625
ROTATED_BOX_WIDTH_PCT = 46.875
ROTATED_BOX_HEIGHT_PCT = 31.25
MANUAL_ROTATION_DEGREES = 90


def test_supported_image_assets_report_preview_metadata(tmp_path) -> None:
    for filename, image_format, media_type in IMAGE_CASES:
        path = tmp_path / filename
        _write_image(path, image_format=image_format, size=(IMAGE_WIDTH, IMAGE_HEIGHT))

        page = image_page_info(path)

        assert is_image_path(path)
        assert is_preview_path(path)
        assert media_type_for_path(path) == media_type
        assert page is not None
        assert page.page_no == 1
        assert page.width == float(IMAGE_WIDTH)
        assert page.height == float(IMAGE_HEIGHT)


def test_image_page_info_uses_exif_oriented_dimensions(tmp_path) -> None:
    path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), color=(42, 84, 126))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, format="JPEG", exif=exif)

    page = image_page_info(path)

    assert page is not None
    assert page.width == float(IMAGE_HEIGHT)
    assert page.height == float(IMAGE_WIDTH)

    bbox = _normalize_bbox(
        RawBBox(left=10.0, top=20.0, right=30.0, bottom=5.0, coord_origin="BOTTOMLEFT"),
        page,
    )

    assert bbox.left_pct == ROTATED_BOX_LEFT_PCT
    assert bbox.top_pct == ROTATED_BOX_TOP_PCT
    assert bbox.width_pct == ROTATED_BOX_WIDTH_PCT
    assert bbox.height_pct == ROTATED_BOX_HEIGHT_PCT


def test_image_page_info_uses_manual_rotation_override(tmp_path) -> None:
    path = tmp_path / "sideways.jpg"
    _write_image(path, image_format="JPEG", size=(IMAGE_WIDTH, IMAGE_HEIGHT))

    page = image_page_info(path, rotation_degrees=MANUAL_ROTATION_DEGREES)
    preview = image_preview_content(path, rotation_degrees=MANUAL_ROTATION_DEGREES)

    assert page is not None
    assert page.width == float(IMAGE_HEIGHT)
    assert page.height == float(IMAGE_WIDTH)
    assert preview is not None
    assert preview.media_type == "image/png"
    with Image.open(BytesIO(preview.content)) as preview_image:
        assert preview_image.size == (IMAGE_HEIGHT, IMAGE_WIDTH)

    bbox = _normalize_bbox(
        RawBBox(left=10.0, top=5.0, right=30.0, bottom=20.0, coord_origin="TOPLEFT"),
        page,
    )

    assert bbox.left_pct == MANUAL_ROTATED_BOX_LEFT_PCT
    assert bbox.top_pct == ROTATED_BOX_TOP_PCT
    assert bbox.width_pct == ROTATED_BOX_WIDTH_PCT
    assert bbox.height_pct == ROTATED_BOX_HEIGHT_PCT


def test_image_page_info_ignores_unsupported_or_invalid_images(tmp_path) -> None:
    text_path = tmp_path / "note.txt"
    text_path.write_text("not an image", encoding="utf-8")
    broken_path = tmp_path / "broken.webp"
    broken_path.write_bytes(b"not-webp")

    assert image_page_info(text_path) is None
    assert image_page_info(broken_path) is None


def _write_image(path: Path, *, image_format: str, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, color=(42, 84, 126))
    image.save(path, format=image_format)
