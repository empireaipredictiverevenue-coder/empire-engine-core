-- Migration 024: storm_risk_log (per-run history for the Warp Scout storm predictor)
--
-- Replaces the single-row upsert pattern in bots/storm_predictor.py (storm_forecasts
-- table) with a per-run history. Lets us see risk over time, alert on changes,
-- and trace which storm window produced which leads.

CREATE TABLE IF NOT EXISTS public.storm_risk_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    source      text NOT NULL DEFAULT 'warp_scout',  -- which agent produced it
    run_id      uuid,                                -- agent_activity.run_id
    metro       text NOT NULL,
    day         int  NOT NULL,                       -- 1, 2, 3
    risk_level  text NOT NULL,                       -- "Thunderstorm", "Marginal", "Slight", "Enhanced", "Moderate", "High"
    risk_rank   int  NOT NULL,                       -- 1..6, for sorting
    lat         double precision,
    lon         double precision
);

CREATE INDEX IF NOT EXISTS storm_risk_log_metro_created_at_idx
    ON public.storm_risk_log (metro, created_at DESC);

CREATE INDEX IF NOT EXISTS storm_risk_log_created_at_idx
    ON public.storm_risk_log (created_at DESC);

-- Backfill: nothing to backfill (this is a new table)
