from __future__ import annotations

from trapo.server.models import NormalizedBBox, PageInfo, RawBBox


def absolute_bbox(bbox: NormalizedBBox, page: PageInfo) -> RawBBox:
    return RawBBox(
        left=bbox.left_pct / 100.0 * page.width,
        top=bbox.top_pct / 100.0 * page.height,
        right=(bbox.left_pct + bbox.width_pct) / 100.0 * page.width,
        bottom=(bbox.top_pct + bbox.height_pct) / 100.0 * page.height,
        coord_origin="TOPLEFT",
    )


def bbox_area(bbox: RawBBox) -> float:
    return max(0.0, bbox.right - bbox.left) * max(0.0, bbox.bottom - bbox.top)


def bbox_iou(left: RawBBox, right: RawBBox) -> float:
    intersection = bbox_intersection_area(left, right)
    union = bbox_area(left) + bbox_area(right) - intersection
    return intersection / union if union > 0 else 0.0


def bbox_intersection_area(left: RawBBox, right: RawBBox) -> float:
    x0 = max(left.left, right.left)
    y0 = max(left.top, right.top)
    x1 = min(left.right, right.right)
    y1 = min(left.bottom, right.bottom)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)
