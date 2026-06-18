from __future__ import annotations

from trapo.server.models import PageInfo, RawBBox
from trapo.server.provenance import parse_json_value


BBOX_COORDINATE_COUNT = 4
NORMALIZED_BBOX_SCALE = 1000.0


def bbox_from_mineru_content_bbox(
    value: object, target_page: PageInfo | None
) -> RawBBox | None:
    """Map MinerU content-list bbox coordinates into the displayed page space."""
    result: RawBBox | None = None
    coordinates = _coordinates(value)
    if target_page is not None and coordinates is not None:
        left, top, right, bottom = coordinates
        max_value = max(abs(left), abs(top), abs(right), abs(bottom))
        if max_value <= 1.0:
            scale = 1.0
            result = RawBBox(
                left=left / scale * target_page.width,
                top=top / scale * target_page.height,
                right=right / scale * target_page.width,
                bottom=bottom / scale * target_page.height,
                coord_origin="TOPLEFT",
            )
        elif max_value <= NORMALIZED_BBOX_SCALE:
            scale = NORMALIZED_BBOX_SCALE
            result = RawBBox(
                left=left / scale * target_page.width,
                top=top / scale * target_page.height,
                right=right / scale * target_page.width,
                bottom=bottom / scale * target_page.height,
                coord_origin="TOPLEFT",
            )
        else:
            result = RawBBox(
                left=left, top=top, right=right, bottom=bottom, coord_origin="TOPLEFT"
            )
    return result


def bbox_from_mineru_middle_bbox(
    value: object,
    source_page: PageInfo | None,
    target_page: PageInfo | None,
) -> RawBBox | None:
    """Map MinerU middle-json absolute bbox coordinates into the displayed page space."""
    coordinates = _coordinates(value)
    if coordinates is None or source_page is None or target_page is None:
        return None
    left, top, right, bottom = coordinates
    if source_page.width <= 0 or source_page.height <= 0:
        return RawBBox(
            left=left, top=top, right=right, bottom=bottom, coord_origin="TOPLEFT"
        )
    x_scale = target_page.width / source_page.width
    y_scale = target_page.height / source_page.height
    return RawBBox(
        left=left * x_scale,
        top=top * y_scale,
        right=right * x_scale,
        bottom=bottom * y_scale,
        coord_origin="TOPLEFT",
    )


def display_bbox_from_mineru_metadata(
    raw_bbox: RawBBox,
    metadata_value: object,
    target_page: PageInfo,
) -> RawBBox:
    """Return a display-space MinerU bbox, repairing older stored source-space rows."""
    metadata = parse_json_value(metadata_value)
    raw_item = parse_json_value(metadata.get("raw_item"))
    source = str(metadata.get("source") or "")
    if source == "content_list":
        return (
            bbox_from_mineru_content_bbox(raw_item.get("bbox"), target_page) or raw_bbox
        )
    if source == "middle_json":
        source_page = _page_from_metadata(metadata.get("source_page"))
        return (
            bbox_from_mineru_middle_bbox(raw_item.get("bbox"), source_page, target_page)
            or raw_bbox
        )
    return raw_bbox


def page_metadata(page: PageInfo | None) -> dict[str, float | int] | None:
    if page is None:
        return None
    return {"page_no": page.page_no, "width": page.width, "height": page.height}


def _page_from_metadata(value: object) -> PageInfo | None:
    data = parse_json_value(value)
    page_no = _int_or_none(data.get("page_no"))
    width = _float_or_none(data.get("width"))
    height = _float_or_none(data.get("height"))
    if page_no is None or width is None or height is None:
        return None
    return PageInfo(page_no=page_no, width=width, height=height)


def _coordinates(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) < BBOX_COORDINATE_COUNT:
        return None
    coordinates = [_float_or_none(item) for item in value[:BBOX_COORDINATE_COUNT]]
    left, top, right, bottom = coordinates
    if left is None or top is None or right is None or bottom is None:
        return None
    return float(left), float(top), float(right), float(bottom)


def _float_or_none(value: object) -> float | None:
    result: float | None = None
    if isinstance(value, int | float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            result = None
    return result


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value)
    return result
