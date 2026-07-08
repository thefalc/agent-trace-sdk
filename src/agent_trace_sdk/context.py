from __future__ import annotations

from contextvars import ContextVar

_current_trace_id: ContextVar[str | None] = ContextVar("agent_trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("agent_span_id", default=None)
_current_service_name: ContextVar[str] = ContextVar("agent_service_name", default="unknown")


def get_trace_id() -> str | None:
    return _current_trace_id.get()


def set_trace_id(trace_id: str | None) -> None:
    _current_trace_id.set(trace_id)


def get_span_id() -> str | None:
    return _current_span_id.get()


def set_span_id(span_id: str | None) -> None:
    _current_span_id.set(span_id)


def get_service_name() -> str:
    return _current_service_name.get()


def set_service_name(name: str) -> None:
    _current_service_name.set(name)
