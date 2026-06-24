-- EMPIRE V49 · Migration 20260624: seo_rankings table
-- =====================================================
-- Stores ranking predictions from products/seo_idea_to_shipped/ranking_predictor.py.
-- Used by the SEO Idea-to-Shipped engine for predictive ranking, gap analysis,
-- and shipping plan generation.
--
-- Writes happen via RankingPredictor._persist_prediction().
-- Reads happen via /api/v1/seo/rankings/* endpoints.

CREATE TABLE IF NOT EXISTS seo_rankings (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    url               TEXT NOT NULL,
    keyword           TEXT NOT NULL,
    niche             TEXT DEFAULT '',
    metro             TEXT DEFAULT '',
    predicted_position INTEGER NOT NULL DEFAULT 50,
    confidence        REAL NOT NULL DEFAULT 0.5,
    factors           JSONB DEFAULT '{}'::jsonb,
    predicted_by      TEXT DEFAULT '',
    predicted_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for querying latest prediction per URL+keyword pair
CREATE INDEX IF NOT EXISTS idx_seo_rankings_url_keyword
    ON seo_rankings (url, keyword);

-- Index for chronological queries (time-series dashboards)
CREATE INDEX IF NOT EXISTS idx_seo_rankings_predicted_at
    ON seo_rankings (predicted_at DESC);

-- Index for niche-based filtering
CREATE INDEX IF NOT EXISTS idx_seo_rankings_niche
    ON seo_rankings (niche) WHERE niche != '';

COMMENT ON TABLE seo_rankings IS
    'SEO ranking predictions from the Idea-to-Shipped engine. One row per prediction.';
