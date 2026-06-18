from __future__ import annotations

from trapo.server.models import PageInfo
from trapo.server.provenance import parse_json_value


def extract_lmstudio_pages(lmstudio_output_json: object) -> list[PageInfo]:
    data = parse_json_value(lmstudio_output_json)
    pages = data.get("pages")
    if not isinstance(pages, list):
        return []
    result: list[PageInfo] = []
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        page_no = _int_or_none(page.get("page_no")) or index
        width = _float_or_none(page.get("width"))
        height = _float_or_none(page.get("height"))
        if width is not None and height is not None:
            result.append(PageInfo(page_no=page_no, width=width, height=height))
    return sorted(result, key=lambda item: item.page_no)


def _int_or_none(value: object) -> int | None:
    result: int | None = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        result = int(value)
    return result


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
