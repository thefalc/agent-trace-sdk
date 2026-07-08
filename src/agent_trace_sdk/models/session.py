from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .base import BaseEvent


class SessionStartEvent(BaseEvent):
    event_type: Literal["session.start"] = "session.start"
    user_id: str | None = None
    agent_id: str | None = None
    session_config: dict[str, Any] = Field(default_factory=dict)


class SessionEndEvent(BaseEvent):
    event_type: Literal["session.end"] = "session.end"
    duration_ms: float
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    exit_reason: str = "completed"
    error: str | None = None
