-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION: SEO + PANEL COURT TABLES
-- ============================================================================
-- Run this in the Supabase SQL Editor to create the tables required by:
--   bots/seo_agent.py      — seo_audits, seo_keywords, seo_content, seo_genome_history
--   bots/panel_court.py    — panel_court_decisions
-- ============================================================================

-- ── seo_audits: website audit results ──────────────────────────────
CREATE TABLE IF NOT EXISTS seo_audits (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    url             text NOT NULL,
    niche           text NOT NULL DEFAULT 'Local SEO & HVAC',
    overall_score   integer DEFAULT 0,
    meta_score      integer DEFAULT 0,
    content_score   integer DEFAULT 0,
    technical_score integer DEFAULT 0,
    issues_json     jsonb DEFAULT '{}'::jsonb,
    recommended_title       text DEFAULT '',
    recommended_description text DEFAULT '',
    priority_actions        jsonb DEFAULT '[]'::jsonb,
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_audits_niche    ON seo_audits (niche);
CREATE INDEX IF NOT EXISTS idx_seo_audits_created  ON seo_audits (created_at DESC);


-- ── seo_keywords: keyword tracking with conversion metrics ─────────
CREATE TABLE IF NOT EXISTS seo_keywords (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    keyword         text NOT NULL,
    niche           text NOT NULL DEFAULT 'Local SEO & HVAC',
    metro           text NOT NULL DEFAULT 'national',
    intent_score    integer DEFAULT 50,
    volume_estimate text DEFAULT 'medium',          -- low | medium | high
    competition     text DEFAULT 'medium',          -- low | medium | high
    category        text DEFAULT 'transactional',   -- transactional | informational | navigational
    last_researched timestamptz DEFAULT now(),
    -- Conversion metrics (updated by record_outcome)
    conversions     integer DEFAULT 0,
    impressions     integer DEFAULT 0,
    conversion_rate numeric(5,3) DEFAULT 0,
    total_revenue   numeric(12,2) DEFAULT 0,
    last_outcome    text DEFAULT NULL,              -- 'success' | 'fail'
    last_outcome_ts timestamptz DEFAULT NULL,
    UNIQUE (keyword, niche, metro)
);

CREATE INDEX IF NOT EXISTS idx_seo_keywords_niche   ON seo_keywords (niche);
CREATE INDEX IF NOT EXISTS idx_seo_keywords_conv    ON seo_keywords (conversion_rate DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_seo_keywords_metro   ON seo_keywords (metro);


-- ── seo_content: generated content pieces with attribution ─────────
CREATE TABLE IF NOT EXISTS seo_content (
    id                uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    keyword           text NOT NULL,
    niche             text NOT NULL DEFAULT 'Local SEO & HVAC',
    metro             text NOT NULL DEFAULT 'national',
    title_tag         text DEFAULT '',
    meta_description  text DEFAULT '',
    h1                text DEFAULT '',
    body              text DEFAULT '',
    cta               text DEFAULT '',
    secondary_keywords jsonb DEFAULT '[]'::jsonb,
    genome_snapshot   jsonb DEFAULT '{}'::jsonb,
    created_at        timestamptz DEFAULT now(),
    -- Attribution (updated by record_outcome when a lead converts)
    attributed_lead_id text DEFAULT NULL,
    attributed_at      timestamptz DEFAULT NULL,
    converted          boolean DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_seo_content_keyword ON seo_content (keyword);
CREATE INDEX IF NOT EXISTS idx_seo_content_created  ON seo_content (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_seo_content_conv     ON seo_content (converted) WHERE converted IS NOT NULL;


-- ── seo_genome_history: genome evolution snapshots ─────────────────
CREATE TABLE IF NOT EXISTS seo_genome_history (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    generation          integer NOT NULL,
    genome              jsonb NOT NULL DEFAULT '{}'::jsonb,
    top_keywords        jsonb DEFAULT '[]'::jsonb,
    avg_conversion_rate numeric(5,3) DEFAULT 0,
    created_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_genome_gen    ON seo_genome_history (generation DESC);
CREATE INDEX IF NOT EXISTS idx_seo_genome_created ON seo_genome_history (created_at DESC);


-- ── panel_court_decisions: 10-agent ensemble results ───────────────
CREATE TABLE IF NOT EXISTS panel_court_decisions (
    id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    lead_id             text DEFAULT '',
    lead_summary        text DEFAULT '',
    winner_agent_id     integer DEFAULT 0,
    score               numeric(5,1) DEFAULT 0,
    verdict             text DEFAULT 'REJECT',      -- DISPATCH | REJECT
    per_agent_scores    jsonb DEFAULT '{}'::jsonb,  -- {1: 82.3, 2: 75.0, ...}
    agent_outputs       jsonb DEFAULT '[]'::jsonb,  -- [{agent_id, quality_score, reasoning, ...}]
    panel_votes         jsonb DEFAULT '{}'::jsonb,  -- {cfo: {scores:...}, growth_coach: {scores:...}, ...}
    judge_reasoning     text DEFAULT '',
    hybrid_reasoning    text DEFAULT '',
    agent_critiques     jsonb DEFAULT '[]'::jsonb,  -- [{critic_id, target_id, critique_text, severity, ...}]
    agent_pool_snapshot jsonb DEFAULT '[]'::jsonb,  -- [{id, temperature, wins, losses, win_rate, ...}]
    created_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pc_decisions_created ON panel_court_decisions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pc_decisions_verdict ON panel_court_decisions (verdict);
CREATE INDEX IF NOT EXISTS idx_pc_decisions_winner  ON panel_court_decisions (winner_agent_id);
