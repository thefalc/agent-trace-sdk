-- Extracts session.end events into a dedicated session summary table.
-- These already contain aggregated stats (total calls, tokens, duration)
-- computed by the SDK's SessionSpan.
-- Output topic: session_summaries

CREATE TABLE `session_summaries` AS
SELECT
    `trace_id`,
    `span_id`,
    `service_name`,
    `timestamp`,
    `duration_ms`,
    `total_llm_calls`,
    `total_tool_calls`,
    `total_input_tokens`,
    `total_output_tokens`,
    `exit_reason`,
    `error`
FROM `agent_trace_events`
WHERE `event_type` = 'session.end';
