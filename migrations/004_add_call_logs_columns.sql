-- ================================================================
-- EMPIRE V49 · ADD CALL_LOGS COLUMNS
-- Created: 2026-06-12
-- ================================================================
-- Adds dimensional columns required by the pulse_rollup_hourly
-- materialized view so it can group by corridor, channel, and
-- contractor_id, and compute spend/margin from cost_usd.
--
-- After this migration, re-run 003_pulse_rollup.sql to recreate
-- the materialized view with full dimensionality.

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS corridor      text;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS channel       text;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS contractor_id uuid;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS cost_usd      numeric DEFAULT 0;
