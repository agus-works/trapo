from __future__ import annotations


MIN_USEFUL_MARKDOWN_CHARS = 8
UNUSABLE_MARKDOWN_VALUES = frozenset({"", "n/a", "na", "none", "null", "not available"})


def is_usable_markdown_text(value: str) -> bool:
    normalized = " ".join(value.split()).casefold()
    return (
        len(normalized) >= MIN_USEFUL_MARKDOWN_CHARS
        and normalized not in UNUSABLE_MARKDOWN_VALUES
    )


def int_value(value: object) -> int:
    result = 0
    if isinstance(value, bool | int | float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            result = 0
    return result


def float_or_none(value: object) -> float | None:
    result: float | None = None
    if isinstance(value, bool | int | float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            result = None
    return result
