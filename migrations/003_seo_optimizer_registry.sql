-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION 003: SEO OPTIMIZER REGISTRY + COMPATIBILITY
-- ============================================================================
-- Run this in the Supabase SQL Editor to finalize the SEO optimizer pipeline.
--
-- This migration closes three schema gaps that block the SEO bot from
-- running end-to-end:
--
--   1. agent_registry           — NEW table. Required for the SEO agent
--                                 (and every other mesh bot) to write
--                                 heartbeats. Referenced in:
--                                   bots/seo_agent.py
--                                   bots/contractor_sniper.py
--                                   bots/agi_lane_engine.py
--                                   bots/predictive_revenue.py
--                                   bots/hermes_controller.py
--                                   bots/agi_revenue.py
--                                   bots/storm_predictor.py
--                                   bots/angi_scraper.py
--                                   bots/reddit_pulse.py
--                                   empire_agi_governor.py
--                                   hub.py
--                                   main.py
--
--   2. panel_court_decisions    — ALTER. The 001 migration created the
--                                 production columns (lead_id, verdict,
--                                 judge_reasoning, …). The SPA seed payload
--                                 in empire_seed.py also writes case_id,
--                                 panel_size, consensus_score, decision,
--                                 confidence, votes, reasoning, niches.
--                                 Adding them as nullable keeps the prod
--                                 panel_court.py insert path unchanged.
--
--   3. dream_memory             — ALTER. The 001 migration created
--                                 sources_analyzed / applied_rules / meta.
--                                 The SPA seed payload writes
--                                 collection_window_hours and sources
--                                 (without the _analyzed suffix). Adding
--                                 them as nullable lets the seed insert
--                                 without a column-mismatch error.
--
-- Every statement is idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS)
-- so this is safe to re-run.
-- ============================================================================


-- ── 1. AGENT REGISTRY (NEW) ────────────────────────────────────────────
-- Shared by every agent. Primary key = agent_name so upserts are simple.
CREATE TABLE IF NOT EXISTS agent_registry (
    agent_name    text PRIMARY KEY,
    status        text NOT NULL DEFAULT 'INACTIVE',  -- ACTIVE | INACTIVE | ERROR | STALE
    last_ping     timestamptz DEFAULT now(),
    enabled       boolean NOT NULL DEFAULT true,
    capabilities  jsonb DEFAULT '[]'::jsonb,         -- e.g. ["seo","content","keyword_research","audit"]
    meta          jsonb DEFAULT '{}'::jsonb,         -- agent-specific config (interval, model, …)
    created_at    timestamptz DEFAULT now(),
    updated_at    timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_registry_status    ON agent_registry (status);
CREATE INDEX IF NOT EXISTS idx_agent_registry_lastping  ON agent_registry (last_ping DESC);
CREATE INDEX IF NOT EXISTS idx_agent_registry_enabled   ON agent_registry (enabled) WHERE enabled = true;

-- Touch updated_at automatically on upsert
CREATE OR REPLACE FUNCTION _agent_registry_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_registry_touch ON agent_registry;
CREATE TRIGGER trg_agent_registry_touch
    BEFORE UPDATE ON agent_registry
    FOR EACH ROW EXECUTE FUNCTION _agent_registry_touch_updated_at();


-- ── 2. PANEL_COURT_DECISIONS (ALTER for SPA seed compat) ───────────────
ALTER TABLE panel_court_decisions
    ADD COLUMN IF NOT EXISTS case_id          text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS panel_size       integer DEFAULT 10,
    ADD COLUMN IF NOT EXISTS consensus_score numeric(5,3) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS decision         text DEFAULT NULL,   -- GO | GO_CAUTIOUS | NO_GO
    ADD COLUMN IF NOT EXISTS confidence       numeric(5,3) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS votes            jsonb DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS reasoning        text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS niches           jsonb DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_pc_decisions_case    ON panel_court_decisions (case_id);
CREATE INDEX IF NOT EXISTS idx_pc_decisions_niches  ON panel_court_decisions USING GIN (niches);
CREATE INDEX IF NOT EXISTS idx_pc_decisions_decision ON panel_court_decisions (decision);


-- ── 3. DREAM_MEMORY (ALTER for SPA seed compat) ────────────────────────
ALTER TABLE dream_memory
    ADD COLUMN IF NOT EXISTS collection_window_hours integer DEFAULT 24,
    ADD COLUMN IF NOT EXISTS sources                jsonb DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_dream_window ON dream_memory (collection_window_hours);


-- ── 4. SEO_KEYWORDS — verify coverage of 'last_outcome' values ─────────
-- 001 already declares: last_outcome text DEFAULT NULL.
-- Production writes 'success' / 'fail'; the seed writes 'booked' / 'clicked' /
-- 'read'. No schema change needed — text accepts both. (Comment-only entry.)


-- ── 5. RLS SANITY ──────────────────────────────────────────────────────
-- All three tables rely on the service role key. No additional RLS policies
-- are required because the bots connect with SUPABASE_SERVICE_KEY, which
-- bypasses RLS. (Comment-only entry.)


-- ============================================================================
-- VERIFICATION QUERIES (run separately after this migration)
-- ============================================================================
-- SELECT count(*) FROM agent_registry;            -- should return >= 0
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'panel_court_decisions'
--   ORDER BY ordinal_position;
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'dream_memory'
--   ORDER BY ordinal_position;
-- ============================================================================
