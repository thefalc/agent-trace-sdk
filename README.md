# Agent Trace SDK

A framework-agnostic Python SDK for capturing AI agent observability data and producing structured traces to [Confluent Cloud](https://confluent.io/). Instrument your agents with a few lines of code to get full visibility into sessions, LLM calls, and tool usage.

## What it does

Agent Trace SDK wraps your agent's LLM and tool calls in lightweight spans that automatically capture:

- **Sessions** -- user/agent identity, duration, token totals, error state
- **LLM calls** -- model, provider, input/output tokens, latency, response content
- **Tool calls** -- tool name, input/output payloads, success/failure, latency

Events are serialized as JSON Schema-validated records and produced to a Kafka topic on Confluent Cloud, where they can be processed with Flink SQL, materialized into dashboards, or forwarded to any downstream system.

## Architecture

```
Your Agent Code
      |
      v
 AgentTracer  (context-managed spans)
      |
      v
 KafkaEventProducer  (JSON Schema serialization + Confluent Kafka producer)
      |
      v
 Confluent Cloud  (Kafka topic → Flink SQL → dashboards / alerts)
```

For local development and testing, swap in the `InMemoryEventSink` to capture events without any Kafka infrastructure.

## Installation

Requires Python 3.11+.

```bash
pip install -e .
```

For development (linting, type checking, tests):

```bash
pip install -e ".[dev]"
```

## Configuration

Copy the example environment file and fill in your Confluent Cloud credentials:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description |
|---|---|
| `CONFLUENT_BOOTSTRAP_SERVERS` | Kafka bootstrap servers (e.g. `pkc-xxxxx.us-west-2.aws.confluent.cloud:9092`) |
| `CONFLUENT_API_KEY` | Kafka cluster API key |
| `CONFLUENT_API_SECRET` | Kafka cluster API secret |
| `CONFLUENT_SCHEMA_REGISTRY_URL` | Schema Registry endpoint URL |
| `CONFLUENT_SCHEMA_REGISTRY_API_KEY` | Schema Registry API key |
| `CONFLUENT_SCHEMA_REGISTRY_API_SECRET` | Schema Registry API secret |

## Quick start

### With Confluent Cloud

```python
from agent_trace_sdk import AgentTracer, KafkaConfig, SchemaRegistryConfig

tracer = AgentTracer(
    service_name="my-agent",
    kafka_config=KafkaConfig.from_env(),
    schema_registry_config=SchemaRegistryConfig.from_env(),
)

with tracer.session(user_id="user-123", agent_id="support-bot") as session:
    with tracer.llm_call(model="claude-sonnet-4-20250514", provider="anthropic") as llm:
        response = call_your_llm(...)
        llm.set_response(
            input_tokens=150,
            output_tokens=42,
            response_content=response.text,
            finish_reason="end_turn",
        )

    with tracer.tool_call(tool_name="search_orders", tool_input={"query": "order status"}) as tool:
        result = search_orders(...)
        tool.set_output(result)

tracer.close()
```

### Without Kafka (local development)

Use the `InMemoryEventSink` for testing and local debugging -- no infrastructure required:

```python
from agent_trace_sdk import AgentTracer, InMemoryEventSink

sink = InMemoryEventSink()
tracer = AgentTracer(service_name="my-agent", sink=sink)

with tracer.session(user_id="user-123") as session:
    with tracer.llm_call(model="gpt-4o", provider="openai") as llm:
        llm.set_response(input_tokens=100, output_tokens=50, response_content="Hello!")

print(f"Captured {len(sink.events)} events")
for event in sink.events:
    print(f"  [{event.event_type}] span={event.span_id}")
```

## Examples

Run the basic example with in-memory tracing:

```bash
python examples/basic_usage.py
```

Or with Kafka (requires `.env` to be configured):

```bash
python examples/basic_usage.py --kafka
```

Generate bulk test data (50 sessions with varied models, tools, and occasional errors):

```bash
python examples/generate_test_data.py
```

## Event types

The SDK emits paired start/end events for each span:

| Event type | Description |
|---|---|
| `session.start` | Agent session opened (user ID, agent ID, metadata) |
| `session.end` | Session closed (duration, token totals, LLM/tool call counts, exit reason) |
| `llm_call.start` | LLM request initiated (model, provider, input messages, parameters) |
| `llm_call.end` | LLM response received (tokens, latency, response content, finish reason) |
| `tool_call.start` | Tool invocation started (tool name, input payload) |
| `tool_call.end` | Tool invocation completed (output, latency, success/failure) |

All events share a `trace_id` (per session) and `span_id`/`parent_span_id` for hierarchical correlation.

## Flink SQL jobs

The `flink/` directory contains four Flink SQL statements that process the raw `agent_trace_events` topic into derived tables. Deploy them in order using the [Confluent Cloud Console](https://confluent.cloud/) Flink SQL workspace or the Confluent CLI.

**Prerequisites:** The `agent_trace_events` topic must already exist and the SDK must be producing events to it.

### Deployment order

The jobs must be deployed sequentially -- each builds on the tables before it:

| # | File | Output topic | Description |
|---|---|---|---|
| 1 | `01_llm_call_completed.sql` | `llm_call_completed` | Joins `llm_call.start` + `llm_call.end` by `span_id` into a single enriched record per LLM invocation |
| 2 | `02_tool_call_completed.sql` | `tool_call_completed` | Joins `tool_call.start` + `tool_call.end` by `span_id` into a single record per tool invocation |
| 3 | `03_session_summaries.sql` | `session_summaries` | Filters `session.end` events into a dedicated session summary table with aggregated stats |
| 4 | `04_agent_health_metrics.sql` | `agent_health_metrics` | 1-minute tumbling window over `llm_call_completed` computing throughput, latency, and error rate per model (depends on job 1) |

### Deploying via Confluent CLI

```bash
confluent flink statement create \
  --cloud aws \
  --region us-west-2 \
  --environment <ENV_ID> \
  --database <CLUSTER_NAME> \
  --sql "$(cat flink/01_llm_call_completed.sql)"
```

Repeat for each SQL file in order. Wait for each statement to reach `RUNNING` before submitting the next.

### Recreating tables

If you need to recreate a table, drop it first:

```sql
DROP TABLE `llm_call_completed`;
```

Then resubmit the `CREATE TABLE AS` statement.

## Dashboard

The `dashboard/` directory contains a [Streamlit](https://streamlit.io/) app that provides real-time observability over your agent traces. It queries the Flink-derived topics via the Confluent Real-Time Context Engine (RTCE) API.

### Pages

- **Overview** -- top-level metrics (session count, error rate, total tokens), sessions by status, LLM calls by model, recent errors
- **Sessions** -- filterable session table with duration distribution chart
- **Session Detail** -- trace waterfall visualization with expandable span details (LLM responses, tool input/output)
- **Models** -- per-model performance stats, duration box plots, token usage comparison
- **Tools** -- per-tool call volume, duration, and success rates

### Running the dashboard

Install the dashboard dependencies:

```bash
pip install streamlit pandas altair requests
```

Set the RTCE environment variables (in addition to the Kafka vars in `.env`):

| Variable | Description |
|---|---|
| `RTCE_ORG_ID` | Confluent Cloud organization ID |
| `RTCE_ENV_ID` | Confluent Cloud environment ID |
| `RTCE_CLUSTER_ID` | Kafka cluster ID |
| `RTCE_API_KEY` | RTCE API key |
| `RTCE_API_SECRET` | RTCE API secret |
| `RTCE_REGION` | AWS region (defaults to `us-east-1`) |

Start the dashboard:

```bash
cd dashboard
streamlit run app.py
```

The dashboard auto-refreshes data every 15 seconds.

## Claude Code hook

The `hooks/` directory contains a hook script that automatically traces [Claude Code](https://docs.anthropic.com/en/docs/claude-code) sessions. It captures every tool call Claude Code makes and produces trace events to Kafka with no manual instrumentation.

### Hook events captured

| Hook event | Trace event | Description |
|---|---|---|
| First event in session | `session.start` | Auto-detected, emits session start with cwd and permission mode |
| `PreToolUse` | `tool_call.start` | Tool name and input payload |
| `PostToolUse` | `tool_call.end` | Tool output (truncated to 2KB), duration, success/failure |
| `Stop` | `session.end` | Session duration and total tool call count |

### Setup

1. Make sure your `.env` file is configured with Confluent Cloud credentials (see [Configuration](#configuration))

2. Add the hook to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "type": "command",
        "command": "python3 /path/to/agent-trace-sdk/hooks/claude_code_hook.py"
      }
    ],
    "PostToolUse": [
      {
        "type": "command",
        "command": "python3 /path/to/agent-trace-sdk/hooks/claude_code_hook.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 /path/to/agent-trace-sdk/hooks/claude_code_hook.py"
      }
    ]
  }
}
```

Replace `/path/to/agent-trace-sdk` with the absolute path to this repository.

3. Session state is stored in `~/.claude/agent-trace-state/` and cleaned up automatically when sessions end.

## Project structure

```
src/agent_trace_sdk/
  __init__.py           # Public API exports
  tracer.py             # AgentTracer entry point
  spans.py              # SessionSpan, LLMSpan, ToolSpan context managers
  producer.py           # KafkaEventProducer, InMemoryEventSink
  config.py             # KafkaConfig, SchemaRegistryConfig
  context.py            # ContextVar-based trace/span propagation
  models/               # Pydantic event models
    base.py             # BaseEvent with trace_id, span_id, timestamp
    session.py          # SessionStartEvent, SessionEndEvent
    llm.py              # LLMCallStartEvent, LLMCallEndEvent
    tool.py             # ToolCallStartEvent, ToolCallEndEvent
examples/
  basic_usage.py        # Minimal working example
  generate_test_data.py # Bulk test data generator
flink/
  01_llm_call_completed.sql   # Join LLM start+end spans
  02_tool_call_completed.sql  # Join tool start+end spans
  03_session_summaries.sql    # Extract session summaries
  04_agent_health_metrics.sql # 1-min tumbling window health metrics
dashboard/
  app.py                # Streamlit observability dashboard
  rtce_client.py        # Confluent RTCE API client
hooks/
  claude_code_hook.py   # Claude Code hook for automatic tracing
```

## License

Apache-2.0
