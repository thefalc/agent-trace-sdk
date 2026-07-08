#!/usr/bin/env python3
"""Claude Code hook that produces agent trace events to Confluent Kafka.

Reads hook event JSON from stdin, maps it to the agent-trace-sdk event
model, and produces to the agent_trace_events topic.

Hook types handled:
  - PreToolUse  → tool_call.start
  - PostToolUse → tool_call.end
  - Stop        → session.end

Session tracking: the first event seen for a session_id triggers a
session.start event. A local state file tracks active sessions.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add the SDK to the path
SDK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SDK_ROOT / "src"))

from agent_trace_sdk.config import KafkaConfig, SchemaRegistryConfig
from agent_trace_sdk.models.base import generate_span_id
from agent_trace_sdk.models.session import SessionEndEvent, SessionStartEvent
from agent_trace_sdk.models.tool import ToolCallEndEvent, ToolCallStartEvent
from agent_trace_sdk.producer import KafkaEventProducer

DOTENV_PATH = str(SDK_ROOT / ".env")
STATE_DIR = Path.home() / ".claude" / "agent-trace-state"
STATE_DIR.mkdir(parents=True, exist_ok=True)


def _session_state_path(session_id: str) -> Path:
    return STATE_DIR / f"{session_id}.json"


def _load_session_state(session_id: str) -> dict | None:
    path = _session_state_path(session_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def _save_session_state(session_id: str, state: dict) -> None:
    _session_state_path(session_id).write_text(json.dumps(state))


def _delete_session_state(session_id: str) -> None:
    path = _session_state_path(session_id)
    if path.exists():
        path.unlink()


def _get_producer() -> KafkaEventProducer:
    kafka_config = KafkaConfig.from_env(DOTENV_PATH)
    sr_config = SchemaRegistryConfig.from_env(DOTENV_PATH)
    return KafkaEventProducer(kafka_config, sr_config, topic="agent_trace_events")


def _ensure_session_started(
    producer: KafkaEventProducer, session_id: str, hook_input: dict
) -> dict:
    state = _load_session_state(session_id)
    if state is not None:
        return state

    state = {
        "trace_id": session_id,
        "span_id": generate_span_id(),
        "start_time": time.monotonic(),
        "start_ts": datetime.now(timezone.utc).isoformat(),
        "tool_call_count": 0,
        "cwd": hook_input.get("cwd", ""),
    }
    _save_session_state(session_id, state)

    producer.emit(SessionStartEvent(
        trace_id=session_id,
        span_id=state["span_id"],
        timestamp=datetime.now(timezone.utc),
        service_name="claude-code",
        agent_id="claude-code",
        metadata={
            "cwd": hook_input.get("cwd", ""),
            "permission_mode": hook_input.get("permission_mode", ""),
        },
    ))
    return state


def handle_pre_tool_use(producer: KafkaEventProducer, hook_input: dict) -> dict:
    session_id = hook_input["session_id"]
    state = _ensure_session_started(producer, session_id, hook_input)

    span_id = generate_span_id()
    tool_use_id = hook_input.get("tool_use_id", span_id)

    # Store span mapping for PostToolUse to pick up
    spans_path = STATE_DIR / f"{session_id}_spans.json"
    spans = json.loads(spans_path.read_text()) if spans_path.exists() else {}
    spans[tool_use_id] = {
        "span_id": span_id,
        "start_mono": time.monotonic(),
    }
    spans_path.write_text(json.dumps(spans))

    tool_input = hook_input.get("tool_input", {})
    if isinstance(tool_input, str):
        tool_input = {"raw": tool_input}

    producer.emit(ToolCallStartEvent(
        trace_id=session_id,
        span_id=span_id,
        parent_span_id=state["span_id"],
        timestamp=datetime.now(timezone.utc),
        service_name="claude-code",
        tool_name=hook_input.get("tool_name", "unknown"),
        tool_input=tool_input,
    ))

    return {}


def handle_post_tool_use(producer: KafkaEventProducer, hook_input: dict) -> dict:
    session_id = hook_input["session_id"]
    state = _load_session_state(session_id)
    if state is None:
        return {}

    tool_use_id = hook_input.get("tool_use_id", "")
    spans_path = STATE_DIR / f"{session_id}_spans.json"
    spans = json.loads(spans_path.read_text()) if spans_path.exists() else {}
    span_info = spans.pop(tool_use_id, None)
    spans_path.write_text(json.dumps(spans))

    if span_info is None:
        span_id = generate_span_id()
        duration_ms = 0.0
    else:
        span_id = span_info["span_id"]
        duration_ms = (time.monotonic() - span_info["start_mono"]) * 1000

    tool_response = hook_input.get("tool_response")
    tool_output_str = None
    if tool_response is not None:
        tool_output_str = json.dumps(tool_response) if not isinstance(tool_response, str) else tool_response
        if len(tool_output_str) > 2000:
            tool_output_str = tool_output_str[:2000] + "... (truncated)"

    error = None
    success = True
    if isinstance(tool_response, dict) and tool_response.get("error"):
        error = str(tool_response["error"])
        success = False

    producer.emit(ToolCallEndEvent(
        trace_id=session_id,
        span_id=span_id,
        parent_span_id=state["span_id"],
        timestamp=datetime.now(timezone.utc),
        service_name="claude-code",
        tool_name=hook_input.get("tool_name", "unknown"),
        duration_ms=duration_ms,
        tool_output=tool_output_str,
        success=success,
        error=error,
    ))

    state["tool_call_count"] = state.get("tool_call_count", 0) + 1
    _save_session_state(session_id, state)

    return {}


def handle_stop(producer: KafkaEventProducer, hook_input: dict) -> dict:
    session_id = hook_input["session_id"]
    state = _load_session_state(session_id)

    if state is None:
        return {}

    start_ts = datetime.fromisoformat(state["start_ts"])
    duration_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000

    producer.emit(SessionEndEvent(
        trace_id=session_id,
        span_id=state["span_id"],
        timestamp=datetime.now(timezone.utc),
        service_name="claude-code",
        duration_ms=duration_ms,
        total_tool_calls=state.get("tool_call_count", 0),
        exit_reason="completed",
    ))

    # Clean up state files
    _delete_session_state(session_id)
    spans_path = STATE_DIR / f"{session_id}_spans.json"
    if spans_path.exists():
        spans_path.unlink()

    return {}


HANDLERS = {
    "PreToolUse": handle_pre_tool_use,
    "PostToolUse": handle_post_tool_use,
    "Stop": handle_stop,
}


def main() -> None:
    try:
        hook_input = json.loads(sys.stdin.read())
        event_name = hook_input.get("hook_event_name", "")
        handler = HANDLERS.get(event_name)

        if handler is None:
            sys.exit(0)

        producer = _get_producer()
        try:
            handler(producer, hook_input)
            producer.flush(timeout=5)
        finally:
            producer.close()

        sys.exit(0)

    except Exception as e:
        print(f"agent-trace hook error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
