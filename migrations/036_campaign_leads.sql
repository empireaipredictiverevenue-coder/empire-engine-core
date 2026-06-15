-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 036: CAMPAIGN LEADS
-- ────────────────────────────────────────────────────────────────────────
-- Separate routing table for classified leads. The lead_scorer cron agent
-- reads from radar_targets + enriched_leads, classifies each lead's
-- temperature (hot/warm/cold), and writes here for other campaigns to
-- consume. This keeps the source tables clean and lets multiple campaign
-- pipelines read from one classified feed.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS campaign_leads (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Source references
    radar_target_id     uuid UNIQUE,            -- references radar_targets.id (unique for upsert)
    enriched_lead_id    uuid,                   -- references enriched_leads.id (nullable)

    -- Lead identity
    warehouse_name      text,
    address             text,
    city                text,
    state               text,
    phone               text,
    email               text,

    -- Classification (set by lead_scorer agent)
    temperature         text NOT NULL DEFAULT 'warm'
        CHECK (temperature IN ('hot', 'warm', 'cold')),

    -- Scores used for classification
    urgency_score       int,                    -- 0-10 from radar_targets
    enrichment_score    numeric(4,3),           -- 0.000-1.000 from enriched_leads
    composite_score     numeric(4,3),           -- weighted combination

    -- Campaign routing
    campaign            text DEFAULT 'default',  -- which campaign pipeline
    last_scored_at      timestamptz,            -- when lead_scorer last evaluated
    last_converted_at   timestamptz,            -- when this lead converted (if ever)

    -- Status lifecycle
    status              text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'converted', 'expired')),

    -- Meta
    source              text,                   -- original source of the lead
    notes               text,
    meta                jsonb DEFAULT '{}'::jsonb
);

-- Indexes for campaign routing lookups
CREATE INDEX IF NOT EXISTS campaign_leads_temp_idx
    ON campaign_leads (temperature, status, composite_score DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS campaign_leads_campaign_idx
    ON campaign_leads (campaign, status)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS campaign_leads_radar_idx
    ON campaign_leads (radar_target_id);

CREATE INDEX IF NOT EXISTS campaign_leads_phone_idx
    ON campaign_leads (phone)
    WHERE phone IS NOT NULL;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION _campaign_leads_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS campaign_leads_updated_at ON campaign_leads;
CREATE TRIGGER campaign_leads_updated_at
    BEFORE UPDATE ON campaign_leads
    FOR EACH ROW
    EXECUTE FUNCTION _campaign_leads_updated_at();

COMMENT ON TABLE  campaign_leads IS 'Classified leads routed to campaign pipelines by the lead_scorer agent';
COMMENT ON COLUMN campaign_leads.temperature IS 'hot=dispatch immediately, warm=nurture sequence, cold=long-tail retarget';
COMMENT ON COLUMN campaign_leads.composite_score IS 'Weighted combination of urgency + enrichment + recency (0.0-1.0)';
COMMENT ON COLUMN campaign_leads.campaign IS 'Campaign pipeline identifier, e.g. default, storm_strike, b2b_outreach, retarget';
