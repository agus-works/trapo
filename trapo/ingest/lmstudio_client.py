from __future__ import annotations

import json
from typing import Any, Protocol, cast

import httpx

from trapo.ingest.lmstudio_chat import (
    ChatPayloadRequest,
    HttpClient,
    execute_chat_completion,
)
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_MODEL,
    DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
    LmStudioPageOrientationResponse,
    LmStudioPageMarkdownResponse,
    LmStudioPageResponse,
)
from trapo.ingest.lmstudio_prompts import (
    MARKDOWN_SYSTEM_PROMPT,
    ORIENTATION_SYSTEM_PROMPT,
)
from trapo.ingest.lmstudio_urls import normalize_lmstudio_base_url
from trapo.ingest.page_images import RenderedPageImage


MIN_MARKDOWN_FENCE_LINES = 2
CHAT_COMPLETIONS_PATH = "/chat/completions"
DEFAULT_LMSTUDIO_CONNECT_TIMEOUT_SECONDS = 30.0
DEFAULT_LMSTUDIO_WRITE_TIMEOUT_SECONDS = 60.0
DEFAULT_LMSTUDIO_POOL_TIMEOUT_SECONDS = 30.0


class PageRegionClient(Protocol):
    detect_page_regions: Any
    close: Any


class PageMarkdownClient(Protocol):
    generate_page_markdown: Any
    close: Any


class LmStudioStructuredOutputError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        model: str,
        raw_content: str,
        response_metadata: dict[str, Any],
        reason: str,
    ) -> None:
        self.stage = stage
        self.model = model
        self.raw_content = raw_content
        self.response_metadata = response_metadata
        self.reason = reason
        super().__init__(self.__str__())

    def __str__(self) -> str:
        stats = self.response_metadata.get("stats")
        usage = self.response_metadata.get("usage")
        details: list[str] = [self.reason]
        if isinstance(stats, dict) and stats:
            details.append(f"stats={stats}")
        if isinstance(usage, dict) and usage:
            details.append(f"usage={usage}")
        return f"LM Studio {self.stage} structured output error: {'; '.join(details)}"


class LmStudioClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_LMSTUDIO_BASE_URL,
        model: str = DEFAULT_LMSTUDIO_MODEL,
        timeout_seconds: float = DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
        http_client: HttpClient | None = None,
    ) -> None:
        self._base_url = normalize_lmstudio_base_url(base_url)
        self._model = model
        self._owns_client = http_client is None
        self._client: HttpClient = http_client or cast(
            HttpClient,
            httpx.Client(timeout=lmstudio_http_timeout(timeout_seconds)),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def detect_page_regions(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageResponse, dict[str, Any]]:
        return execute_chat_completion(
            self._client,
            endpoint=f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
            stage="page_regions",
            request=ChatPayloadRequest(
                model=self._model,
                page=page,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            ),
            parse=lambda content, _response_json: (
                LmStudioPageResponse.model_validate_json(_json_content(content))
            ),
        )

    def detect_page_orientation(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageOrientationResponse, dict[str, Any]]:
        return execute_chat_completion(
            self._client,
            endpoint=f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
            stage="page_orientation",
            request=ChatPayloadRequest(
                model=self._model,
                page=page,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                schema_name="trapo_page_orientation",
                schema=LmStudioPageOrientationResponse.model_json_schema(),
                system_prompt=ORIENTATION_SYSTEM_PROMPT,
            ),
            parse=lambda content, _response_json: (
                LmStudioPageOrientationResponse.model_validate_json(
                    _json_content(content)
                )
            ),
        )

    def generate_page_markdown(
        self,
        page: RenderedPageImage,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[LmStudioPageMarkdownResponse, dict[str, Any]]:
        return execute_chat_completion(
            self._client,
            endpoint=f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
            stage="page_markdown",
            request=ChatPayloadRequest(
                model=self._model,
                page=page,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                schema_name="trapo_page_markdown",
                system_prompt=MARKDOWN_SYSTEM_PROMPT,
                structured_output=False,
            ),
            parse=lambda content, _response_json: LmStudioPageMarkdownResponse(
                markdown=_markdown_content(content)
            ),
        )


def _json_content(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _markdown_content(content: str) -> str:
    stripped = content.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("markdown"), str):
        return str(parsed["markdown"]).strip()
    lines = stripped.splitlines()
    if (
        len(lines) >= MIN_MARKDOWN_FENCE_LINES
        and _is_markdown_fence(lines[0])
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _is_markdown_fence(line: str) -> bool:
    return line.strip().casefold() in {"```markdown", "```md"}


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
