from __future__ import annotations

from trapo.server.models import PageInfo, RawBBox


INFINITY_BBOX_VALUE_COUNT = 4
NORMALIZED_BBOX_SCALE = 1000.0


def bbox_from_infinity_item(  # noqa: PLR0911
    item: dict[str, object], page: PageInfo
) -> RawBBox | None:
    bbox = bbox_value(item)
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return None
    max_value = max(abs(left), abs(top), abs(right), abs(bottom))
    if max_value <= 1.0:
        return _scaled_bbox(left, top, right, bottom, page, scale=1.0)
    if max_value <= NORMALIZED_BBOX_SCALE:
        return _scaled_bbox(
            left,
            top,
            right,
            bottom,
            page,
            scale=NORMALIZED_BBOX_SCALE,
        )
    return RawBBox(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        coord_origin="TOPLEFT",
    )


def bbox_value(item: dict[str, object]) -> tuple[float, float, float, float] | None:
    value = (
        item.get("bbox")
        or item.get("box")
        or item.get("box_2d")
        or item.get("bounding_box")
    )
    if not isinstance(value, list) or len(value) < INFINITY_BBOX_VALUE_COUNT:
        return None
    coordinates = [_float_or_none(item) for item in value[:INFINITY_BBOX_VALUE_COUNT]]
    left, top, right, bottom = coordinates
    if left is None or top is None or right is None or bottom is None:
        return None
    return left, top, right, bottom


def _scaled_bbox(  # noqa: PLR0913
    left: float,
    top: float,
    right: float,
    bottom: float,
    page: PageInfo,
    *,
    scale: float,
) -> RawBBox:
    return RawBBox(
        left=left / scale * page.width,
        top=top / scale * page.height,
        right=right / scale * page.width,
        bottom=bottom / scale * page.height,
        coord_origin="TOPLEFT",
    )


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
