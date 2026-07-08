from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import field_serializer

from .base import BaseEvent


class ToolCallStartEvent(BaseEvent):
    event_type: Literal["tool_call.start"] = "tool_call.start"
    tool_name: str
    tool_input: dict[str, Any] | None = None

    @field_serializer("tool_input")
    @classmethod
    def serialize_tool_input(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)


class ToolCallEndEvent(BaseEvent):
    event_type: Literal["tool_call.end"] = "tool_call.end"
    tool_name: str
    duration_ms: float
    tool_output: Any = None
    success: bool = True
    error: str | None = None

    @field_serializer("tool_output")
    @classmethod
    def serialize_tool_output(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)
