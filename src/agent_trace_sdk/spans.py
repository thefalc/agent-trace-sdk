from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .context import get_service_name, get_span_id, get_trace_id, set_span_id, set_trace_id
from .models import (
    LLMCallEndEvent,
    LLMCallStartEvent,
    SessionEndEvent,
    SessionStartEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    generate_span_id,
    generate_trace_id,
)

if TYPE_CHECKING:
    from .producer import EventSink


class SessionSpan:
    def __init__(
        self,
        sink: EventSink,
        service_name: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._sink = sink
        self._service_name = service_name
        self._user_id = user_id
        self._agent_id = agent_id
        self._metadata = metadata or {}
        self._trace_id = generate_trace_id()
        self._span_id = generate_span_id()
        self._start_time: float = 0
        self._llm_call_count = 0
        self._tool_call_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._prev_trace_id: str | None = None
        self._prev_span_id: str | None = None

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def span_id(self) -> str:
        return self._span_id

    def increment_llm_calls(self) -> None:
        self._llm_call_count += 1

    def increment_tool_calls(self) -> None:
        self._tool_call_count += 1

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

    def __enter__(self) -> SessionSpan:
        self._start_time = time.monotonic()
        self._prev_trace_id = get_trace_id()
        self._prev_span_id = get_span_id()
        set_trace_id(self._trace_id)
        set_span_id(self._span_id)
        self._sink.emit(SessionStartEvent(
            trace_id=self._trace_id,
            span_id=self._span_id,
            timestamp=datetime.now(timezone.utc),
            service_name=self._service_name,
            user_id=self._user_id,
            agent_id=self._agent_id,
            metadata=self._metadata,
        ))
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        self._sink.emit(SessionEndEvent(
            trace_id=self._trace_id,
            span_id=self._span_id,
            timestamp=datetime.now(timezone.utc),
            service_name=self._service_name,
            duration_ms=duration_ms,
            total_llm_calls=self._llm_call_count,
            total_tool_calls=self._tool_call_count,
            total_input_tokens=self._total_input_tokens,
            total_output_tokens=self._total_output_tokens,
            exit_reason="error" if exc_val else "completed",
            error=str(exc_val) if exc_val else None,
        ))
        set_trace_id(self._prev_trace_id)
        set_span_id(self._prev_span_id)
        return False


class LLMSpan:
    def __init__(
        self,
        sink: EventSink,
        service_name: str,
        session: SessionSpan | None,
        *,
        model: str,
        provider: str,
        input_messages: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._sink = sink
        self._service_name = service_name
        self._session = session
        self._model = model
        self._provider = provider
        self._input_messages = input_messages
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._metadata = metadata or {}
        self._span_id = generate_span_id()
        self._start_time: float = 0
        self._parent_span_id: str | None = None
        self._prev_span_id: str | None = None

        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._total_tokens: int | None = None
        self._response_content: str | None = None
        self._finish_reason: str | None = None

    @property
    def span_id(self) -> str:
        return self._span_id

    def set_response(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        response_content: str | None = None,
        finish_reason: str | None = None,
    ) -> None:
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._total_tokens = total_tokens
        self._response_content = response_content
        self._finish_reason = finish_reason

    def __enter__(self) -> LLMSpan:
        self._start_time = time.monotonic()
        self._parent_span_id = get_span_id()
        self._prev_span_id = get_span_id()
        set_span_id(self._span_id)
        self._sink.emit(LLMCallStartEvent(
            trace_id=get_trace_id() or "",
            span_id=self._span_id,
            parent_span_id=self._parent_span_id,
            timestamp=datetime.now(timezone.utc),
            service_name=self._service_name,
            model=self._model,
            provider=self._provider,
            input_messages=self._input_messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            metadata=self._metadata,
        ))
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        set_span_id(self._prev_span_id)

        if self._session:
            self._session.increment_llm_calls()
            self._session.add_tokens(
                input_tokens=self._input_tokens or 0,
                output_tokens=self._output_tokens or 0,
            )

        self._sink.emit(LLMCallEndEvent(
            trace_id=get_trace_id() or "",
            span_id=self._span_id,
            parent_span_id=self._parent_span_id,
            timestamp=datetime.now(timezone.utc),
            service_name=self._service_name,
            model=self._model,
            provider=self._provider,
            duration_ms=duration_ms,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._total_tokens,
            response_content=self._response_content,
            finish_reason=self._finish_reason,
            error=str(exc_val) if exc_val else None,
        ))
        return False


class ToolSpan:
    def __init__(
        self,
        sink: EventSink,
        service_name: str,
        session: SessionSpan | None,
        *,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._sink = sink
        self._service_name = service_name
        self._session = session
        self._tool_name = tool_name
        self._tool_input = tool_input
        self._metadata = metadata or {}
        self._span_id = generate_span_id()
        self._start_time: float = 0
        self._parent_span_id: str | None = None
        self._prev_span_id: str | None = None

        self._tool_output: Any = None
        self._success: bool = True

    @property
    def span_id(self) -> str:
        return self._span_id

    def set_output(self, output: Any, *, success: bool = True) -> None:
        self._tool_output = output
        self._success = success

    def __enter__(self) -> ToolSpan:
        self._start_time = time.monotonic()
        self._parent_span_id = get_span_id()
        self._prev_span_id = get_span_id()
        set_span_id(self._span_id)
        self._sink.emit(ToolCallStartEvent(
            trace_id=get_trace_id() or "",
            span_id=self._span_id,
            parent_span_id=self._parent_span_id,
            timestamp=datetime.now(timezone.utc),
            service_name=self._service_name,
            tool_name=self._tool_name,
            tool_input=self._tool_input,
            metadata=self._metadata,
        ))
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        duration_ms = (time.monotonic() - self._start_time) * 1000
        set_span_id(self._prev_span_id)

        if self._session:
            self._session.increment_tool_calls()

        if exc_val:
            self._success = False

        self._sink.emit(ToolCallEndEvent(
            trace_id=get_trace_id() or "",
            span_id=self._span_id,
            parent_span_id=self._parent_span_id,
            timestamp=datetime.now(timezone.utc),
            service_name=self._service_name,
            tool_name=self._tool_name,
            duration_ms=duration_ms,
            tool_output=self._tool_output,
            success=self._success,
            error=str(exc_val) if exc_val else None,
        ))
        return False
