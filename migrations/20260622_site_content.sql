-- ============================================================================
-- Empire AI · B2B Site Content Migration
-- ============================================================================
-- Stores cleaned text from Crawlee-crawled B2B lead websites.
-- Feeds the STORM copywriting engine with real business language for
-- targeted ad copy, email sequences, and landing page generation.
--
-- One row per (b2b_lead_id, page_url) — idempotent on re-crawl.
-- ============================================================================

CREATE TABLE IF NOT EXISTS site_content (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    b2b_lead_id     UUID NOT NULL REFERENCES b2b_leads(id) ON DELETE CASCADE,
    company_name    TEXT,
    website         TEXT,          -- the lead's main website URL
    page_url        TEXT NOT NULL, -- the specific page URL crawled
    page_type       TEXT NOT NULL DEFAULT 'homepage',  -- homepage|services|pricing|contact|about|other
    title           TEXT,          -- <title> tag content
    meta_desc       TEXT,          -- <meta name="description"> content    headings        JSONB DEFAULT '[]',  -- H1/H2 headings extracted from the page
    raw_text        TEXT,          -- cleaned body text (no nav, no scripts, no boilerplate)
    word_count      INTEGER DEFAULT 0,
    pricing_mentions JSONB DEFAULT '[]', -- extracted pricing snippets: [{text, amount, period, currency}]
    cta_buttons     JSONB DEFAULT '[]',  -- extracted CTA button text: [{text, link, context}]
    contact_info    JSONB DEFAULT '{}',  -- {email, phone, form_url} found on page
    crawl_status    TEXT NOT NULL DEFAULT 'pending',  -- pending|crawling|done|failed
    crawl_error     TEXT,          -- error message if crawl failed
    crawl_duration_ms INTEGER,     -- time spent crawling this page
    meta            JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_site_content_lead     ON site_content (b2b_lead_id);
CREATE INDEX IF NOT EXISTS idx_site_content_page_type ON site_content (page_type);
CREATE INDEX IF NOT EXISTS idx_site_content_status   ON site_content (crawl_status);
CREATE INDEX IF NOT EXISTS idx_site_content_updated   ON site_content (updated_at DESC);

-- Unique constraint: one row per (lead, page_url)
CREATE UNIQUE INDEX IF NOT EXISTS uq_site_content_lead_page 
    ON site_content (b2b_lead_id, page_url);

-- Note: updated_at auto-update is handled by application code (pipeline sets updated_at).
-- If a trigger is preferred, create it with:
--   CREATE TRIGGER trg_site_content_updated_at BEFORE UPDATE ON site_content
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
-- (requires the function from a prior migration).
