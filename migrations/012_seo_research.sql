-- EMPIRE V49 · MIGRATION 012
-- ==========================
-- seo_research: Stores deep research results from the ResearchAgent
-- (property, market, competitor, storm_history, neighborhood, buyer_intent).
-- Used by the ContentAgent to generate landing pages, descriptions,
-- and other SEO-optimized content assets.

CREATE TABLE IF NOT EXISTS seo_research (
    id              BIGSERIAL PRIMARY KEY,
    research_type   TEXT NOT NULL,          -- property|market_trend|competitor|storm_history|neighborhood|buyer_intent
    niche           TEXT NOT NULL DEFAULT '',
    metro           TEXT NOT NULL DEFAULT '',
    zip_code        TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    findings        JSONB NOT NULL DEFAULT '{}',  -- Full research output from the agent
    confidence_level TEXT NOT NULL DEFAULT 'medium',  -- high|medium|low
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_seo_research_type ON seo_research (research_type);
CREATE INDEX IF NOT EXISTS idx_seo_research_niche ON seo_research (niche);
CREATE INDEX IF NOT EXISTS idx_seo_research_metro ON seo_research (metro);
CREATE INDEX IF NOT EXISTS idx_seo_research_zip   ON seo_research (zip_code);
CREATE INDEX IF NOT EXISTS idx_seo_research_created ON seo_research (created_at DESC);

-- Row-level security: service_role only (agents write via service key)
ALTER TABLE seo_research ENABLE ROW LEVEL SECURITY;

-- Service role can do anything
CREATE POLICY seo_research_service_policy
    ON seo_research
    USING (true)
    WITH CHECK (true);
