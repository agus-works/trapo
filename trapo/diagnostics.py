from __future__ import annotations

import json
import logging
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter

from trapo.db import DuckConnection
from trapo.diagnostics_values import (
    MAX_ATTRIBUTE_DEPTH,
    MAX_ATTRIBUTE_STRING_LENGTH,
    MAX_ERROR_MESSAGE_LENGTH,
    MAX_ERROR_STACK_LENGTH,
    category_from_name,
    int_attr,
    random_span_id,
    random_trace_id,
    safe_value,
    step_from_name,
    str_attr,
    truncate,
)


LOGGER = logging.getLogger(__name__)
INSERT_DIAGNOSTIC_EVENT_SQL = """
INSERT INTO ingest_diagnostic_events (
    event_id, trace_id, span_id, ingest_run_id, file_hash, page_no,
    timestamp, event_type, name, severity, message, attributes_json
)
VALUES (
    nextval('diagnostic_event_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON
)
"""


@dataclass
class DiagnosticRunContext:
    connection: DuckConnection
    ingest_run_id: int
    trace_id: str | None = None


@dataclass(frozen=True)
class DiagnosticAttributes:
    values: dict[str, object]
    string_limit: int = MAX_ATTRIBUTE_STRING_LENGTH
    depth_limit: int = MAX_ATTRIBUTE_DEPTH


@dataclass
class DiagnosticSpanHandle:  # noqa: PLR0902
    connection: DuckConnection
    trace_id: str
    span_id: str
    parent_span_id: str | None
    ingest_run_id: int
    name: str
    started_at: datetime
    started_perf: float
    attributes: dict[str, object] = field(default_factory=dict)
    file_hash: str | None = None
    page_no: int | None = None
    pipeline_step: str = ""
    category: str = "pipeline"
    annotation_engine: str | None = None
    status: str = "ok"
    error_type: str | None = None
    error_message: str | None = None
    error_stack: str | None = None

    def set_attributes(self, attributes: dict[str, object | None]) -> None:
        safe_attributes = {
            key: safe_value(value)
            for key, value in attributes.items()
            if value is not None
        }
        self.attributes.update(safe_attributes)
        self.file_hash = str_attr(self.attributes, "file.hash") or self.file_hash
        self.page_no = int_attr(self.attributes, "page.no") or self.page_no
        self.pipeline_step = (
            str_attr(self.attributes, "pipeline.step") or self.pipeline_step
        )
        self.category = str_attr(self.attributes, "pipeline.category") or self.category
        self.annotation_engine = (
            str_attr(self.attributes, "annotation.engine") or self.annotation_engine
        )
        ingest_status = str_attr(self.attributes, "ingest.status")
        if ingest_status in {"error", "skipped"}:
            self.status = ingest_status

    def record_exception(self, exc: BaseException) -> None:
        self.status = "error"
        self.error_type = exc.__class__.__name__
        self.error_message = truncate(str(exc), MAX_ERROR_MESSAGE_LENGTH)
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.error_stack = truncate(stack, MAX_ERROR_STACK_LENGTH)
        record_diagnostic_event(
            "exception",
            message=self.error_message,
            severity="error",
            event_type="exception",
            attributes={"exception.type": self.error_type},
        )

    def finish(self) -> None:
        ended_at = datetime.now(UTC)
        duration_ms = max(0.0, (perf_counter() - self.started_perf) * 1000)
        self.connection.execute(
            """
            INSERT OR REPLACE INTO ingest_diagnostic_spans (
                span_id, trace_id, parent_span_id, ingest_run_id, file_hash, page_no,
                name, pipeline_step, category, annotation_engine, status,
                started_at, ended_at, duration_ms, attributes_json,
                error_type, error_message, error_stack
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::JSON, ?, ?, ?)
            """,
            [
                self.span_id,
                self.trace_id,
                self.parent_span_id,
                self.ingest_run_id,
                self.file_hash,
                self.page_no,
                self.name,
                self.pipeline_step or step_from_name(self.name),
                self.category,
                self.annotation_engine,
                self.status,
                self.started_at,
                ended_at,
                duration_ms,
                json.dumps(self.attributes),
                self.error_type,
                self.error_message,
                self.error_stack,
            ],
        )


_RUN_CONTEXT: ContextVar[DiagnosticRunContext | None] = ContextVar(
    "trapo_diagnostic_run_context", default=None
)
_SPAN_STACK: ContextVar[tuple[DiagnosticSpanHandle, ...]] = ContextVar(
    "trapo_diagnostic_span_stack", default=()
)


