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
from trapo.ingest.lmstudio_unload import unload_lmstudio_model
from trapo.ingest.lmstudio_urls import normalize_lmstudio_base_url


CONTEXT_TOKENS = DEFAULT_LMSTUDIO_CONTEXT_TOKENS
EXPLICIT_LOWER_MARKDOWN_TOKENS = 8192
EXPLICIT_HIGHER_MARKDOWN_TOKENS = DEFAULT_LMSTUDIO_CONTEXT_TOKENS + 1
SMALL_CONTEXT = 4096
LMSTUDIO_DEFAULT_CONTEXT = 2048
OLMOCR_CONTEXT_TOKENS = 128_000
CONTEXT_RESERVE_TOKENS = 1024
EXPECTED_LOAD_RETRY_CALLS = 2
INFINITY_LMSTUDIO_MODEL = "infinity-parser2-flash"
GEMMA_MODEL = "google/gemma-4-26b-a4b-qat"


def test_ensure_lmstudio_max_context_loads_advertised_max_when_not_loaded() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
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
            "model": INFINITY_LMSTUDIO_MODEL,
            "context_length": CONTEXT_TOKENS,
            "echo_load_config": True,
        }
    ]


def test_ensure_lmstudio_max_context_uses_supported_model_floor() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": GEMMA_MODEL,
                    "max_context_length": SMALL_CONTEXT,
                    "loaded_instances": [
                        {
                            "id": "supported-low-context",
                            "load_config": {"context_length": SMALL_CONTEXT},
                        }
                    ],
                }
            ]
        },
        load_response={
            "status": "loaded",
            "config": {"context_length": CONTEXT_TOKENS},
        },
    )

    info = ensure_lmstudio_max_context(model=GEMMA_MODEL, http_client=client)

    assert info.max_context_tokens == CONTEXT_TOKENS
    assert info.loaded_context_tokens == SMALL_CONTEXT
    assert info.applied_context_tokens == CONTEXT_TOKENS
    assert client.unload_payloads == [{"instance_id": "supported-low-context"}]
    assert client.post_payloads == [
        {
            "model": GEMMA_MODEL,
            "context_length": CONTEXT_TOKENS,
            "echo_load_config": True,
        }
    ]


def test_ensure_lmstudio_max_context_forces_known_max_when_lmstudio_reports_default_context() -> (
    None
):
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "max_context_length": LMSTUDIO_DEFAULT_CONTEXT,
                    "loaded_instances": [
                        {
                            "id": "infinity-default-context",
                            "load_config": {"context_length": LMSTUDIO_DEFAULT_CONTEXT},
                        }
                    ],
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
    assert info.loaded_context_tokens == LMSTUDIO_DEFAULT_CONTEXT
    assert info.applied_context_tokens == CONTEXT_TOKENS
    assert client.unload_payloads == [{"instance_id": "infinity-default-context"}]
    assert client.post_payloads == [
        {
            "model": INFINITY_LMSTUDIO_MODEL,
            "context_length": CONTEXT_TOKENS,
            "echo_load_config": True,
        }
    ]


def test_ensure_lmstudio_max_context_fails_when_loaded_context_stays_low() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "max_context_length": LMSTUDIO_DEFAULT_CONTEXT,
                    "loaded_instances": [
                        {
                            "id": "infinity-default-context",
                            "load_config": {"context_length": LMSTUDIO_DEFAULT_CONTEXT},
                        }
                    ],
                }
            ]
        },
        load_response={"load_config": {"context_length": CONTEXT_TOKENS}},
    )
    client.loaded_context_override = LMSTUDIO_DEFAULT_CONTEXT

    info = ensure_lmstudio_max_context(http_client=client)

    assert info.load_status == "verification_failed"
    assert info.max_context_tokens == CONTEXT_TOKENS
    assert info.loaded_context_tokens == LMSTUDIO_DEFAULT_CONTEXT
    assert len(client.post_payloads) == EXPECTED_LOAD_RETRY_CALLS


def test_ensure_lmstudio_max_context_forces_infinity_parser_known_max() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "loaded_instances": [],
                }
            ]
        },
        load_response={
            "status": "loaded",
            "load_config": {"context_length": CONTEXT_TOKENS},
        },
    )

    info = ensure_lmstudio_max_context(
        model=INFINITY_LMSTUDIO_MODEL,
        http_client=client,
    )

    assert info.max_context_tokens == CONTEXT_TOKENS
    assert info.applied_context_tokens == CONTEXT_TOKENS
    assert client.post_payloads == [
        {
            "model": INFINITY_LMSTUDIO_MODEL,
            "context_length": CONTEXT_TOKENS,
            "echo_load_config": True,
        }
    ]


