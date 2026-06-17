-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 039: PUBLISHER PORTAL
-- ────────────────────────────────────────────────────────────────────────
-- Self-serve publisher accounts: signup, magic-link login, API key
-- management, embed code generation, and earnings dashboard.
--
-- Each publisher can create multiple ad slots (via the existing ad_slots
-- table). Performance data is aggregated from ad_impressions + ad_clicks
-- keyed on publisher_id.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS publishers (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Identity
    email               text NOT NULL UNIQUE,
    name                text NOT NULL,              -- business / publisher name
    website             text NOT NULL DEFAULT '',    -- their site URL
    contact_name        text NOT NULL DEFAULT '',

    -- Auth
    api_key             text NOT NULL DEFAULT '',    -- auto-generated on signup
    password_hash       text DEFAULT '',             -- reserved for future password auth

    -- Status
    is_active           boolean NOT NULL DEFAULT false,  -- false until email verified
    status              text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'suspended')),

    -- Payout
    revenue_share_pct   numeric(5,2) DEFAULT 70.00, -- default rev share (they get 70%)
    payout_method       text DEFAULT 'manual',       -- 'manual', 'paypal', 'stripe'
    payout_address      text DEFAULT '',

    -- Meta
    notes               text,
    meta                jsonb DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX IF NOT EXISTS publishers_email_idx ON publishers (email);
CREATE INDEX IF NOT EXISTS publishers_api_key_idx ON publishers (api_key);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION _publishers_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS publishers_updated_at ON publishers;
CREATE TRIGGER publishers_updated_at
    BEFORE UPDATE ON publishers
    FOR EACH ROW EXECUTE FUNCTION _publishers_updated_at();

COMMENT ON TABLE publishers IS 'Self-serve ad network publisher accounts — signup, embed code, earnings dashboard';
