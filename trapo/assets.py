from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from trapo.page_orientation import normalize_clockwise_degrees
from trapo.server.models import PageInfo


EXIF_ORIENTATION_TAG = 274
PDF_EXTENSIONS = frozenset({".pdf"})
IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif"}
)
PREVIEW_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".gif": "image/gif",
}


@dataclass(frozen=True)
class ImagePreviewContent:
    content: bytes
    media_type: str


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_pdf_path(path: Path) -> bool:
    return path.suffix.lower() in PDF_EXTENSIONS


def is_preview_path(path: Path) -> bool:
    return path.suffix.lower() in PREVIEW_EXTENSIONS


def media_type_for_path(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def image_page_info(path: Path, *, rotation_degrees: int = 0) -> PageInfo | None:
    """Return a single preview page for supported raster image assets."""
    page_info: PageInfo | None = None
    if not is_image_path(path):
        return page_info
    rotation = normalize_clockwise_degrees(rotation_degrees)
    metadata = _image_metadata(path)
    if metadata is not None:
        source_width, source_height, base_width, base_height, orientation = metadata
        display_width, display_height = _rotated_size(base_width, base_height, rotation)
        if display_width > 0 and display_height > 0:
            page_info = PageInfo(
                page_no=1,
                width=float(display_width),
                height=float(display_height),
            )
            page_info._image_base_width = float(base_width)
            page_info._image_base_height = float(base_height)
            page_info._source_width = float(source_width)
            page_info._source_height = float(source_height)
            page_info._image_orientation = orientation
            page_info._image_rotation_degrees = rotation
    return page_info


def image_preview_content(
    path: Path, *, rotation_degrees: int = 0
) -> ImagePreviewContent | None:
    """Render the first raster image page in the same orientation used by overlays."""
    preview: ImagePreviewContent | None = None
    if is_image_path(path):
        rotation = normalize_clockwise_degrees(rotation_degrees)
        try:
            with Image.open(path) as image:
                frame = next(ImageSequence.Iterator(image), None)
                if frame is not None:
                    display = _rotate_image_clockwise(
                        ImageOps.exif_transpose(frame.copy()),
                        rotation,
                    )
                    output = BytesIO()
                    _preview_image_mode(display).save(
                        output, format="PNG", optimize=True
                    )
                    preview = ImagePreviewContent(
                        content=output.getvalue(), media_type="image/png"
                    )
        except (OSError, UnidentifiedImageError):
            preview = None
    return preview


def _image_metadata(path: Path) -> tuple[int, int, int, int, int | None] | None:
    try:
        with Image.open(path) as image:
            source_width, source_height = image.size
            display_width, display_height = ImageOps.exif_transpose(image).size
            return (
                source_width,
                source_height,
                display_width,
                display_height,
                _image_orientation(image),
            )
    except (OSError, UnidentifiedImageError):
        return None


def _image_orientation(image: Image.Image) -> int | None:
    orientation = image.getexif().get(EXIF_ORIENTATION_TAG)
    return orientation if isinstance(orientation, int) else None


def _preview_image_mode(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


def _rotated_size(width: int, height: int, degrees: int) -> tuple[int, int]:
    rotation = normalize_clockwise_degrees(degrees)
    return (height, width) if rotation in {90, 270} else (width, height)


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
