from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from trapo.diagnostics import DiagnosticAttributes, record_diagnostic_event
from trapo.diagnostics_values import (
    MAX_LLM_ATTRIBUTE_DEPTH,
    MAX_LLM_ATTRIBUTE_STRING_LENGTH,
)
from trapo.ingest.llm_diagnostic_payloads import (
    attachment_metadata,
    sanitized_payload,
)
from trapo.ingest.page_images import RenderedPageImage
from trapo.observability import span_set_attributes, traced_span


LLM_PROVIDER = "lmstudio"


@dataclass(frozen=True)
class LlmDiagnosticRequest:
    endpoint: str
    model: str
    page: RenderedPageImage | None
    prompt: str
    payload: dict[str, Any]
    stage: str
    system_prompt: str
    max_tokens: int
    temperature: float
    structured_output: bool
    schema_name: str | None


@dataclass(frozen=True)
class LlmDiagnosticContext:
    attachment: dict[str, object] | None
    request: LlmDiagnosticRequest
    sanitized_payload: dict[str, Any]
    started_perf: float


@dataclass(frozen=True)
class LlmDiagnosticSuccess:
    content: str
    response_json: Any
    status_code: int | None
    response_metadata: dict[str, Any]
    span: Any


@dataclass(frozen=True)
class LlmDiagnosticError:
    exc: BaseException
    status_code: int | None
    response_text: str | None
    response_json: Any | None
    span: Any


def start_llm_diagnostic_span(request: LlmDiagnosticRequest) -> Any:
    page = request.page
    attributes: dict[str, object] = {
        "pipeline.category": "lmstudio",
        "pipeline.step": "lmstudio_chat_completion",
        "llm.provider": LLM_PROVIDER,
        "llm.stage": request.stage,
        "llm.endpoint": request.endpoint,
        "llm.model": request.model,
        "llm.request.max_tokens": request.max_tokens,
        "llm.request.temperature": request.temperature,
        "llm.request.structured_output": request.structured_output,
    }
    if request.schema_name:
        attributes["llm.request.schema_name"] = request.schema_name
    if page is not None:
        attributes.update(
            {
                "page.no": page.page_no,
                "llm.attachment.mime_type": page.mime_type,
                "llm.attachment.sha256": page.image_sha256,
                "llm.attachment.bytes": len(page.image_bytes),
                "llm.attachment.render_width": page.render_width,
                "llm.attachment.render_height": page.render_height,
            }
        )
    return traced_span("trapo.ingest.lmstudio.chat_completion", attributes=attributes)


def begin_llm_diagnostic(request: LlmDiagnosticRequest) -> LlmDiagnosticContext:
    attachment = attachment_metadata(request.page, request.stage, request.model)
    payload = sanitized_payload(request.payload, attachment)
    context = LlmDiagnosticContext(
        attachment=attachment,
        request=request,
        sanitized_payload=payload,
        started_perf=perf_counter(),
    )
    record_diagnostic_event(
        "llm.request",
        message=_event_message("request", request, None),
        severity="info",
        event_type="llm.request",
        attributes=_large_attributes(_request_attributes(context)),
    )
    return context


def record_llm_success(
    context: LlmDiagnosticContext,
    *,
    result: LlmDiagnosticSuccess,
) -> None:
    elapsed_ms = _elapsed_ms(context)
    record_diagnostic_event(
        "llm.response",
        message=_event_message("response", context.request, result.status_code),
        severity="info",
        event_type="llm.response",
        attributes=_large_attributes(
            {
                **_common_attributes(context),
                "llm.response.status_code": result.status_code,
                "llm.response.elapsed_ms": elapsed_ms,
                "llm.response.content": result.content,
                "llm.response.metadata": result.response_metadata,
                "llm.response.raw_json": result.response_json,
            }
        ),
    )
    span_set_attributes(
        result.span,
        {
            "llm.response.status_code": result.status_code,
            "llm.response.elapsed_ms": elapsed_ms,
            "llm.response.content_length": len(result.content),
            "llm.response.id": result.response_metadata.get("id"),
        },
    )


def record_llm_error(
    context: LlmDiagnosticContext,
    *,
    error: LlmDiagnosticError,
) -> None:
    elapsed_ms = _elapsed_ms(context)
    record_diagnostic_event(
        "llm.error",
        message=_event_message("error", context.request, error.status_code),
        severity="error",
        event_type="llm.error",
        attributes=_large_attributes(
            {
                **_common_attributes(context),
                "llm.error.type": error.exc.__class__.__name__,
                "llm.error.message": str(error.exc),
                "llm.error.status_code": error.status_code,
                "llm.error.elapsed_ms": elapsed_ms,
                "llm.error.response_text": error.response_text,
                "llm.error.response_json": error.response_json,
            }
        ),
    )
    span_set_attributes(
        error.span,
        {
            "ingest.status": "error",
            "llm.error.type": error.exc.__class__.__name__,
            "llm.error.status_code": error.status_code,
            "llm.error.elapsed_ms": elapsed_ms,
        },
    )


def _request_attributes(context: LlmDiagnosticContext) -> dict[str, object]:
    request = context.request
    return {
        **_common_attributes(context),
        "llm.request.parameters": {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": bool(request.payload.get("stream")),
            "structured_output": request.structured_output,
            "schema_name": request.schema_name,
        },
        "llm.request.system_prompt": request.system_prompt,
        "llm.request.prompt": request.prompt,
        "llm.request.payload": context.sanitized_payload,
    }


def _large_attributes(attributes: dict[str, object]) -> DiagnosticAttributes:
    return DiagnosticAttributes(
        attributes, MAX_LLM_ATTRIBUTE_STRING_LENGTH, MAX_LLM_ATTRIBUTE_DEPTH
    )


def _common_attributes(context: LlmDiagnosticContext) -> dict[str, object]:
    request = context.request
    attributes: dict[str, object] = {
        "llm.provider": LLM_PROVIDER,
        "llm.stage": request.stage,
        "llm.endpoint": request.endpoint,
        "llm.model": request.model,
    }
    if request.page is not None:
        attributes["page.no"] = request.page.page_no
        attributes["llm.attachment"] = context.attachment
    return attributes


def _elapsed_ms(context: LlmDiagnosticContext) -> float:
    return max(0.0, (perf_counter() - context.started_perf) * 1000)


def _event_message(
    phase: str,
    request: LlmDiagnosticRequest,
    status_code: int | None,
) -> str:
    status = f" status={status_code}" if status_code is not None else ""
    page = f" page={request.page.page_no}" if request.page is not None else ""
    return (
        f"LM Studio {phase}: stage={request.stage} model={request.model}{page}{status}"
    )
