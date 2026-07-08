-- Joins tool call start and end events by span_id to produce a single
-- enriched record per tool invocation.
-- Includes tool input/output for debugging.
-- Output topic: tool_call_completed
--
-- NOTE: Drop existing table first if recreating:
--   DROP TABLE `tool_call_completed`;

CREATE TABLE `tool_call_completed` AS
SELECT
    s.`trace_id`,
    s.`span_id`,
    s.`parent_span_id`,
    s.`service_name`,
    s.`tool_name`,
    s.`tool_input`,
    s.`timestamp`                   AS `start_time`,
    e.`timestamp`                   AS `end_time`,
    e.`duration_ms`,
    e.`tool_output`,
    e.`success`,
    e.`error`
FROM `agent_trace_events` s
JOIN `agent_trace_events` e
    ON s.`span_id` = e.`span_id`
    AND e.`$rowtime` BETWEEN s.`$rowtime` AND s.`$rowtime` + INTERVAL '10' MINUTES
WHERE s.`event_type` = 'tool_call.start'
  AND e.`event_type` = 'tool_call.end';
