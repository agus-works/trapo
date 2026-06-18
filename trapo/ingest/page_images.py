from __future__ import annotations

import base64
import hashlib
import importlib
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageSequence

from trapo.assets import is_image_path, is_pdf_path
from trapo.ingest.page_selection import normalize_page_numbers, selected_page_indexes
from trapo.page_orientation import normalize_clockwise_degrees


PDF_POINTS_PER_INCH = 72.0
DEFAULT_RENDER_DPI = 200
DEFAULT_MAX_SIDE = 2048
DEFAULT_IMAGE_FORMAT = "PNG"
DEFAULT_JPEG_QUALITY = 92
MIN_JPEG_QUALITY = 1
MAX_JPEG_QUALITY = 95


@dataclass(frozen=True)
class RenderedPageImage:
    page_no: int
    width: float
    height: float
    render_width: int
    render_height: int
    mime_type: str
    image_bytes: bytes
    image_sha256: str

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.image_bytes).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


def iter_rendered_pages(  # noqa: PLR0913
    path: Path,
    *,
    dpi: int = DEFAULT_RENDER_DPI,
    max_side: int = DEFAULT_MAX_SIDE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    image_rotation_degrees_by_page: dict[int, int] | None = None,
    page_numbers: set[int] | None = None,
) -> Iterator[RenderedPageImage]:
    """Yield display-oriented page images for LM Studio vision calls."""
    requested_pages = normalize_page_numbers(page_numbers)
    if is_pdf_path(path):
        yield from _iter_pdf_pages(
            path,
            dpi=dpi,
            max_side=max_side,
            image_format=image_format,
            jpeg_quality=jpeg_quality,
            rotation_degrees_by_page=image_rotation_degrees_by_page or {},
            page_numbers=requested_pages,
        )
        return
    if is_image_path(path):
        yield from _iter_image_pages(
            path,
            max_side=max_side,
            image_format=image_format,
            jpeg_quality=jpeg_quality,
            rotation_degrees_by_page=image_rotation_degrees_by_page or {},
            page_numbers=requested_pages,
        )
        return
    raise ValueError(f"Unsupported LM Studio page image input: {path.suffix}")


def _iter_pdf_pages(  # noqa: PLR0913
    path: Path,
    *,
    dpi: int,
    max_side: int,
    image_format: str,
    jpeg_quality: int,
    rotation_degrees_by_page: dict[int, int],
    page_numbers: set[int] | None,
) -> Iterator[RenderedPageImage]:
    try:
        pdfium: Any = importlib.import_module("pypdfium2")
    except Exception as exc:
        raise RuntimeError(
            "PDF rendering for LM Studio requires pypdfium2. Run `uv sync` "
            "after installing the project dependencies."
        ) from exc

    scale = max(float(dpi), 1.0) / PDF_POINTS_PER_INCH
    document = pdfium.PdfDocument(str(path))
    try:
        for page_index in selected_page_indexes(len(document), page_numbers):
            page = document[page_index]
            page_no = page_index + 1
            try:
                width, height = page.get_size()
                bitmap = page.render(scale=scale)
                rotation = rotation_degrees_by_page.get(page_no, 0)
                image = _rotate_image_clockwise(bitmap.to_pil(), rotation)
                yield _page_from_image(
                    page_no=page_no,
                    display_size=_rotated_display_size(
                        (float(width), float(height)),
                        rotation,
                    ),
                    image=image,
                    max_side=max_side,
                    image_format=image_format,
                    jpeg_quality=jpeg_quality,
                )
            finally:
                close = getattr(page, "close", None)
                if callable(close):
                    close()
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()


