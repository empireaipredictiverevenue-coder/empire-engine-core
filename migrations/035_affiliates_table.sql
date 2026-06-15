-- EMPIRE V49 · DDL MIGRATION 035: AFFILIATES TABLE
-- ==================================================
-- Creates a dedicated affiliates table for the affiliate
-- recruitment program, separate from buyers.
--
-- Run: python3 scripts/run_migrations.py  (auto-discovered)
--   or: psql "$SUPABASE_DB_URL" -f migrations/035_affiliates_table.sql

-- ── 1. AFFILIATES TABLE ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.affiliates (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz,

    -- Identity
    name            text NOT NULL,
    email           text NOT NULL UNIQUE,
    phone           text,
    company         text DEFAULT '',

    -- Referral tracking
    referral_code   text NOT NULL UNIQUE,
    referred_by     uuid REFERENCES public.affiliates(id) ON DELETE SET NULL,

    -- Commission
    commission_rate numeric NOT NULL DEFAULT 0.10,  -- 10%
    payout_method   text DEFAULT 'usdc',            -- stripe | usdc | paypal
    payout_address  text DEFAULT '',
    min_payout_usd  numeric NOT NULL DEFAULT 50.00,

    -- Status
    status          text NOT NULL DEFAULT 'active',  -- active | paused | suspended
    is_active       boolean NOT NULL DEFAULT true,

    -- Stats (updated by triggers/app)
    total_clicks    integer NOT NULL DEFAULT 0,
    total_leads     integer NOT NULL DEFAULT 0,
    total_conversions integer NOT NULL DEFAULT 0,
    total_earned_usd numeric NOT NULL DEFAULT 0.00,
    total_paid_usd  numeric NOT NULL DEFAULT 0.00,

    -- Metadata
    notes           text DEFAULT '',
    metadata        jsonb DEFAULT '{}'::jsonb,
    source          text DEFAULT 'web_form',         -- web_form | referral | manual

    -- Tracking pixel last seen
    last_click_at   timestamptz,
    last_lead_at    timestamptz
);

-- ── 2. INDEXES ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS affiliates_email_idx
    ON public.affiliates (email);
CREATE INDEX IF NOT EXISTS affiliates_referral_code_idx
    ON public.affiliates (referral_code);
CREATE INDEX IF NOT EXISTS affiliates_status_idx
    ON public.affiliates (status);
CREATE INDEX IF NOT EXISTS affiliates_referred_by_idx
    ON public.affiliates (referred_by);

-- ── 3. AUTO-UPDATE updated_at ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.affiliates_set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS affiliates_updated_at ON public.affiliates;
CREATE TRIGGER affiliates_updated_at
    BEFORE UPDATE ON public.affiliates
    FOR EACH ROW
    EXECUTE FUNCTION public.affiliates_set_updated_at();

-- ── 4. REFERRAL CODE GENERATION FUNCTION ──────────────────────────────
CREATE OR REPLACE FUNCTION public.generate_affiliate_code(name text)
RETURNS text AS $$
DECLARE
    base text;
    suffix text;
    code text;
BEGIN
    -- Normalize: lowercase, replace spaces with hyphens, remove non-alphanumeric
    base := LOWER(REGEXP_REPLACE(TRIM(name), '[^a-zA-Z0-9 ]+', '', 'g'));
    base := REPLACE(base, ' ', '-');
    -- Truncate to 20 chars
    base := LEFT(base, 20);
    -- Add 4-char random suffix
    suffix := SUBSTR(MD5(RANDOM()::text), 1, 4);
    code := base || '-' || suffix;
    RETURN code;
END;
$$ LANGUAGE plpgsql;

-- ── 5. AFFILIATE STATS VIEW (comprehensive) ───────────────────────────
CREATE OR REPLACE VIEW public.affiliate_performance AS
SELECT
    a.id,
    a.name,
    a.email,
    a.referral_code,
    a.commission_rate,
    a.status,
    a.total_clicks,
    a.total_leads,
    a.total_conversions,
    a.total_earned_usd,
    a.total_paid_usd,
    a.created_at,
    a.last_click_at,
    a.last_lead_at,
    -- Computed fields
    CASE WHEN a.total_earned_usd > 0
         THEN ROUND((a.total_paid_usd / a.total_earned_usd) * 100, 1)
         ELSE 0
    END AS payout_ratio,
    CASE WHEN a.total_leads > 0 AND a.total_clicks > 0
         THEN ROUND((a.total_leads::numeric / a.total_clicks) * 100, 1)
         ELSE 0
    END AS click_to_lead_pct,
    CASE WHEN a.total_leads > 0
         THEN ROUND((a.total_conversions::numeric / a.total_leads) * 100, 1)
         ELSE 0
    END AS conversion_rate,
    (a.total_earned_usd - a.total_paid_usd) AS balance_due
FROM public.affiliates a;

COMMENT ON VIEW public.affiliate_performance IS 'Affiliate performance metrics for dashboards and payouts';

-- ── 6. VERIFY ─────────────────────────────────────────────────────────
-- SELECT * FROM public.affiliate_performance ORDER BY total_earned_usd DESC;
