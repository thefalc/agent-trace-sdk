"""Generates realistic test data: multiple agent sessions with varied
models, tools, latencies, and occasional errors."""

from __future__ import annotations

import random
import time

from agent_trace_sdk import AgentTracer, KafkaConfig, SchemaRegistryConfig

MODELS = [
    ("claude-sonnet-4-20250514", "anthropic"),
    ("claude-haiku-4-5-20251001", "anthropic"),
    ("gpt-4o", "openai"),
]

TOOLS = [
    ("search_orders", {"query": "order status"}),
    ("lookup_customer", {"customer_id": "cust-101"}),
    ("query_inventory", {"sku": "SKU-9921"}),
    ("send_email", {"to": "user@example.com", "subject": "Follow up"}),
    ("search_knowledge_base", {"query": "return policy"}),
]

AGENTS = ["support-bot", "sales-assistant", "ops-monitor"]


def simulate_session(tracer: AgentTracer, session_num: int) -> None:
    agent_id = random.choice(AGENTS)
    user_id = f"user-{random.randint(100, 999)}"
    num_turns = random.randint(1, 5)
    should_error = random.random() < 0.1

    with tracer.session(user_id=user_id, agent_id=agent_id) as session:
        for turn in range(num_turns):
            model, provider = random.choice(MODELS)

            with tracer.llm_call(model=model, provider=provider) as llm:
                latency = random.uniform(20, 1500)
                time.sleep(0.005)

                if should_error and turn == num_turns - 1:
                    raise RuntimeError(f"Model timeout after {latency:.0f}ms")

                input_tokens = random.randint(50, 500)
                output_tokens = random.randint(20, 300)
                llm.set_response(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    response_content=f"Response for turn {turn + 1}",
                    finish_reason="end_turn",
                )

            if random.random() < 0.6:
                tool_name, tool_input = random.choice(TOOLS)
                with tracer.tool_call(tool_name=tool_name, tool_input=tool_input) as tool:
                    time.sleep(0.005)
                    tool.set_output({"status": "success", "results": random.randint(1, 50)})

    print(f"  Session {session_num:3d}: {agent_id:20s} | {num_turns} turns | trace={session.trace_id[:12]}...")


def main() -> None:
    tracer = AgentTracer(
        service_name="test-harness",
        kafka_config=KafkaConfig.from_env(),
        schema_registry_config=SchemaRegistryConfig.from_env(),
    )

    num_sessions = 50
    print(f"Generating {num_sessions} test sessions...\n")

    for i in range(1, num_sessions + 1):
        try:
            simulate_session(tracer, i)
        except RuntimeError as e:
            print(f"  Session {i:3d}: (errored: {e})")

    tracer.flush(timeout=15)
    print(f"\nDone. All events flushed to Kafka.")


if __name__ == "__main__":
    main()
