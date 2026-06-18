from __future__ import annotations

import ipaddress
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast
from urllib.parse import urlparse

from trapo.ingest.llm_diagnostics import (
    LlmDiagnosticError,
    LlmDiagnosticRequest,
    LlmDiagnosticSuccess,
    begin_llm_diagnostic,
    record_llm_error,
    record_llm_success,
    start_llm_diagnostic_span,
)
from trapo.ingest.lmstudio_models import LmStudioPageResponse
from trapo.ingest.lmstudio_prompts import SYSTEM_PROMPT
from trapo.ingest.page_images import RenderedPageImage


ParsedResponseT = TypeVar("ParsedResponseT")
LOCALHOST_NAMES = {"localhost"}
BLOCKED_LLM_HOSTS = {"169.254.169.254"}


class HttpResponse(Protocol):
    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return {}


class HttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, Any],
    ) -> HttpResponse:
        del url, headers, json
        return cast(HttpResponse, None)

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class ChatPayloadRequest:
    model: str
    page: RenderedPageImage
    prompt: str
    max_tokens: int
    temperature: float
    schema_name: str = "trapo_page_regions"
    schema: dict[str, Any] | None = None
    system_prompt: str = SYSTEM_PROMPT
    include_image: bool = True
    structured_output: bool = True


def execute_chat_completion(
    client: HttpClient,
    *,
    endpoint: str,
    stage: str,
    request: ChatPayloadRequest,
    parse: Callable[[str, Any], ParsedResponseT],
) -> tuple[ParsedResponseT, dict[str, Any]]:
    payload = chat_payload(request)
    diagnostic_request = _diagnostic_request(endpoint, stage, request, payload)
    with start_llm_diagnostic_span(diagnostic_request) as span:
        diagnostic_context = begin_llm_diagnostic(diagnostic_request)
        try:
            parsed, response_json, content, status_code = _post_and_parse(
                client,
                endpoint=endpoint,
                payload=payload,
                parse=parse,
            )
        except Exception as exc:
            record_llm_error(
                diagnostic_context,
                error=LlmDiagnosticError(
                    exc=exc,
                    status_code=_exception_status_code(exc, None),
                    response_text=_exception_response_text(exc, None),
                    response_json=None,
                    span=span,
                ),
            )
            raise
        response_metadata = raw_response_metadata(response_json)
        record_llm_success(
            diagnostic_context,
            result=LlmDiagnosticSuccess(
                content=content,
                response_json=response_json,
                status_code=status_code,
                response_metadata=response_metadata,
                span=span,
            ),
        )
        return parsed, response_metadata


def _post_and_parse(
    client: HttpClient,
    *,
    endpoint: str,
    payload: dict[str, Any],
    parse: Callable[[str, Any], ParsedResponseT],
) -> tuple[ParsedResponseT, Any, str, int | None]:
    safe_endpoint = _validate_api_request_url(endpoint)
    response = client.post(
        safe_endpoint,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer lm-studio",
        },
        json=payload,
    )
    status_code = _response_status_code(response)
    response.raise_for_status()
    response_json = response.json()
    content = _completion_content(response_json)
    return parse(content, response_json), response_json, content, status_code


def chat_payload(request: ChatPayloadRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {
                "role": "user",
                "content": _user_message_content(request),
            },
        ],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": False,
    }
    if request.structured_output:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": request.schema_name,
                "strict": True,
                "schema": request.schema or LmStudioPageResponse.model_json_schema(),
            },
        }
    return payload


def raw_response_metadata(response_json: Any) -> dict[str, Any]:
    if not isinstance(response_json, dict):
        return {}
    return {
        key: response_json[key]
        for key in ("id", "model", "created", "usage", "stats")
        if key in response_json
    }


def _validate_api_request_url(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("LM Studio endpoint must be an HTTP(S) URL with a host.")
    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_LLM_HOSTS:
        raise ValueError("LM Studio endpoint cannot target metadata service hosts.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if hostname not in LOCALHOST_NAMES:
            raise ValueError(
                "LM Studio endpoint host must be localhost or an IP address."
            )
    else:
        if not (address.is_loopback or address.is_private):
            raise ValueError("LM Studio endpoint IP must be loopback or private.")
    return endpoint


def _diagnostic_request(
    endpoint: str,
    stage: str,
    request: ChatPayloadRequest,
    payload: dict[str, Any],
) -> LlmDiagnosticRequest:
    return LlmDiagnosticRequest(
        endpoint=endpoint,
        model=request.model,
        page=request.page if request.include_image else None,
        prompt=request.prompt,
        payload=payload,
        stage=stage,
        system_prompt=request.system_prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        structured_output=request.structured_output,
        schema_name=request.schema_name if request.structured_output else None,
    )


def _user_message_content(request: ChatPayloadRequest) -> str | list[dict[str, Any]]:
    if not request.include_image:
        return request.prompt
    return [
        {"type": "text", "text": request.prompt},
        {"type": "image_url", "image_url": {"url": request.page.data_url}},
    ]


def _completion_content(response_json: Any) -> str:
    if not isinstance(response_json, dict):
        raise RuntimeError("LM Studio returned a non-object response.")
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LM Studio response did not include choices.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("LM Studio response choice is not an object.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("LM Studio response choice did not include a message.")
    content = message.get("content")
    if isinstance(content, str):
        return content
    raise RuntimeError("LM Studio response message content was not a string.")


def _response_status_code(response: HttpResponse) -> int | None:
    value = getattr(response, "status_code", None)
    return int(value) if isinstance(value, int) else None


def _exception_status_code(exc: BaseException, fallback: int | None) -> int | None:
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return int(value) if isinstance(value, int) else fallback


def _exception_response_text(
    exc: BaseException,
    fallback: str | None,
) -> str | None:
    response = getattr(exc, "response", None)
    value = getattr(response, "text", None)
    return value if isinstance(value, str) else fallback
