from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def generate_trace_id() -> str:
    return os.urandom(16).hex()


def generate_span_id() -> str:
    return os.urandom(8).hex()


class BaseEvent(BaseModel):
    event_type: str
    trace_id: str = Field(description="128-bit hex trace identifier shared across a session")
    span_id: str = Field(
        default_factory=generate_span_id,
        description="64-bit hex span identifier unique to this span",
    )
    parent_span_id: str | None = Field(
        default=None,
        description="64-bit hex span identifier of the parent span",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service_name: str = Field(description="Name of the agent or application")
    metadata: dict[str, Any] = Field(default_factory=dict)
