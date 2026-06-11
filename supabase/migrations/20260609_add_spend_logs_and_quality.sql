-- ═══════════════════════════════════════════════════════════════════
-- CALL INTELLIGENCE & MARGIN HUB
-- Migration 3: spend_logs table + quality score columns
-- ═══════════════════════════════════════════════════════════════════

-- 1. SPEND LOGS — ad spend tracking per campaign/metro
CREATE TABLE IF NOT EXISTS spend_logs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    campaign_id       text,
    metro             text NOT NULL,
    niche             text NOT NULL DEFAULT 'roofing',
    source            text DEFAULT 'corridor',      -- corridor, manual, facebook, google
    impressions       int DEFAULT 0,
    clicks            int DEFAULT 0,
    cost_per_impression numeric(12,6) DEFAULT 0,
    cost_per_click      numeric(12,6) DEFAULT 0,
    total_spend         numeric(12,2) NOT NULL DEFAULT 0,
    meta                jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS spend_logs_metro_idx ON spend_logs (metro, created_at DESC);
CREATE INDEX IF NOT EXISTS spend_logs_campaign_idx ON spend_logs (campaign_id);

-- 2. QUALITY SCORE COLUMNS on call_logs
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS transcript_text  text;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS quality_score    numeric(4,3);         -- 0.000 - 1.000 overall
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS qualification_score numeric(4,3);     -- script adherence
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS sentiment_score    numeric(4,3);      -- customer satisfaction
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS churn_risk         numeric(4,3);      -- early-drop risk
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS scored_at          timestamptz;       -- when quality bot ran
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_url      text;              -- Vonage recording URL

CREATE INDEX IF NOT EXISTS call_logs_scored_idx ON call_logs (scored_at) WHERE scored_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS call_logs_quality_idx ON call_logs (quality_score) WHERE quality_score IS NOT NULL;

COMMENT ON TABLE spend_logs IS 'Ad spend per campaign/metro for margin calculations';
COMMENT ON COLUMN call_logs.quality_score IS 'Overall call quality 0-1 from AI analyst';
COMMENT ON COLUMN call_logs.qualification_score IS 'Script adherence score 0-1';
COMMENT ON COLUMN call_logs.sentiment_score IS 'Customer sentiment score 0-1';
COMMENT ON COLUMN call_logs.churn_risk IS 'Early-drop risk score 0-1 (higher = riskier)';
