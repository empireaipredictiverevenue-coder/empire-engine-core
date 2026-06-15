-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 037: SEO BACKLINKS
-- ────────────────────────────────────────────────────────────────────────
-- Tables for the backlinks monitoring agent (bots/backlinks_agent.py).
-- Tracks referring domains, broken link status, and scan history for
-- each monitored target domain.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS seo_backlinks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Identity (unique pair)
    target_domain       text NOT NULL,           -- the site being tracked (e.g. empire-ai.co.uk)
    referring_domain    text NOT NULL,           -- the site linking to us (e.g. angel.co)

    -- Link metadata
    referring_url       text,                    -- full URL of the referring page
    link_type           text DEFAULT 'unknown',  -- e.g. Social Share, Business Directory, Editorial, Forum
    domain_authority    numeric(4,3),            -- 0.000-1.000 estimated quality score

    -- Status
    is_broken           boolean NOT NULL DEFAULT false,
    first_seen          timestamptz,
    last_checked        timestamptz,

    -- Meta
    notes               text,
    meta                jsonb DEFAULT '{}'::jsonb,

    -- Unique constraint for upsert
    UNIQUE (target_domain, referring_domain)
);

CREATE TABLE IF NOT EXISTS seo_backlink_scans (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),

    -- Scan metadata
    domain              text NOT NULL,
    backlinks_found     int DEFAULT 0,
    backlinks_saved     int DEFAULT 0,
    broken_found        int DEFAULT 0,
    status              text DEFAULT 'complete',
    duration_seconds    numeric(8,2),

    -- Meta
    notes               text,
    meta                jsonb DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX IF NOT EXISTS seo_backlinks_target_idx
    ON seo_backlinks (target_domain);

CREATE INDEX IF NOT EXISTS seo_backlinks_ref_idx
    ON seo_backlinks (referring_domain);

CREATE INDEX IF NOT EXISTS seo_backlinks_broken_idx
    ON seo_backlinks (is_broken)
    WHERE is_broken = true;

CREATE INDEX IF NOT EXISTS seo_backlinks_da_idx
    ON seo_backlinks (domain_authority DESC);

CREATE INDEX IF NOT EXISTS seo_backlink_scans_domain_idx
    ON seo_backlink_scans (domain, created_at DESC);

-- Auto-update updated_at on seo_backlinks
CREATE OR REPLACE FUNCTION _seo_backlinks_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS seo_backlinks_updated_at ON seo_backlinks;
CREATE TRIGGER seo_backlinks_updated_at
    BEFORE UPDATE ON seo_backlinks
    FOR EACH ROW
    EXECUTE FUNCTION _seo_backlinks_updated_at();

COMMENT ON TABLE  seo_backlinks IS 'Backlinks monitored by the backlinks_agent — one row per referring domain per target domain';
COMMENT ON TABLE  seo_backlink_scans IS 'Scan history — tracks each full cycle run by the backlinks_agent';
COMMENT ON COLUMN seo_backlinks.domain_authority IS 'Estimated quality score 0.0-1.0 based on TLD, known authority, and heuristics';
COMMENT ON COLUMN seo_backlinks.link_type IS 'Category of the link: Social Share, Business Directory, Editorial, Industry Directory, etc.';
