from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from trapo.ingest.lmstudio_context import (
    LmStudioContextInfo,
    ensure_lmstudio_max_context,
    lmstudio_native_base_url,
    resolve_markdown_max_tokens,
)
from trapo.ingest.lmstudio_models import DEFAULT_LMSTUDIO_CONTEXT_TOKENS
from trapo.ingest.lmstudio_urls import normalize_lmstudio_base_url


CONTEXT_TOKENS = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
EXPLICIT_LOWER_MARKDOWN_TOKENS = 8192
EXPLICIT_HIGHER_MARKDOWN_TOKENS = DEFAULT_LMSTUDIO_CONTEXT_TOKENS + 1
SMALL_CONTEXT = 4096
CONTEXT_RESERVE_TOKENS = 1024


def test_ensure_lmstudio_max_context_loads_advertised_max_when_not_loaded() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": "google/gemma-4-26b-a4b-qat",
                    "max_context_length": CONTEXT_TOKENS,
                    "loaded_instances": [],
                }
            ]
        },
        load_response={
            "status": "loaded",
            "load_config": {"context_length": CONTEXT_TOKENS},
        },
    )

    info = ensure_lmstudio_max_context(http_client=client)

    assert info.max_context_tokens == CONTEXT_TOKENS
    assert info.loaded_context_tokens is None
    assert info.applied_context_tokens == CONTEXT_TOKENS
    assert info.load_attempted is True
    assert info.load_status == "loaded_max"
    assert client.post_payloads == [
        {
            "model": "google/gemma-4-26b-a4b-qat",
            "context_length": CONTEXT_TOKENS,
            "echo_load_config": True,
        }
    ]


def test_ensure_lmstudio_max_context_does_not_reload_when_already_at_max() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": "google/gemma-4-26b-a4b-qat",
                    "max_context_length": CONTEXT_TOKENS,
                    "loaded_instances": [
                        {"load_config": {"context_length": CONTEXT_TOKENS}}
                    ],
                }
            ]
        },
        load_response={},
    )

    info = ensure_lmstudio_max_context(http_client=client)

    assert info.max_context_tokens == CONTEXT_TOKENS
    assert info.loaded_context_tokens == CONTEXT_TOKENS
    assert info.applied_context_tokens is None
    assert info.load_attempted is False
    assert info.load_status == "already_max"
    assert client.post_payloads == []


def test_ensure_lmstudio_max_context_unloads_other_active_models() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": "other/model",
                    "loaded_instances": [{"load_config": {"context_length": 4096}}],
                },
                {
                    "key": "google/gemma-4-26b-a4b-qat",
                    "max_context_length": CONTEXT_TOKENS,
                    "loaded_instances": [
                        {"load_config": {"context_length": CONTEXT_TOKENS}}
                    ],
                },
            ]
        },
        load_response={},
    )

    info = ensure_lmstudio_max_context(http_client=client)

    assert info.load_status == "already_max"
    assert client.unload_payloads == [{"model": "other/model"}]
    assert client.post_payloads == []


def test_lmstudio_native_base_url_strips_openai_suffix() -> None:
    assert (
        lmstudio_native_base_url("http://localhost:1234/v1") == "http://localhost:1234"
    )
    assert (
        lmstudio_native_base_url("http://localhost:1234/api/v1")
        == "http://localhost:1234"
    )


def test_resolve_markdown_max_tokens_expands_default_to_context_budget() -> None:
    context = LmStudioContextInfo(
        model="test-model",
        base_url="http://localhost:1234/v1",
        native_base_url="http://localhost:1234",
        max_context_tokens=CONTEXT_TOKENS,
        applied_context_tokens=CONTEXT_TOKENS,
    )

    assert (
        resolve_markdown_max_tokens(
            requested_tokens=DEFAULT_LMSTUDIO_CONTEXT_TOKENS,
            context_info=context,
        )
        == CONTEXT_TOKENS - 1024
    )


def test_resolve_markdown_max_tokens_honors_explicit_lower_cap() -> None:
    context = LmStudioContextInfo(
        model="test-model",
        base_url="http://localhost:1234/v1",
        native_base_url="http://localhost:1234",
        max_context_tokens=CONTEXT_TOKENS,
        applied_context_tokens=CONTEXT_TOKENS,
    )

    assert (
        resolve_markdown_max_tokens(
            requested_tokens=EXPLICIT_LOWER_MARKDOWN_TOKENS,
            context_info=context,
        )
        == EXPLICIT_LOWER_MARKDOWN_TOKENS
    )


def test_resolve_markdown_max_tokens_caps_explicit_higher_value() -> None:
    context = LmStudioContextInfo(
        model="test-model",
        base_url="http://localhost:1234/v1",
        native_base_url="http://localhost:1234",
        max_context_tokens=SMALL_CONTEXT,
        applied_context_tokens=SMALL_CONTEXT,
    )

    assert (
        resolve_markdown_max_tokens(
            requested_tokens=EXPLICIT_HIGHER_MARKDOWN_TOKENS,
            context_info=context,
        )
        == SMALL_CONTEXT - CONTEXT_RESERVE_TOKENS
    )


def test_normalize_lmstudio_base_url_rejects_unsafe_urls() -> None:
    rejected_urls = [
        "file:///tmp/socket",
        "http://user:pass@localhost:1234/v1",
        "http://localhost:1234/v1?token=value",
        "http://localhost:1234/v1#fragment",
    ]

    for url in rejected_urls:
        with pytest.raises(ValueError):
            normalize_lmstudio_base_url(url)


class _FakeContextClient:
    def __init__(
        self, *, model_info: dict[str, Any], load_response: dict[str, Any]
    ) -> None:
        self.model_info = model_info
        self.load_response = load_response
        self.post_payloads: list[dict[str, Any]] = []
        self.unload_payloads: list[dict[str, Any]] = []

    def get(self, url: str, *, headers: Mapping[str, str]) -> _FakeResponse:
        assert headers["Authorization"] == "Bearer lm-studio"
        assert url.endswith("/api/v1/models")
        return _FakeResponse(self.model_info)

    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> _FakeResponse:
        assert headers["Authorization"] == "Bearer lm-studio"
        if url.endswith("/api/v1/models/unload"):
            self.unload_payloads.append(dict(json))
            return _FakeResponse({"status": "unloaded"})
        assert url.endswith("/api/v1/models/load")
        self.post_payloads.append(dict(json))
        return _FakeResponse(self.load_response)

    def close(self) -> None:
        pass


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        pass
