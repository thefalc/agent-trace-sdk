-- Joins LLM call start and end events by span_id to produce a single
-- enriched record per LLM invocation with computed duration.
-- Includes input/output content for debugging.
-- Output topic: llm_call_completed
--
-- NOTE: Drop existing table first if recreating:
--   DROP TABLE `llm_call_completed`;

CREATE TABLE `llm_call_completed` AS
SELECT
    s.`trace_id`,
    s.`span_id`,
    s.`parent_span_id`,
    s.`service_name`,
    s.`model`,
    s.`provider`,
    s.`temperature`,
    s.`max_tokens`,
    s.`timestamp`           AS `start_time`,
    e.`timestamp`           AS `end_time`,
    e.`duration_ms`,
    e.`input_tokens`,
    e.`output_tokens`,
    e.`total_tokens`,
    e.`response_content`,
    e.`finish_reason`,
    e.`error`
FROM `agent_trace_events` s
JOIN `agent_trace_events` e
    ON s.`span_id` = e.`span_id`
    AND e.`$rowtime` BETWEEN s.`$rowtime` AND s.`$rowtime` + INTERVAL '10' MINUTES
WHERE s.`event_type` = 'llm_call.start'
  AND e.`event_type` = 'llm_call.end';
