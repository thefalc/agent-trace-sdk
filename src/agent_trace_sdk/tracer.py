from __future__ import annotations

from typing import Any

from .config import KafkaConfig, SchemaRegistryConfig
from .context import set_service_name
from .producer import EventSink, InMemoryEventSink, KafkaEventProducer
from .spans import LLMSpan, SessionSpan, ToolSpan


class AgentTracer:
    """Main entry point for tracing AI agent interactions.

    Usage:
        tracer = AgentTracer(
            service_name="my-agent",
            kafka_config=KafkaConfig.from_env(),
            schema_registry_config=SchemaRegistryConfig.from_env(),
        )

        with tracer.session(user_id="user-123") as session:
            with tracer.llm_call(model="claude-sonnet-4-20250514", provider="anthropic") as llm:
                response = call_llm(...)
                llm.set_response(output_tokens=100, response_content="...")

        tracer.close()
    """

    def __init__(
        self,
        service_name: str,
        kafka_config: KafkaConfig | None = None,
        schema_registry_config: SchemaRegistryConfig | None = None,
        topic: str = "agent_trace_events",
        sink: EventSink | None = None,
    ) -> None:
        self._service_name = service_name
        set_service_name(service_name)

        if sink is not None:
            self._sink = sink
        elif kafka_config is not None and schema_registry_config is not None:
            self._sink = KafkaEventProducer(kafka_config, schema_registry_config, topic)
        else:
            self._sink = InMemoryEventSink()

        self._active_session: SessionSpan | None = None

    @property
    def sink(self) -> EventSink:
        return self._sink

    def session(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionSpan:
        span = SessionSpan(
            self._sink,
            self._service_name,
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata,
        )
        self._active_session = span
        return span

    def llm_call(
        self,
        *,
        model: str,
        provider: str,
        input_messages: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMSpan:
        return LLMSpan(
            self._sink,
            self._service_name,
            self._active_session,
            model=model,
            provider=provider,
            input_messages=input_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata=metadata,
        )

    def tool_call(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolSpan:
        return ToolSpan(
            self._sink,
            self._service_name,
            self._active_session,
            tool_name=tool_name,
            tool_input=tool_input,
            metadata=metadata,
        )

    def flush(self, timeout: float = 10.0) -> None:
        self._sink.flush(timeout)

    def close(self) -> None:
        self._sink.close()
