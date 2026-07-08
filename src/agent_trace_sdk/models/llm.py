from __future__ import annotations

from typing import Any, Literal

from .base import BaseEvent


class LLMCallStartEvent(BaseEvent):
    event_type: Literal["llm_call.start"] = "llm_call.start"
    model: str
    provider: str
    input_messages: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class LLMCallEndEvent(BaseEvent):
    event_type: Literal["llm_call.end"] = "llm_call.end"
    model: str
    provider: str
    duration_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    response_content: str | None = None
    finish_reason: str | None = None
    error: str | None = None
