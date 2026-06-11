-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION: MODEL BENCHMARK + ALERTS TABLES
-- ============================================================================
-- Run this in the Supabase SQL Editor to create the tables required by:
--   scripts/nightly_model_benchmark.py   — nightly benchmark + auto-switch
-- ============================================================================

-- ── model_benchmark: per-night quality stats for the active Ollama model ──
CREATE TABLE IF NOT EXISTS model_benchmark (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          timestamptz DEFAULT now(),
    model               text NOT NULL,
    n_calls             int NOT NULL,
    success_count       int NOT NULL,
    success_rate        numeric(5,3) NOT NULL,        -- 0.000 to 1.000
    p50_latency_s       numeric(6,2) NOT NULL,
    p95_latency_s       numeric(6,2) NOT NULL,
    max_latency_s       numeric(6,2) NOT NULL,
    csv_path            text,
    note                text DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_model_benchmark_model_created
    ON model_benchmark (model, created_at DESC);


-- ── model_alerts: model-switch events (one row per switch attempt) ────────
CREATE TABLE IF NOT EXISTS model_alerts (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at          timestamptz DEFAULT now(),
    from_model          text NOT NULL,
    to_model            text NOT NULL,
    reason              text NOT NULL,                 -- e.g. "3 consecutive nights <70% success"
    consecutive_nights  int NOT NULL,                  -- how many nights triggered the threshold
    success_rates       numeric(5,3)[] NOT NULL,       -- the 3 rates that triggered
    switched            bool DEFAULT false,            -- true if the worker was actually restarted
    ntfy_sent           bool DEFAULT false,            -- true if the operator was notified
    note                text DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_model_alerts_created
    ON model_alerts (created_at DESC);
