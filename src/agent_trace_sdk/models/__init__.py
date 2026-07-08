from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field

from .base import BaseEvent, generate_span_id, generate_trace_id
from .llm import LLMCallEndEvent, LLMCallStartEvent
from .session import SessionEndEvent, SessionStartEvent
from .tool import ToolCallEndEvent, ToolCallStartEvent

AgentEvent = Annotated[
    Union[
        SessionStartEvent,
        SessionEndEvent,
        LLMCallStartEvent,
        LLMCallEndEvent,
        ToolCallStartEvent,
        ToolCallEndEvent,
    ],
    Field(discriminator="event_type"),
]

__all__ = [
    "AgentEvent",
    "BaseEvent",
    "LLMCallEndEvent",
    "LLMCallStartEvent",
    "SessionEndEvent",
    "SessionStartEvent",
    "ToolCallEndEvent",
    "ToolCallStartEvent",
    "generate_span_id",
    "generate_trace_id",
]
