-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 041: ENRICHMENT ENGINE — Quality Tracking + Pipeline State
-- ────────────────────────────────────────────────────────────────────────
-- Tracks per-source enrichment quality, per-niche source performance,
-- and pipeline DAG state.
-- ────────────────────────────────────────────────────────────────────────

-- Enrichment sources registry — each source + strategy combination
CREATE TABLE IF NOT EXISTS enrichment_sources (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    
    source_name         text NOT NULL,           -- 'website_scrape', 'google_places', 'hunter_io', etc.
    strategy            text NOT NULL DEFAULT 'default', -- 'regex_fast', 'llm_deep', 'pattern_guess'
    niche               text DEFAULT '__all__',  -- which niche this source is tuned for
    
    -- Reliability tracking
    attempts            integer DEFAULT 0,
    successes           integer DEFAULT 0,
    total_confidence    numeric(10,4) DEFAULT 0.0000,  -- sum of confidence scores
    avg_response_ms     numeric(10,2) DEFAULT 0.00,
    
    -- Field-level accuracy (which fields this source is good at)
    fields_found        text[] DEFAULT '{}',     -- fields this source typically finds
    
    -- Status
    is_active           boolean DEFAULT true,
    priority            integer DEFAULT 5,       -- 1 (highest) to 10 (lowest)
    
    meta                jsonb DEFAULT '{}'::jsonb,
    UNIQUE (source_name, strategy, niche)
);

-- Enrichment pipeline runs — DAG execution tracking
CREATE TABLE IF NOT EXISTS enrichment_pipeline_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    
    run_type            text NOT NULL DEFAULT 'batch'
        CHECK (run_type IN ('batch', 'realtime', 'scheduled')),
    
    -- Pipeline state
    current_step        text NOT NULL DEFAULT 'pending',
    status              text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'partial')),
    
    -- Per-step tracking
    steps               jsonb DEFAULT '[]'::jsonb,  -- [{step, started_at, finished_at, rows_in, rows_out, status}]
    
    -- Results
    total_rows          integer DEFAULT 0,
    rows_processed      integer DEFAULT 0,
    rows_errored        integer DEFAULT 0,
    error               text,
    
    meta                jsonb DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX IF NOT EXISTS enrichment_sources_niche_idx ON enrichment_sources (niche, priority);
CREATE INDEX IF NOT EXISTS enrichment_sources_active_idx ON enrichment_sources (is_active, attempts);
CREATE INDEX IF NOT EXISTS enrichment_pipeline_status_idx ON enrichment_pipeline_runs (status, created_at DESC);

-- Seed default enrichment sources
INSERT INTO enrichment_sources (source_name, strategy, niche, fields_found, priority) VALUES
    ('website_scrape', 'regex_fast', '__all__', ARRAY['email', 'phone', 'social_links'], 1),
    ('website_scrape', 'llm_deep', '__all__', ARRAY['services', 'niche', 'location', 'business_name'], 2),
    ('google_places', 'default', '__all__', ARRAY['phone', 'address', 'website'], 3),
    ('email_pattern_guess', 'default', '__all__', ARRAY['email'], 10)
ON CONFLICT (source_name, strategy, niche) DO NOTHING;

COMMENT ON TABLE enrichment_sources IS 'Enrichment source registry with per-niche quality tracking';
COMMENT ON TABLE enrichment_pipeline_runs IS 'DAG pipeline execution tracking for enrichment orchestration';
