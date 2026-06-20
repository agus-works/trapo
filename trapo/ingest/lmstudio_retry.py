from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from trapo.ingest.lmstudio_client import PageRegionClient
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_ANNOTATION_MAX_TOKENS,
    DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
    LmStudioOptions,
    LmStudioPageResponse,
)
from trapo.ingest.lmstudio_prompts import page_prompt
from trapo.ingest.page_images import RenderedPageImage


RETRY_TOKEN_BUDGETS = (8192, 4096, 4096)


class LmStudioPageAttemptsError(RuntimeError):
    def __init__(self, *, page_no: int, attempts: list[dict[str, Any]]) -> None:
        self.page_no = page_no
        self.attempts = attempts
        super().__init__(
            f"LM Studio page {page_no} failed after {len(attempts)} attempt(s)."
        )


def detect_page_regions_with_retries(
    lmstudio: PageRegionClient,
    page: RenderedPageImage,
    *,
    options: LmStudioOptions,
    page_evidence: list[dict[str, Any]],
    log: Callable[[str], None] | None,
) -> tuple[LmStudioPageResponse, dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    max_attempts = max(0, options.retry_count) + 1
    base_prompt = page_prompt(
        page,
        page_evidence,
        profile_instructions=options.profile_instructions,
    )
    last_exc: Exception | None = None
    for attempt_index in range(1, max_attempts + 1):
        max_tokens = attempt_max_tokens(options.max_tokens, attempt_index)
        prompt = attempt_prompt(base_prompt, attempt_index)
        started_at = time.perf_counter()
        try:
            parsed, raw_response = lmstudio.detect_page_regions(
                page,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=options.temperature,
            )
        except Exception as exc:
            last_exc = exc
            elapsed_seconds = time.perf_counter() - started_at
            attempts.append(
                attempt_result(
                    attempt_index=attempt_index,
                    max_tokens=max_tokens,
                    elapsed_seconds=elapsed_seconds,
                    exc=exc,
                )
            )
            log_attempt_error(log, page.page_no, attempt_index, elapsed_seconds, exc)
            continue
        elapsed_seconds = time.perf_counter() - started_at
        attempts.append(
            {
                "attempt": attempt_index,
                "max_tokens": max_tokens,
                "elapsed_seconds": elapsed_seconds,
                "status": "ok",
                "region_count": len(parsed.regions),
                "response_metadata": raw_response,
            }
        )
        return parsed, raw_response, attempts
    if last_exc is not None:
        raise LmStudioPageAttemptsError(
            page_no=page.page_no, attempts=attempts
        ) from last_exc
    raise LmStudioPageAttemptsError(page_no=page.page_no, attempts=attempts)


def attempt_max_tokens(requested_tokens: int, attempt_index: int) -> int:
    if attempt_index <= 1:
        if requested_tokens == DEFAULT_LMSTUDIO_CONTEXT_TOKENS:
            return DEFAULT_LMSTUDIO_ANNOTATION_MAX_TOKENS
        return min(requested_tokens, DEFAULT_LMSTUDIO_ANNOTATION_MAX_TOKENS)
    retry_index = min(attempt_index - 2, len(RETRY_TOKEN_BUDGETS) - 1)
    return min(requested_tokens, RETRY_TOKEN_BUDGETS[retry_index])


def attempt_prompt(base_prompt: str, attempt_index: int) -> str:
    if attempt_index <= 1:
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        "Previous response was invalid or truncated JSON. Retry with compact valid "
        "JSON only. Use fewer regions if needed. Keep text short, avoid repetition, "
        "and return a complete object matching the schema."
    )


def attempt_result(
    *,
    attempt_index: int,
    max_tokens: int,
    elapsed_seconds: float,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "attempt": attempt_index,
        "max_tokens": max_tokens,
        "elapsed_seconds": elapsed_seconds,
        "status": "error",
        "error_type": type(exc).__name__,
        "error": str(exc)[:2000],
    }


def attempts_from_exception(exc: Exception) -> list[dict[str, Any]]:
    attempts = getattr(exc, "attempts", None)
    return attempts if isinstance(attempts, list) else []


def page_error_type(exc: Exception) -> str:
    cause = exc.__cause__
    if isinstance(exc, LmStudioPageAttemptsError) and isinstance(cause, Exception):
        return type(cause).__name__
    return type(exc).__name__


def page_error_message(exc: Exception) -> str:
    cause = exc.__cause__
    if isinstance(exc, LmStudioPageAttemptsError) and isinstance(cause, Exception):
        return str(cause)
    return str(exc)


def log_attempt_error(
    log: Callable[[str], None] | None,
    page_no: int,
    attempt_index: int,
    elapsed_seconds: float,
    exc: Exception,
) -> None:
    if log is not None:
        log(
            "LM Studio page attempt failed: "
            f"page={page_no} attempt={attempt_index} "
            f"elapsed={elapsed_seconds:.2f}s error={exc}"
        )
