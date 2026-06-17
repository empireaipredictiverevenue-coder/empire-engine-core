-- 044_idle_asset_pipeline.sql
-- Idle Asset Pipeline — Enrichment + Multi-Model Scoring + Outreach Tracking
--
-- Tables:
--   idle_asset_enriched  — enriched compounds with business identity + 3-model scores
--   idle_asset_outreach  — outreach attempts per compound/channel/business model

CREATE TABLE IF NOT EXISTS idle_asset_enriched (
    compound_id TEXT PRIMARY KEY REFERENCES logistics_compounds(compound_id),
    business_name TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    industry TEXT,
    lead_gen_score FLOAT8 DEFAULT 0.0,       -- value to logistics brokers
    consulting_score FLOAT8 DEFAULT 0.0,      -- waste audit value
    marketplace_score FLOAT8 DEFAULT 0.0,     -- idle capacity match value
    best_model TEXT,                          -- lead_gen / consulting / marketplace
    enrichment_source TEXT DEFAULT 'osm_metadata',
    enrichment_confidence FLOAT8 DEFAULT 0.0,
    status TEXT DEFAULT 'enriched',
    enriched_at TIMESTAMPTZ DEFAULT NOW(),
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_idle_asset_enriched_best_model
    ON idle_asset_enriched(best_model);
CREATE INDEX IF NOT EXISTS idx_idle_asset_enriched_lead_gen_score
    ON idle_asset_enriched(lead_gen_score DESC);
CREATE INDEX IF NOT EXISTS idx_idle_asset_enriched_status
    ON idle_asset_enriched(status);

CREATE TABLE IF NOT EXISTS idle_asset_outreach (
    compound_id TEXT REFERENCES logistics_compounds(compound_id),
    channel TEXT NOT NULL,                    -- email / sms
    business_model TEXT NOT NULL,             -- lead_gen / consulting / marketplace
    status TEXT DEFAULT 'enrolled',           -- enrolled / sent / replied / bounced / opted_out
    sequence_id TEXT,
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    last_contact_at TIMESTAMPTZ,
    meta JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (compound_id, channel, business_model)
);

CREATE INDEX IF NOT EXISTS idx_idle_asset_outreach_status
    ON idle_asset_outreach(status);
CREATE INDEX IF NOT EXISTS idx_idle_asset_outreach_model
    ON idle_asset_outreach(business_model);
