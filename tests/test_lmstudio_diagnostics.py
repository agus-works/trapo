from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import httpx

from trapo.config import RuntimeConfig
from trapo.db import connect
from trapo.diagnostics import activate_diagnostic_run, deactivate_diagnostic_run
from trapo.ingest.lmstudio_chat import (
    ChatPayloadRequest,
    HttpClient,
    execute_chat_completion,
)
from trapo.ingest.lmstudio_client import CHAT_COMPLETIONS_PATH
from trapo.ingest.lmstudio_models import DEFAULT_LMSTUDIO_CONTEXT_TOKENS
from trapo.ingest.page_images import RenderedPageImage
from trapo.migrations import apply_migrations


HTTP_BAD_REQUEST = 400


def test_lmstudio_call_records_request_response_and_attachment(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "TRAPO_LLM_DIAGNOSTICS_CACHE_ROOT",
        str(tmp_path / "llm-diagnostics"),
    )
    db_path = tmp_path / "trapo.duckdb"
    page = _page()

    with connect(db_path) as connection:
        apply_migrations(
            connection,
            RuntimeConfig.from_env(db_path=str(db_path)),
            create_backup=False,
        )
        activate_diagnostic_run(connection, 7)
        try:
            response, _raw = _chat_completion(
                _SuccessHttpClient("# Receipt\n\nTotal 42.00"),
                page=page,
            )
        finally:
            deactivate_diagnostic_run()

        events = _events(connection)
        spans = connection.execute(
            "SELECT pipeline_step, page_no, status FROM ingest_diagnostic_spans"
        ).fetchall()

    assert response == "# Receipt\n\nTotal 42.00"
    assert [event["name"] for event in events] == ["llm.request", "llm.response"]
    request_attrs = events[0]["attributes_json"]
    assert request_attrs["llm.request.prompt"] == "Return only Markdown for this page."
    assert (
        request_attrs["llm.request.parameters"]["max_tokens"]
        == DEFAULT_LMSTUDIO_CONTEXT_TOKENS
    )
    assert "data:image" not in json.dumps(request_attrs["llm.request.payload"])
    attachment_path = Path(request_attrs["llm.attachment"]["file_path"])
    assert attachment_path.exists()
    assert attachment_path.read_bytes() == page.image_bytes
    response_attrs = events[1]["attributes_json"]
    assert response_attrs["llm.response.content"] == "# Receipt\n\nTotal 42.00"
    assert response_attrs["llm.response.raw_json"]["choices"][0]["message"]["content"]
    assert spans == [("lmstudio_chat_completion", 3, "ok")]


def test_lmstudio_http_error_records_status_and_response_body(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "TRAPO_LLM_DIAGNOSTICS_CACHE_ROOT",
        str(tmp_path / "llm-diagnostics"),
    )
    db_path = tmp_path / "trapo.duckdb"

    with connect(db_path) as connection:
        apply_migrations(
            connection,
            RuntimeConfig.from_env(db_path=str(db_path)),
            create_backup=False,
        )
        activate_diagnostic_run(connection, 8)
        try:
            try:
                _chat_completion(_ErrorHttpClient("context window exceeded"))
            except httpx.HTTPStatusError:
                pass
        finally:
            deactivate_diagnostic_run()

        events = _events(connection)
        spans = connection.execute(
            "SELECT pipeline_step, page_no, status FROM ingest_diagnostic_spans"
        ).fetchall()

    assert [event["name"] for event in events] == [
        "llm.request",
        "llm.error",
        "exception",
    ]
    error_attrs = events[1]["attributes_json"]
    assert error_attrs["llm.error.status_code"] == HTTP_BAD_REQUEST
    assert error_attrs["llm.error.response_text"] == "context window exceeded"
    assert error_attrs["llm.error.type"] == "HTTPStatusError"
    assert spans == [("lmstudio_chat_completion", 3, "error")]


def _chat_completion(
    http_client: object,
    *,
    page: RenderedPageImage | None = None,
) -> tuple[str, dict[str, Any]]:
    return execute_chat_completion(
        cast(HttpClient, http_client),
        endpoint=f"http://localhost:1234/v1{CHAT_COMPLETIONS_PATH}",
        stage="infinity_doc2md",
        request=ChatPayloadRequest(
            model="test-model",
            page=page or _page(),
            prompt="Return only Markdown for this page.",
            max_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
            temperature=0.0,
            structured_output=False,
        ),
        parse=lambda content, _response_json: content,
    )


def _page() -> RenderedPageImage:
    return RenderedPageImage(
        page_no=3,
        width=120,
        height=60,
        render_width=80,
        render_height=40,
        mime_type="image/jpeg",
        image_bytes=b"fake-jpeg",
        image_sha256="7bb242b6e4655937b76b10b3bd14aa0dc4fe4a078516cbc8a0b36d572996fd71",
    )


def _events(connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT name, event_type, severity, page_no, attributes_json
        FROM ingest_diagnostic_events
        ORDER BY event_id
        """
    ).fetchall()
    return [
        {
            "name": str(row[0]),
            "event_type": str(row[1]),
            "severity": str(row[2]),
            "page_no": row[3],
            "attributes_json": json.loads(str(row[4])),
        }
        for row in rows
    ]


class _SuccessHttpResponse:
    status_code = 200

    def __init__(self, content: str) -> None:
        self._content = content
        self.text = json.dumps(self.json())

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": self._content}}],
            "id": "chatcmpl-test",
            "model": "test-model",
            "usage": {"total_tokens": 12},
        }


class _SuccessHttpClient:
    def __init__(self, content: str) -> None:
        self._content = content

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> _SuccessHttpResponse:
        del url, headers, json
        return _SuccessHttpResponse(self._content)

    def close(self) -> None:
        return None


class _ErrorHttpResponse:
    status_code = HTTP_BAD_REQUEST

    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        request = httpx.Request("POST", "http://127.0.0.1:1234/v1/chat/completions")
        response = httpx.Response(self.status_code, text=self.text, request=request)
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    def json(self) -> dict[str, Any]:
        return {}


class _ErrorHttpClient:
    def __init__(self, text: str) -> None:
        self._text = text

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> _ErrorHttpResponse:
        del url, headers, json
        return _ErrorHttpResponse(self._text)

    def close(self) -> None:
        return None
