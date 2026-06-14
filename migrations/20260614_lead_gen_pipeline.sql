-- Empire AI · Predictive Revenue
-- Lead-Gen Pipeline: enriched_leads, outreach_log, agent_activity, agent_config
-- All four tables are needed by the 3-agent pipeline (scanner → enricher → converter).
-- Migration is idempotent (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).
-- See notes/lead_gen_conversions_agent_plan.md for the design.

-- ─────────────────────────────────────────────────────────────────────
-- enriched_leads: output of the scanner + enricher, input to the converter
-- One row per real lead, keyed by the radar_target_id it came from.
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS enriched_leads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    radar_target_id UUID,                                       -- FK to radar_targets.id, NULL = manually seeded
    address         TEXT,
    city            TEXT,
    state           TEXT,
    phone           TEXT,
    email           TEXT,
    warehouse_name  TEXT,
    asset_value     NUMERIC,
    source          TEXT,                                       -- 'radar_targets' | 'manual' | 'leads'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score           NUMERIC,                                    -- populated by lead_enricher; 0.0–10.0
    status          TEXT NOT NULL DEFAULT 'pending_enrichment' -- 'pending_enrichment' | 'pending_outreach' | 'blocked' | 'converted' | 'opted_out'
                    CHECK (status IN ('pending_enrichment','pending_outreach','blocked','converted','opted_out','rejected')),
    last_enriched_at TIMESTAMPTZ,
    meta            JSONB DEFAULT '{}'::jsonb,                  -- enrichment trace + custom fields
    UNIQUE (radar_target_id)                                    -- one enriched row per radar target
);
CREATE INDEX IF NOT EXISTS enriched_leads_status_idx   ON enriched_leads (status, score DESC);
CREATE INDEX IF NOT EXISTS enriched_leads_created_idx  ON enriched_leads (created_at DESC);
CREATE INDEX IF NOT EXISTS enriched_leads_phone_idx    ON enriched_leads (phone) WHERE phone IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────
-- outreach_log: every would-send (dry-run) or did-send (live) is recorded
-- Critical for: TCPA audit trail, conversion analytics, script A/B testing
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enriched_lead_id    UUID REFERENCES enriched_leads(id) ON DELETE CASCADE,
    agent_name          TEXT NOT NULL,                          -- 'lead_converter'
    run_id              UUID NOT NULL,                          -- groups attempts in one agent run
    channel             TEXT NOT NULL CHECK (channel IN ('sms','voice','email')),
    sequence            TEXT,                                   -- 'storm_strike' | 'contractor_recruit' | 'lead_nurture' | 'manual'
    step                INTEGER,                                -- which step in the sequence (1, 2, 3 ...)
    body_preview        TEXT,                                   -- first 280 chars of the body
    would_send_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    compliance_passed   BOOLEAN NOT NULL,
    compliance_block_reason TEXT,                                -- if !compliance_passed
    mode                TEXT NOT NULL CHECK (mode IN ('dry_run','live')),
    sent_at             TIMESTAMPTZ,                            -- NULL in dry_run; populated in live
    sent_status         TEXT,                                   -- 'queued' | 'delivered' | 'failed' | 'no_answer' (live only)
    response_received_at TIMESTAMPTZ,
    response_text       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS outreach_log_lead_idx   ON outreach_log (enriched_lead_id, would_send_at DESC);
CREATE INDEX IF NOT EXISTS outreach_log_mode_idx   ON outreach_log (mode, would_send_at DESC);
CREATE INDEX IF NOT EXISTS outreach_log_run_idx    ON outreach_log (run_id);

-- ─────────────────────────────────────────────────────────────────────
-- agent_activity: per-run health, errors, summary. The "did it work?" ledger.
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_activity (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      TEXT NOT NULL,                              -- 'lead_scanner' | 'lead_enricher' | 'lead_converter'
    run_id          UUID NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','error','skipped_disabled')),
    rows_seen       INTEGER DEFAULT 0,
    rows_processed  INTEGER DEFAULT 0,
    rows_blocked    INTEGER DEFAULT 0,
    rows_errored    INTEGER DEFAULT 0,
    error           TEXT,
    summary         TEXT
);
CREATE INDEX IF NOT EXISTS agent_activity_agent_idx ON agent_activity (agent_name, started_at DESC);

-- ─────────────────────────────────────────────────────────────────────
-- agent_config: per-agent on/off switch + dry-run toggle + last-run stamp
-- The agents read this at the start of every run.
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_config (
    agent_name      TEXT PRIMARY KEY,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    dry_run         BOOLEAN NOT NULL DEFAULT TRUE,              -- default TRUE: all 3 agents start in dry-run
    last_run_at     TIMESTAMPTZ,
    last_run_status TEXT,
    config_json     JSONB DEFAULT '{}'::jsonb,                  -- agent-specific knobs (cadence, max_per_run, etc.)
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed configs for all 3 agents. All start in dry-run, enabled.
INSERT INTO agent_config (agent_name, enabled, dry_run, config_json) VALUES
    ('lead_scanner',   TRUE, TRUE, '{"max_per_run": 100, "lookback_hours": 2}'::jsonb),
    ('lead_enricher',  TRUE, TRUE, '{"max_per_run": 100, "min_score_threshold": 1.0}'::jsonb),
    ('lead_converter', TRUE, TRUE, '{"max_per_run": 10,  "channels": ["sms","voice"], "default_sequence": "storm_strike"}'::jsonb)
ON CONFLICT (agent_name) DO NOTHING;
