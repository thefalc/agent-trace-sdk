-- Computes per-minute health metrics across all agents from the
-- completed LLM call records: throughput, latency percentiles, error rate.
-- Output topic: agent_health_metrics
-- Depends on: 01_llm_call_completed.sql

CREATE TABLE `agent_health_metrics` AS
SELECT
    window_start,
    window_end,
    `service_name`,
    `model`,
    COUNT(*)                                        AS `call_count`,
    COUNT(CASE WHEN `error` IS NOT NULL THEN 1 END) AS `error_count`,
    AVG(`duration_ms`)                              AS `avg_duration_ms`,
    MAX(`duration_ms`)                              AS `max_duration_ms`,
    SUM(COALESCE(`input_tokens`, 0))                AS `total_input_tokens`,
    SUM(COALESCE(`output_tokens`, 0))               AS `total_output_tokens`
FROM TABLE(
    TUMBLE(TABLE `llm_call_completed`, DESCRIPTOR(`$rowtime`), INTERVAL '1' MINUTE)
)
GROUP BY window_start, window_end, `service_name`, `model`;
