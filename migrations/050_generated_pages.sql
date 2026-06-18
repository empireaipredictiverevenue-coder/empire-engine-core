-- ─────────────────────────────────────────────────────────────────────────────
-- EMPIRE V49 · MIGRATION 050
-- generated_pages table — tracks all AI-generated landing pages & content
-- Used by the JARVIS Command Bridge dashboard to show page generation history
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.generated_pages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz,
    slug            text NOT NULL,
    page_type       text NOT NULL DEFAULT 'storm_landing',
    city            text,
    state           text,
    url             text,
    html_length     int DEFAULT 0,
    status          text NOT NULL DEFAULT 'active',
    source          text DEFAULT 'console',
    meta            jsonb DEFAULT '{}'::jsonb
);

-- Unique constraint: one slug per page type
CREATE UNIQUE INDEX IF NOT EXISTS idx_generated_pages_slug_type
    ON public.generated_pages (slug, page_type);

-- Index for listing by freshness
CREATE INDEX IF NOT EXISTS idx_generated_pages_created_at
    ON public.generated_pages (created_at DESC);

-- Index for filtering by type
CREATE INDEX IF NOT EXISTS idx_generated_pages_type
    ON public.generated_pages (page_type);

COMMENT ON TABLE public.generated_pages IS 'Tracks all AI-generated landing pages (storm, SEO, etc.) for the JARVIS Command Bridge dashboard';
COMMENT ON COLUMN public.generated_pages.slug IS 'URL slug, e.g. dallas-tx';
COMMENT ON COLUMN public.generated_pages.page_type IS 'storm_landing | seo_landing | pricing_page | custom';
COMMENT ON COLUMN public.generated_pages.source IS 'How the page was generated: console, bridge, automated';
