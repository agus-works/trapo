from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
from PIL import Image

from trapo.ingest.infinity_models import InfinityOptions
from trapo.ingest.lmstudio_context import ensure_lmstudio_max_context
from trapo.ingest.lmstudio_chat import (
    ChatPayloadRequest,
    HttpClient,
    execute_chat_completion,
)
from trapo.ingest.lmstudio_client import CHAT_COMPLETIONS_PATH, lmstudio_http_timeout
from trapo.ingest.lmstudio_models import (
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_LMSTUDIO_TIMEOUT_SECONDS,
)
from trapo.ingest.lmstudio_urls import normalize_lmstudio_base_url
from trapo.ingest.page_images import RenderedPageImage


INFINITY_JSON_PROMPT = """Extract layout information from the provided document image.
For each layout element, output bbox, category, and text.
Bbox format must be [x1, y1, x2, y2].
Allowed categories: header, title, text, figure, table, formula, figure_caption,
table_caption, formula_caption, figure_footnote, table_footnote, page_footnote,
footer.
For tables, format text as HTML. For formulas, format text as LaTeX.
Return only a JSON array sorted in human reading order."""

INFINITY_MARKDOWN_PROMPT = """Convert the provided document image to faithful Markdown.
Preserve visible reading order, headings, paragraphs, lists, tables, formulas,
line breaks that affect meaning, and document structure. Return only Markdown."""

INFINITY_LMSTUDIO_SYSTEM_PROMPT = (
    "You are Infinity Parser2 Flash running as a document parsing engine. "
    "Follow the requested output format exactly."
)
DEFAULT_INFINITY_MAX_TOKENS = 32768


class LmStudioInfinityParser:
    def __init__(self, options: InfinityOptions) -> None:
        self._options = options
        self._base_url = normalize_lmstudio_base_url(DEFAULT_LMSTUDIO_BASE_URL)
        ensure_lmstudio_max_context(
            base_url=self._base_url,
            model=self._options.model,
            timeout_seconds=min(DEFAULT_LMSTUDIO_TIMEOUT_SECONDS, 60.0),
        )
        self._client = cast(
            HttpClient,
            httpx.Client(
                timeout=lmstudio_http_timeout(DEFAULT_LMSTUDIO_TIMEOUT_SECONDS)
            ),
        )

    def parse(self, source: object, **kwargs: Any) -> object:
        paths = _source_paths(source)
        results = [
            self._parse_path(path, task_type=str(kwargs.get("task_type") or "doc2json"))
            for path in paths
        ]
        if isinstance(source, list):
            return results
        return results[0] if results else ""

    def _parse_path(self, path: Path, *, task_type: str) -> str:
        page = _rendered_page_from_path(path)
        prompt = _prompt_for_task(task_type)
        parsed, _metadata = execute_chat_completion(
            self._client,
            endpoint=f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
            stage=f"infinity_{task_type}",
            request=ChatPayloadRequest(
                model=self._options.model,
                page=page,
                prompt=prompt,
                max_tokens=DEFAULT_INFINITY_MAX_TOKENS,
                temperature=0.0,
                system_prompt=INFINITY_LMSTUDIO_SYSTEM_PROMPT,
                structured_output=False,
            ),
            parse=lambda content, _response_json: _content_for_task(
                content,
                task_type=task_type,
            ),
        )
        return parsed


def _source_paths(source: object) -> list[Path]:
    if isinstance(source, str):
        return [Path(source)]
    if isinstance(source, list):
        return [Path(item) for item in source if isinstance(item, str)]
    raise TypeError(
        f"Infinity LM Studio backend requires file paths, got {type(source)}"
    )


def _rendered_page_from_path(path: Path) -> RenderedPageImage:
    image_bytes = path.read_bytes()
    with Image.open(path) as image:
        width, height = image.size
        mime_type = Image.MIME.get(image.format or "JPEG", "image/jpeg")
    return RenderedPageImage(
        page_no=1,
        width=float(width),
        height=float(height),
        render_width=width,
        render_height=height,
        mime_type=mime_type,
        image_bytes=image_bytes,
        image_sha256="",
    )


def _prompt_for_task(task_type: str) -> str:
    if task_type == "doc2md":
        return INFINITY_MARKDOWN_PROMPT
    return INFINITY_JSON_PROMPT


def _content_for_task(content: str, *, task_type: str) -> str:
    text = _strip_code_fence(content)
    if task_type == "doc2json":
        return _json_array_text(text)
    return text


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _json_array_text(content: str) -> str:
    result = content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        result = json.dumps(parsed, ensure_ascii=False)
    elif isinstance(parsed, dict) and isinstance(parsed.get("elements"), list):
        result = json.dumps(parsed["elements"], ensure_ascii=False)
    return result
