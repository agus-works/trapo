from __future__ import annotations

import secrets


MAX_ATTRIBUTE_STRING_LENGTH = 2000
MAX_LLM_ATTRIBUTE_STRING_LENGTH = 1_000_000
MAX_ERROR_MESSAGE_LENGTH = 4000
MAX_ERROR_STACK_LENGTH = 12000
MAX_ATTRIBUTE_DEPTH = 4
MAX_LLM_ATTRIBUTE_DEPTH = 8
MAX_ATTRIBUTE_SEQUENCE_ITEMS = 100
CATEGORY_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("markdown",), "markdown"),
    (("lmstudio",), "lmstudio"),
    (("docling",), "docling"),
    (("mineru",), "mineru"),
    (("preview",), "preview"),
    (("fuse", "fusion"), "fusion"),
    (("region",), "regions"),
)


def safe_value(
    value: object,
    *,
    depth: int = 0,
    string_limit: int = MAX_ATTRIBUTE_STRING_LENGTH,
    depth_limit: int = MAX_ATTRIBUTE_DEPTH,
) -> object:
    result: object
    if value is None or isinstance(value, bool | int | float):
        result = value
    elif isinstance(value, str):
        result = truncate(value, string_limit)
    elif depth >= depth_limit:
        result = truncate(str(value), string_limit)
    elif isinstance(value, dict):
        result = {
            str(key): safe_value(
                item,
                depth=depth + 1,
                string_limit=string_limit,
                depth_limit=depth_limit,
            )
            for key, item in value.items()
            if item is not None
        }
    elif isinstance(value, list | tuple | set):
        result = [
            safe_value(
                item,
                depth=depth + 1,
                string_limit=string_limit,
                depth_limit=depth_limit,
            )
            for item in list(value)[:MAX_ATTRIBUTE_SEQUENCE_ITEMS]
        ]
    else:
        result = truncate(str(value), string_limit)
    return result


def str_attr(attributes: dict[str, object], key: str) -> str | None:
    value = attributes.get(key)
    return value if isinstance(value, str) and value else None


def int_attr(attributes: dict[str, object], key: str) -> int | None:
    value = attributes.get(key)
    result = None
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    return result


def step_from_name(name: str) -> str:
    prefix = "trapo.ingest."
    normalized = name.removeprefix(prefix).replace(".", "_").replace("-", "_")
    return normalized or name


def category_from_name(name: str) -> str:
    for keywords, category in CATEGORY_KEYWORDS:
        if any(keyword in name for keyword in keywords):
            return category
    return "pipeline"


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}... [truncated]"


def random_trace_id() -> str:
    return secrets.token_hex(16)


def random_span_id() -> str:
    return secrets.token_hex(8)