def test_ensure_lmstudio_max_context_accepts_v0_model_list_shape() -> None:
    client = _FakeContextClient(
        model_info={
            "data": [
                {
                    "id": "allenai/olmocr-2-7b",
                    "max_context_length": OLMOCR_CONTEXT_TOKENS,
                    "state": "not-loaded",
                }
            ]
        },
        load_response={"config": {"context_length": OLMOCR_CONTEXT_TOKENS}},
    )

    info = ensure_lmstudio_max_context(
        model="allenai/olmocr-2-7b",
        http_client=client,
    )

    assert info.max_context_tokens == OLMOCR_CONTEXT_TOKENS
    assert info.applied_context_tokens == OLMOCR_CONTEXT_TOKENS
    assert client.post_payloads == [
        {
            "model": "allenai/olmocr-2-7b",
            "context_length": OLMOCR_CONTEXT_TOKENS,
            "echo_load_config": True,
        }
    ]


def test_ensure_lmstudio_max_context_does_not_reload_when_already_at_max() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "max_context_length": CONTEXT_TOKENS,
                    "loaded_instances": [
                        {
                            "load_config": {
                                "context_length": CONTEXT_TOKENS,
                                "repeat_penalty": 1.2,
                            }
                        }
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
                    "loaded_instances": [
                        {
                            "instance_id": "other-instance",
                            "load_config": {"context_length": 4096},
                        }
                    ],
                },
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "max_context_length": CONTEXT_TOKENS,
                    "loaded_instances": [
                        {
                            "load_config": {
                                "context_length": CONTEXT_TOKENS,
                                "repeat_penalty": 1.2,
                            }
                        }
                    ],
                },
            ]
        },
        load_response={},
    )

    info = ensure_lmstudio_max_context(http_client=client)

    assert info.load_status == "already_max"
    assert client.unload_payloads == [{"instance_id": "other-instance"}]
    assert client.post_payloads == []


def test_ensure_lmstudio_max_context_unload_falls_back_to_model_key() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": "other/model",
                    "loaded_instances": [{"load_config": {"context_length": 4096}}],
                },
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "max_context_length": CONTEXT_TOKENS,
                    "loaded_instances": [
                        {
                            "load_config": {
                                "context_length": CONTEXT_TOKENS,
                                "repeat_penalty": 1.2,
                            }
                        }
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


def test_unload_lmstudio_model_unloads_target_instances() -> None:
    client = _FakeContextClient(
        model_info={
            "models": [
                {
                    "key": GEMMA_MODEL,
                    "loaded_instances": [{"id": "supported-instance"}],
                },
                {
                    "key": INFINITY_LMSTUDIO_MODEL,
                    "loaded_instances": [{"id": "infinity-instance"}],
                },
            ]
        },
        load_response={},
    )

    unload_lmstudio_model(
        client,
        "http://localhost:1234",
        GEMMA_MODEL,
    )

    assert client.unload_payloads == [{"instance_id": "supported-instance"}]


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
        self.loaded_model: str | None = None
        self.loaded_context: int | None = None
        self.loaded_context_override: int | None = None
        self.post_payloads: list[dict[str, Any]] = []
        self.unload_payloads: list[dict[str, Any]] = []

    def get(self, url: str, *, headers: Mapping[str, str]) -> _FakeResponse:
        assert headers["Authorization"] == "Bearer lm-studio"
        assert url.endswith("/api/v1/models")
        if self.loaded_model is not None and self.loaded_context is not None:
            return _FakeResponse(
                {
                    "models": [
                        {
                            "key": self.loaded_model,
                            "loaded_instances": [
                                {
                                    "id": f"{self.loaded_model}-instance",
                                    "load_config": {
                                        "context_length": self.loaded_context,
                                    },
                                }
                            ],
                        }
                    ]
                }
            )
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
            self.loaded_model = None
            self.loaded_context = None
            return _FakeResponse({"status": "unloaded"})
        assert url.endswith("/api/v1/models/load")
        payload = dict(json)
        self.post_payloads.append(payload)
        self.loaded_model = str(payload["model"])
        self.loaded_context = self.loaded_context_override or int(
            payload["context_length"]
        )
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
