from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from .models import BaseEvent

if TYPE_CHECKING:
    from .config import KafkaConfig, SchemaRegistryConfig

logger = logging.getLogger("agent_trace_sdk")


class EventSink(Protocol):
    def emit(self, event: BaseEvent) -> None: ...
    def flush(self, timeout: float = 10.0) -> None: ...
    def close(self) -> None: ...


def _build_schema_str() -> str:
    """Build a flat JSON Schema with all fields across all event types.

    Flink SQL cannot parse $defs/$ref/oneOf, so we produce a single flat
    object schema where event-type-specific fields are optional.
    """
    return json.dumps({
        "type": "object",
        "properties": {
            "event_type":           {"type": "string"},
            "trace_id":             {"type": "string"},
            "span_id":              {"type": "string"},
            "parent_span_id":       {"type": ["string", "null"]},
            "timestamp":            {"type": "string", "format": "date-time"},
            "service_name":         {"type": "string"},
            "metadata":             {"type": "object", "additionalProperties": True},
            # session fields
            "user_id":              {"type": ["string", "null"]},
            "agent_id":             {"type": ["string", "null"]},
            "session_config":       {"type": ["object", "null"], "additionalProperties": True},
            "duration_ms":          {"type": ["number", "null"]},
            "total_llm_calls":      {"type": ["integer", "null"]},
            "total_tool_calls":     {"type": ["integer", "null"]},
            "total_input_tokens":   {"type": ["integer", "null"]},
            "total_output_tokens":  {"type": ["integer", "null"]},
            "exit_reason":          {"type": ["string", "null"]},
            "error":                {"type": ["string", "null"]},
            # llm fields
            "model":                {"type": ["string", "null"]},
            "provider":             {"type": ["string", "null"]},
            "input_messages":       {"type": ["array", "null"], "items": {"type": "object", "additionalProperties": True}},
            "temperature":          {"type": ["number", "null"]},
            "max_tokens":           {"type": ["integer", "null"]},
            "input_tokens":         {"type": ["integer", "null"]},
            "output_tokens":        {"type": ["integer", "null"]},
            "total_tokens":         {"type": ["integer", "null"]},
            "response_content":     {"type": ["string", "null"]},
            "finish_reason":        {"type": ["string", "null"]},
            # tool fields
            "tool_name":            {"type": ["string", "null"]},
            "tool_input":           {"type": ["string", "null"]},
            "tool_output":          {"type": ["string", "null"]},
            "success":              {"type": ["boolean", "null"]},
        },
        "required": ["event_type", "trace_id", "span_id", "timestamp", "service_name"],
    })


def _to_dict(obj: dict[str, Any], ctx: SerializationContext) -> dict[str, Any]:
    return obj


class KafkaEventProducer:
    def __init__(
        self,
        kafka_config: KafkaConfig,
        schema_registry_config: SchemaRegistryConfig,
        topic: str = "agent_trace_events",
    ) -> None:
        self._topic = topic

        sr_client = SchemaRegistryClient(schema_registry_config.to_confluent_config())
        schema_str = _build_schema_str()
        self._serializer = JSONSerializer(schema_str, sr_client, to_dict=_to_dict)
        self._producer = Producer(kafka_config.to_confluent_config())

    def _delivery_report(self, err: Any, msg: Any) -> None:
        if err is not None:
            logger.error("Trace event delivery failed: %s", err)
        else:
            logger.debug(
                "Trace event delivered to %s [%d] @ %d",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )

    def emit(self, event: BaseEvent) -> None:
        event_dict = event.model_dump(mode="json")
        value = self._serializer(
            event_dict,
            SerializationContext(self._topic, MessageField.VALUE),
        )
        self._producer.produce(
            self._topic,
            key=event.trace_id,
            value=value,
            on_delivery=self._delivery_report,
        )
        self._producer.poll(0)

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)

    def close(self) -> None:
        self.flush()


class InMemoryEventSink:
    """Event sink that stores events in memory — useful for testing and local debugging."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    def emit(self, event: BaseEvent) -> None:
        self.events.append(event)

    def flush(self, timeout: float = 10.0) -> None:
        pass

    def close(self) -> None:
        pass
