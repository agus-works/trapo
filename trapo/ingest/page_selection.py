from __future__ import annotations


def normalize_page_numbers(page_numbers: set[int] | None) -> set[int] | None:
    if page_numbers is None:
        return None
    return {page_no for page_no in page_numbers if page_no > 0}


def selected_page_indexes(page_count: int, page_numbers: set[int] | None) -> list[int]:
    if page_numbers is None:
        return list(range(page_count))
    return [
        page_no - 1 for page_no in sorted(page_numbers) if 1 <= page_no <= page_count
    ]
