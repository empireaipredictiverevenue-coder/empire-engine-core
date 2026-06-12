-- ================================================================
-- EMPIRE V49 · PULSE ROLLUP
-- Created: 2026-06-12 · Updated: 2026-06-12 (full dims)
-- ================================================================
-- Materialized view refreshed every 5 min by a cron in hub.py.
-- Groups call_logs by hour, niche, corridor, channel, and contractor
-- to power the /view/pulse insight layer.
--
-- Requires 004_add_call_logs_columns.sql to be run first.
--
-- API consumers:
--   GET  /api/pulse/summary?window=24h|7d|30d
--   GET  /api/pulse/breakdown?dimension=niche|channel|contractor|corridor|hour
--   GET  /api/pulse/lanes
--   POST /api/pulse/refresh  (owner-only, force refresh)

CREATE MATERIALIZED VIEW IF NOT EXISTS pulse_rollup_hourly AS
SELECT
  date_trunc('hour', created_at) AS hour_bucket,
  niche,
  corridor,
  channel,
  contractor_id,
  SUM(fee_earned) FILTER (WHERE is_billable)              AS revenue,
  COUNT(*)                                                AS calls,
  SUM(cost_usd)                                           AS spend,
  SUM(fee_earned) FILTER (WHERE is_billable) - SUM(cost_usd) AS margin
FROM call_logs
WHERE created_at > now() - interval '7 days'
GROUP BY 1, 2, 3, 4, 5;

-- Unique index on the natural key of the rollup
CREATE UNIQUE INDEX IF NOT EXISTS pulse_rollup_hourly_pk
  ON pulse_rollup_hourly (hour_bucket, niche, corridor, channel, contractor_id);

-- Descending hour index for time-range queries
CREATE INDEX IF NOT EXISTS pulse_rollup_hourly_hour
  ON pulse_rollup_hourly (hour_bucket DESC);

-- Niche-only index for dimension breakdowns
CREATE INDEX IF NOT EXISTS pulse_rollup_hourly_niche
  ON pulse_rollup_hourly (niche, hour_bucket DESC);

-- Channel-only index for dimension breakdowns
CREATE INDEX IF NOT EXISTS pulse_rollup_hourly_channel
  ON pulse_rollup_hourly (channel, hour_bucket DESC);

-- Stored procedure for refreshing the materialized view.
-- Called by /api/pulse/refresh (owner-only) and the background cron in hub.py.
CREATE OR REPLACE FUNCTION refresh_pulse_rollup()
RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW pulse_rollup_hourly;
END;
$$ LANGUAGE plpgsql;