def activate_diagnostic_run(connection: DuckConnection, ingest_run_id: int) -> None:
    _RUN_CONTEXT.set(
        DiagnosticRunContext(connection=connection, ingest_run_id=ingest_run_id)
    )
    _SPAN_STACK.set(())


def deactivate_diagnostic_run() -> None:
    _SPAN_STACK.set(())
    _RUN_CONTEXT.set(None)


def start_diagnostic_span(
    name: str,
    *,
    attributes: dict[str, object] | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> DiagnosticSpanHandle | None:
    context = _RUN_CONTEXT.get()
    if context is None:
        return None
    active_trace_id = _active_trace_id(context, trace_id)
    stack = _SPAN_STACK.get()
    parent = stack[-1] if stack else None
    handle = DiagnosticSpanHandle(
        connection=context.connection,
        trace_id=active_trace_id,
        span_id=span_id or random_span_id(),
        parent_span_id=parent.span_id if parent else None,
        ingest_run_id=context.ingest_run_id,
        name=name,
        started_at=datetime.now(UTC),
        started_perf=perf_counter(),
        file_hash=parent.file_hash if parent else None,
        page_no=parent.page_no if parent else None,
        pipeline_step=step_from_name(name),
        category=category_from_name(name),
        annotation_engine=parent.annotation_engine if parent else None,
    )
    handle.set_attributes(attributes or {})
    _SPAN_STACK.set((*stack, handle))
    return handle


def finish_diagnostic_span(handle: DiagnosticSpanHandle | None) -> None:
    if handle is None:
        return
    stack = _SPAN_STACK.get()
    if stack and stack[-1] is handle:
        _SPAN_STACK.set(stack[:-1])
    else:
        _SPAN_STACK.set(tuple(item for item in stack if item is not handle))
    try:
        handle.finish()
    except Exception:
        LOGGER.debug("Failed to finish ingest diagnostic span.", exc_info=True)
        return


def record_diagnostic_event(
    name: str,
    *,
    message: str | None = None,
    severity: str = "info",
    event_type: str = "log",
    attributes: dict[str, object] | DiagnosticAttributes | None = None,
) -> None:
    context = _RUN_CONTEXT.get()
    if context is None:
        return
    if context.trace_id is None:
        context.trace_id = random_trace_id()
    event_attributes = (
        attributes
        if isinstance(attributes, DiagnosticAttributes)
        else DiagnosticAttributes(values=attributes or {})
    )
    safe_attributes = safe_value(
        event_attributes.values,
        string_limit=event_attributes.string_limit,
        depth_limit=event_attributes.depth_limit,
    )
    if not isinstance(safe_attributes, dict):
        safe_attributes = {}
    trace_id, span_id, file_hash, page_no = _event_scope(
        context,
        attributes=safe_attributes,
    )
    parameters = [
        trace_id,
        span_id,
        context.ingest_run_id,
        file_hash,
        page_no,
        datetime.now(UTC),
        event_type,
        name,
        severity,
        truncate(message or "", MAX_ERROR_MESSAGE_LENGTH),
        json.dumps(safe_attributes),
    ]
    try:
        context.connection.execute(INSERT_DIAGNOSTIC_EVENT_SQL, parameters)
    except Exception:
        LOGGER.debug("Failed to persist ingest diagnostic event.", exc_info=True)
        return


def diagnostic_context_active() -> bool:
    return _RUN_CONTEXT.get() is not None


def _active_trace_id(context: DiagnosticRunContext, trace_id: str | None) -> str:
    if trace_id is not None:
        context.trace_id = trace_id
    elif context.trace_id is None:
        context.trace_id = random_trace_id()
    active_trace_id = context.trace_id
    if active_trace_id is None:
        active_trace_id = random_trace_id()
        context.trace_id = active_trace_id
    return active_trace_id


def _event_scope(
    context: DiagnosticRunContext,
    *,
    attributes: dict[str, object],
) -> tuple[str, str | None, str | None, int | None]:
    stack = _SPAN_STACK.get()
    span = stack[-1] if stack else None
    attr_file_hash = str_attr(attributes, "file.hash")
    attr_page_no = int_attr(attributes, "page.no")
    if span is not None:
        return (
            span.trace_id,
            span.span_id,
            span.file_hash or attr_file_hash,
            span.page_no or attr_page_no,
        )
    return context.trace_id or random_trace_id(), None, attr_file_hash, attr_page_no
