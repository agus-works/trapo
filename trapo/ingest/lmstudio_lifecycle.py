from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import cast

import httpx

from trapo.ingest.lmstudio_context import (
    LmStudioContextInfo,
    ensure_lmstudio_max_context,
)
from trapo.ingest.lmstudio_models import DEFAULT_LMSTUDIO_BASE_URL
from trapo.ingest.lmstudio_native_models import LmStudioNativeClient
from trapo.ingest.lmstudio_unload import unload_lmstudio_model
from trapo.ingest.lmstudio_urls import lmstudio_native_base_url


@contextmanager
def lmstudio_model_lease(  # noqa: PLR0913
    *,
    base_url: str = DEFAULT_LMSTUDIO_BASE_URL,
    model: str,
    timeout_seconds: float,
    enabled: bool = True,
    unload_on_exit: bool = True,
    log: Callable[[str], None] | None = None,
) -> Iterator[LmStudioContextInfo | None]:
    context_info = ensure_lmstudio_max_context(
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
        log=log,
    )
    try:
        yield context_info
    finally:
        if unload_on_exit and enabled:
            _unload_model(
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                log=log,
            )


def _unload_model(
    *,
    base_url: str,
    model: str,
    timeout_seconds: float,
    log: Callable[[str], None] | None,
) -> None:
    native_base_url = lmstudio_native_base_url(base_url)
    client = cast(LmStudioNativeClient, httpx.Client(timeout=timeout_seconds))
    try:
        unload_lmstudio_model(client, native_base_url, model, log)
    finally:
        client.close()