def _iter_image_pages(  # noqa: PLR0913
    path: Path,
    *,
    max_side: int,
    image_format: str,
    jpeg_quality: int,
    rotation_degrees_by_page: dict[int, int],
    page_numbers: set[int] | None,
) -> Iterator[RenderedPageImage]:
    with Image.open(path) as image:
        if page_numbers is None:
            for page_no, frame in enumerate(ImageSequence.Iterator(image), start=1):
                yield _render_image_frame(
                    frame,
                    page_no=page_no,
                    max_side=max_side,
                    image_format=image_format,
                    jpeg_quality=jpeg_quality,
                    rotation_degrees=rotation_degrees_by_page.get(page_no, 0),
                )
            return

        frame_count = int(getattr(image, "n_frames", 1) or 1)
        for page_index in selected_page_indexes(frame_count, page_numbers):
            image.seek(page_index)
            page_no = page_index + 1
            yield _render_image_frame(
                image,
                page_no=page_no,
                max_side=max_side,
                image_format=image_format,
                jpeg_quality=jpeg_quality,
                rotation_degrees=rotation_degrees_by_page.get(page_no, 0),
            )


def _render_image_frame(  # noqa: PLR0913
    frame: Image.Image,
    *,
    page_no: int,
    max_side: int,
    image_format: str,
    jpeg_quality: int,
    rotation_degrees: int,
) -> RenderedPageImage:
    display = _rotate_image_clockwise(
        ImageOps.exif_transpose(frame.copy()),
        rotation_degrees,
    )
    width, height = display.size
    return _page_from_image(
        page_no=page_no,
        display_size=(float(width), float(height)),
        image=display,
        max_side=max_side,
        image_format=image_format,
        jpeg_quality=jpeg_quality,
    )


def _page_from_image(  # noqa: PLR0913
    *,
    page_no: int,
    display_size: tuple[float, float],
    image: Image.Image,
    max_side: int,
    image_format: str,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> RenderedPageImage:
    normalized = _white_rgb_image(image)
    resized = _resize_for_prompt(normalized, max_side=max_side)
    image_bytes, mime_type = _encode_image(
        resized,
        image_format=image_format,
        jpeg_quality=jpeg_quality,
    )
    return RenderedPageImage(
        page_no=page_no,
        width=display_size[0],
        height=display_size[1],
        render_width=resized.width,
        render_height=resized.height,
        mime_type=mime_type,
        image_bytes=image_bytes,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
    )


def _white_rgb_image(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def _resize_for_prompt(image: Image.Image, *, max_side: int) -> Image.Image:
    if max_side <= 0:
        return image.copy()
    longest_side = max(image.size)
    if longest_side <= max_side:
        return image.copy()
    scale = max_side / longest_side
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _encode_image(
    image: Image.Image,
    *,
    image_format: str,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> tuple[bytes, str]:
    normalized_format = image_format.strip().upper() or DEFAULT_IMAGE_FORMAT
    if normalized_format not in {"PNG", "JPEG", "WEBP"}:
        normalized_format = DEFAULT_IMAGE_FORMAT
    output = BytesIO()
    if normalized_format == "JPEG":
        image.save(
            output,
            format=normalized_format,
            quality=_jpeg_quality(jpeg_quality),
            optimize=True,
        )
        return output.getvalue(), "image/jpeg"
    if normalized_format == "WEBP":
        image.save(output, format=normalized_format, quality=92, method=4)
        return output.getvalue(), "image/webp"
    image.save(output, format="PNG", optimize=True)
    return output.getvalue(), "image/png"


def _jpeg_quality(value: int) -> int:
    if not isinstance(value, int):
        return DEFAULT_JPEG_QUALITY
    return max(MIN_JPEG_QUALITY, min(MAX_JPEG_QUALITY, value))


def _rotate_image_clockwise(image: Image.Image, degrees: int) -> Image.Image:
    rotation = normalize_clockwise_degrees(degrees)
    if rotation == 0:
        return image
    transpose_by_degrees = {
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    return image.transpose(transpose_by_degrees[rotation])


def _rotated_display_size(
    display_size: tuple[float, float],
    degrees: int,
) -> tuple[float, float]:
    rotation = normalize_clockwise_degrees(degrees)
    if rotation in {90, 270}:
        return display_size[1], display_size[0]
    return display_size
