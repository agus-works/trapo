from __future__ import annotations

import httpx


CHAT_COMPLETIONS_PATH = "/chat/completions"
DEFAULT_LMSTUDIO_CONNECT_TIMEOUT_SECONDS = 30.0
DEFAULT_LMSTUDIO_WRITE_TIMEOUT_SECONDS = 60.0
DEFAULT_LMSTUDIO_POOL_TIMEOUT_SECONDS = 30.0


def lmstudio_http_timeout(timeout_seconds: float) -> httpx.Timeout:
    """Build HTTP timeouts for local non-streamed LM Studio generation."""
    if timeout_seconds <= 0:
        raise ValueError("LM Studio timeout must be greater than zero seconds.")
    return httpx.Timeout(
        connect=min(DEFAULT_LMSTUDIO_CONNECT_TIMEOUT_SECONDS, timeout_seconds),
        read=timeout_seconds,
        write=min(DEFAULT_LMSTUDIO_WRITE_TIMEOUT_SECONDS, timeout_seconds),
        pool=min(DEFAULT_LMSTUDIO_POOL_TIMEOUT_SECONDS, timeout_seconds),
    )
