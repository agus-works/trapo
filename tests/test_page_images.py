from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from pytest import mark

from trapo.ingest.page_images import iter_rendered_pages


PDF_FIRST_WIDTH = 200.0
PDF_FIRST_HEIGHT = 100.0
PDF_SECOND_WIDTH = 100.0
PDF_SECOND_HEIGHT = 200.0
PDF_MAX_SIDE = 100
IMAGE_WIDTH = 120.0
IMAGE_HEIGHT = 60.0
IMAGE_MAX_SIDE = 80
ROTATED_WIDTH = 60.0
ROTATED_HEIGHT = 120.0
TIFF_FIRST_WIDTH = 40.0
TIFF_SECOND_WIDTH = 30.0
ANIMATED_FRAME_COUNT = 2


def test_iter_rendered_pages_renders_pdf_page_by_page(tmp_path) -> None:
    path = tmp_path / "two-pages.pdf"
    _write_minimal_pdf(
        path,
        [(PDF_FIRST_WIDTH, PDF_FIRST_HEIGHT), (PDF_SECOND_WIDTH, PDF_SECOND_HEIGHT)],
    )

    pages = list(iter_rendered_pages(path, dpi=72, max_side=PDF_MAX_SIDE))

    assert [page.page_no for page in pages] == [1, 2]
    assert pages[0].width == PDF_FIRST_WIDTH
    assert pages[0].height == PDF_FIRST_HEIGHT
    assert pages[0].render_width == PDF_MAX_SIDE
    assert pages[0].render_height == PDF_MAX_SIDE // 2
    assert pages[1].width == PDF_SECOND_WIDTH
    assert pages[1].height == PDF_SECOND_HEIGHT
    assert pages[1].render_width == PDF_MAX_SIDE // 2
    assert pages[1].render_height == PDF_MAX_SIDE
    assert all(page.mime_type == "image/png" for page in pages)


def test_iter_rendered_pages_applies_pdf_rotation_overrides(tmp_path) -> None:
    path = tmp_path / "rotated.pdf"
    _write_minimal_pdf(path, [(PDF_FIRST_WIDTH, PDF_FIRST_HEIGHT)])

    pages = list(
        iter_rendered_pages(
            path,
            dpi=72,
            max_side=PDF_MAX_SIDE,
            image_rotation_degrees_by_page={1: 90},
        )
    )

    assert len(pages) == 1
    assert pages[0].width == PDF_FIRST_HEIGHT
    assert pages[0].height == PDF_FIRST_WIDTH
    assert pages[0].render_width == PDF_MAX_SIDE // 2
    assert pages[0].render_height == PDF_MAX_SIDE


def test_iter_rendered_pages_can_render_selected_pdf_pages(tmp_path) -> None:
    path = tmp_path / "two-pages.pdf"
    _write_minimal_pdf(
        path,
        [(PDF_FIRST_WIDTH, PDF_FIRST_HEIGHT), (PDF_SECOND_WIDTH, PDF_SECOND_HEIGHT)],
    )

    pages = list(
        iter_rendered_pages(path, dpi=72, max_side=PDF_MAX_SIDE, page_numbers={2})
    )

    assert [page.page_no for page in pages] == [2]
    assert pages[0].width == PDF_SECOND_WIDTH
    assert pages[0].height == PDF_SECOND_HEIGHT


@mark.parametrize(
    ("filename", "image_format"),
    [
        ("page.png", "PNG"),
        ("page.jpg", "JPEG"),
        ("page.webp", "WEBP"),
    ],
)
def test_iter_rendered_pages_supports_static_raster_inputs(
    tmp_path,
    filename: str,
    image_format: str,
) -> None:
    path = tmp_path / filename
    Image.new("RGB", (int(IMAGE_WIDTH), int(IMAGE_HEIGHT)), color=(255, 255, 255)).save(
        path,
        format=image_format,
    )

    pages = list(iter_rendered_pages(path, max_side=IMAGE_MAX_SIDE))

    assert len(pages) == 1
    assert pages[0].page_no == 1
    assert pages[0].width == IMAGE_WIDTH
    assert pages[0].height == IMAGE_HEIGHT
    assert pages[0].render_width == IMAGE_MAX_SIDE
    assert pages[0].render_height == IMAGE_MAX_SIDE // 2
    assert pages[0].mime_type == "image/png"


@mark.parametrize(("suffix", "image_format"), [(".gif", "GIF"), (".tiff", "TIFF")])
def test_iter_rendered_pages_splits_animated_or_multipage_images(
    tmp_path,
    suffix: str,
    image_format: str,
) -> None:
    path = tmp_path / f"scan{suffix}"
    first = Image.new("RGB", (int(TIFF_FIRST_WIDTH), 20), color=(255, 255, 255))
    second = Image.new("RGB", (int(TIFF_SECOND_WIDTH), 10), color=(240, 240, 240))
    first.save(path, format=image_format, save_all=True, append_images=[second])

    pages = list(iter_rendered_pages(path, max_side=20))

    assert len(pages) == ANIMATED_FRAME_COUNT
    assert [page.page_no for page in pages] == [1, 2]
    assert pages[0].width == TIFF_FIRST_WIDTH
    if image_format == "TIFF":
        assert pages[1].width == TIFF_SECOND_WIDTH
    else:
        assert pages[1].width == TIFF_FIRST_WIDTH


def test_iter_rendered_pages_can_render_selected_multipage_image(tmp_path) -> None:
    path = tmp_path / "scan.tiff"
    first = Image.new("RGB", (int(TIFF_FIRST_WIDTH), 20), color=(255, 255, 255))
    second = Image.new("RGB", (int(TIFF_SECOND_WIDTH), 10), color=(240, 240, 240))
    first.save(path, format="TIFF", save_all=True, append_images=[second])

    pages = list(iter_rendered_pages(path, max_side=20, page_numbers={2}))

    assert [page.page_no for page in pages] == [2]
    assert pages[0].width == TIFF_SECOND_WIDTH


def test_iter_rendered_pages_applies_image_rotation_overrides(tmp_path) -> None:
    path = tmp_path / "receipt.png"
    Image.new("RGB", (int(IMAGE_WIDTH), int(IMAGE_HEIGHT)), color=(255, 255, 255)).save(
        path
    )

    pages = list(
        iter_rendered_pages(
            path,
            max_side=IMAGE_MAX_SIDE,
            image_rotation_degrees_by_page={1: 90},
        )
    )

    assert len(pages) == 1
    assert pages[0].width == ROTATED_WIDTH
    assert pages[0].height == ROTATED_HEIGHT
    assert pages[0].render_width == IMAGE_MAX_SIDE // 2
    assert pages[0].render_height == IMAGE_MAX_SIDE


def _write_minimal_pdf(path: Path, page_sizes: list[tuple[float, float]]) -> None:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        _pdf_pages_object(len(page_sizes)),
    ]
    for index, (width, height) in enumerate(page_sizes):
        content_object_id = 2 + len(page_sizes) + index + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:g} {height:g}] "
                f"/Resources << >> /Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
    objects.extend([b"<< /Length 0 >>\nstream\n\nendstream" for _ in page_sizes])
    path.write_bytes(_pdf_bytes(objects))


def _pdf_pages_object(page_count: int) -> bytes:
    kids = " ".join(f"{index} 0 R" for index in range(3, page_count + 3))
    return f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii")


def _pdf_bytes(objects: list[bytes]) -> bytes:
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode("ascii"))
        output.write(body)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return output.getvalue()
