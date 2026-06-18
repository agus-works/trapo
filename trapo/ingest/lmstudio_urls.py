from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


ALLOWED_LMSTUDIO_URL_SCHEMES = {"http", "https"}
LMSTUDIO_NATIVE_SUFFIXES = ("/api/v1", "/api/v0", "/v1")


def normalize_lmstudio_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in ALLOWED_LMSTUDIO_URL_SCHEMES:
        raise ValueError("LM Studio base URL must use http or https.")
    if not parsed.hostname:
        raise ValueError("LM Studio base URL must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("LM Studio base URL must not include credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("LM Studio base URL must not include query or fragment data.")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def lmstudio_native_base_url(base_url: str) -> str:
    normalized = normalize_lmstudio_base_url(base_url)
    for suffix in LMSTUDIO_NATIVE_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized
