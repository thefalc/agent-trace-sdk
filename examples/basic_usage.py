"""
Basic usage example: traces an agent session with LLM and tool calls.

Run with InMemoryEventSink (no Kafka needed):
    python examples/basic_usage.py

Run with Confluent Kafka (requires .env):
    CONFLUENT_BOOTSTRAP_SERVERS=... python examples/basic_usage.py --kafka
"""

from __future__ import annotations

import sys
import time

from agent_trace_sdk import AgentTracer, InMemoryEventSink, KafkaConfig, SchemaRegistryConfig


def simulate_llm_call() -> dict:
    time.sleep(0.05)
    return {
        "content": "I'll search the database for your order status.",
        "input_tokens": 150,
        "output_tokens": 42,
        "finish_reason": "end_turn",
    }


def simulate_tool_call(query: str) -> dict:
    time.sleep(0.02)
    return {"order_id": "ORD-123", "status": "shipped", "eta": "2026-04-20"}


def run_agent(tracer: AgentTracer) -> None:
    with tracer.session(user_id="user-456", agent_id="support-bot-v2") as session:
        # First turn: LLM decides to use a tool
        with tracer.llm_call(model="claude-sonnet-4-20250514", provider="anthropic") as llm:
            response = simulate_llm_call()
            llm.set_response(
                input_tokens=response["input_tokens"],
                output_tokens=response["output_tokens"],
                response_content=response["content"],
                finish_reason=response["finish_reason"],
            )

        # Tool call triggered by LLM
        with tracer.tool_call(
            tool_name="search_orders",
            tool_input={"query": "order status for user-456"},
        ) as tool:
            result = simulate_tool_call("order status for user-456")
            tool.set_output(result)

        # Second turn: LLM responds with tool results
        with tracer.llm_call(
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            input_messages=[
                {"role": "user", "content": "Where is my order?"},
                {"role": "assistant", "content": response["content"]},
                {"role": "tool", "content": str(result)},
            ],
        ) as llm:
            final = simulate_llm_call()
            llm.set_response(
                input_tokens=final["input_tokens"],
                output_tokens=final["output_tokens"],
                response_content="Your order ORD-123 has shipped and will arrive by April 20th.",
                finish_reason="end_turn",
            )

    print(f"Session {session.trace_id} traced successfully")


def main() -> None:
    use_kafka = "--kafka" in sys.argv

    if use_kafka:
        tracer = AgentTracer(
            service_name="support-agent",
            kafka_config=KafkaConfig.from_env(),
            schema_registry_config=SchemaRegistryConfig.from_env(),
        )
    else:
        sink = InMemoryEventSink()
        tracer = AgentTracer(service_name="support-agent", sink=sink)

    try:
        run_agent(tracer)

        if not use_kafka:
            assert isinstance(tracer.sink, InMemoryEventSink)
            print(f"\nCaptured {len(tracer.sink.events)} events:")
            for event in tracer.sink.events:
                print(f"  [{event.event_type:20s}] span={event.span_id[:8]}... "
                      f"parent={event.parent_span_id[:8] + '...' if event.parent_span_id else 'None':12s}")
    finally:
        tracer.close()


if __name__ == "__main__":
    main()
