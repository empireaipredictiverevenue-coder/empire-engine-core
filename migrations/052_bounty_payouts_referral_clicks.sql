-- EMPIRE V49 · DDL MIGRATION 052: BOUNTY PAYOUTS + REFERRAL CLICKS
-- ================================================================
-- Two new tables for the contractor referral bounty program:
--
--   1. bounty_payouts     — Payout-request-level table. When a contractor
--                           clicks "Request Payout" in the portal, one row
--                           is created bundling N referral_payouts. Tracks
--                           approval, processing, and on-chain tx status.
--
--   2. referral_clicks    — Click-level attribution. Every /ref/contractor/{code}
--                           hit logs a row so we can measure the conversion
--                           funnel: clicks → signups → first deal → bounty earned.
--
--   Also adds bounty_payout_id FK to referral_payouts for traceability.
--
-- Run: python3 scripts/run_migrations.py
--   or: psql "$SUPABASE_DB_URL" -f migrations/052_bounty_payouts_referral_clicks.sql


-- ── 1. BOUNTY PAYOUTS TABLE ─────────────────────────────────────────
-- A single payout request bundling multiple earned referral bounties.
-- Created when a contractor clicks "Request Payout" in the portal.
CREATE TABLE IF NOT EXISTS public.bounty_payouts (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    contractor_id         uuid NOT NULL REFERENCES public.contractors(id) ON DELETE CASCADE,
    status                text NOT NULL DEFAULT 'requested'
                          CHECK (status IN ('requested', 'approved', 'paid', 'cancelled', 'failed')),
    total_amount          numeric(12,2) NOT NULL DEFAULT 0,
    bounty_count          int NOT NULL DEFAULT 0,
    payout_method         text NOT NULL DEFAULT 'usdc_solana',
    payout_address        text,
    notes                 text,
    approved_by           text,
    approved_at           timestamptz,
    paid_at               timestamptz,
    paid_tx_sig           text,
    meta                  jsonb DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.bounty_payouts
    IS 'Grouped payout requests bundling multiple earned referral bounties. One request per contractor action.';

CREATE INDEX IF NOT EXISTS idx_bounty_payouts_contractor
    ON public.bounty_payouts (contractor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bounty_payouts_status
    ON public.bounty_payouts (status, created_at DESC);


-- ── 2. LINK referral_payouts → bounty_payouts ───────────────────────
ALTER TABLE public.referral_payouts
    ADD COLUMN IF NOT EXISTS bounty_payout_id uuid REFERENCES public.bounty_payouts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_referral_payouts_bounty_payout
    ON public.referral_payouts (bounty_payout_id);

COMMENT ON COLUMN public.referral_payouts.bounty_payout_id
    IS 'Links this individual bounty payout to the parent grouped payout request';


-- ── 3. REFERRAL CLICKS TABLE ────────────────────────────────────────
-- Every hit to /ref/contractor/{code} logs a row for funnel analysis.
-- The converted_to_signup + converted_contractor_id fields are updated
-- when the clicking user completes self-onboarding.
CREATE TABLE IF NOT EXISTS public.referral_clicks (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              timestamptz NOT NULL DEFAULT now(),
    referral_code           text NOT NULL,
    referrer_contractor_id  uuid REFERENCES public.contractors(id) ON DELETE SET NULL,
    ip_address              text,
    user_agent              text,
    referrer_url            text,
    landing_page            text,
    converted_to_signup     boolean NOT NULL DEFAULT false,
    converted_at            timestamptz,
    converted_contractor_id uuid REFERENCES public.contractors(id) ON DELETE SET NULL,
    meta                    jsonb DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.referral_clicks
    IS 'Referral link click tracking for funnel analysis (clicks → signups → first deal → bounty)';

CREATE INDEX IF NOT EXISTS idx_referral_clicks_code
    ON public.referral_clicks (referral_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_clicks_referrer
    ON public.referral_clicks (referrer_contractor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_referral_clicks_converted
    ON public.referral_clicks (converted_to_signup)
    WHERE converted_to_signup = true;


-- ── 4. REFERRAL CLICK FUNNEL VIEW ───────────────────────────────────
-- Aggregates clicks per referral code with signup conversion stats.
-- Useful for the operator dashboard and leaderboard enrichment.
CREATE OR REPLACE VIEW public.referral_click_funnel AS
SELECT
    rc.referral_code,
    rc.referrer_contractor_id,
    c.name AS referrer_name,
    c.metro AS referrer_metro,
    COUNT(rc.id) AS total_clicks,
    COUNT(rc.id) FILTER (WHERE rc.converted_to_signup) AS signups,
    CASE
        WHEN COUNT(rc.id) > 0
        THEN ROUND(100.0 * COUNT(rc.id) FILTER (WHERE rc.converted_to_signup) / COUNT(rc.id), 2)
        ELSE 0
    END AS conversion_pct,
    MIN(rc.created_at) AS first_click_at,
    MAX(rc.created_at) AS latest_click_at
FROM public.referral_clicks rc
LEFT JOIN public.contractors c ON c.id = rc.referrer_contractor_id
GROUP BY rc.referral_code, rc.referrer_contractor_id, c.name, c.metro;

COMMENT ON VIEW public.referral_click_funnel
    IS 'Aggregated referral click-to-signup funnel per referral code';


-- ── 5. BOUNTY PAYOUT SUMMARY VIEW ───────────────────────────────────
-- Enriches bounty_payouts with referrer name and linked bounty details.
CREATE OR REPLACE VIEW public.bounty_payout_summary AS
SELECT
    bp.id,
    bp.created_at,
    bp.updated_at,
    bp.contractor_id,
    c.name AS contractor_name,
    c.email AS contractor_email,
    c.solana_wallet AS contractor_wallet,
    bp.status,
    bp.total_amount,
    bp.bounty_count,
    bp.payout_method,
    bp.payout_address,
    bp.approved_by,
    bp.approved_at,
    bp.paid_at,
    bp.paid_tx_sig,
    bp.notes,
    bp.meta,
    -- Linked referral_payouts stats
    COUNT(rp.id) FILTER (WHERE rp.status = 'paid') AS paid_bounty_count,
    SUM(rp.bounty_amount) FILTER (WHERE rp.status = 'paid') AS paid_bounty_total
FROM public.bounty_payouts bp
LEFT JOIN public.contractors c ON c.id = bp.contractor_id
LEFT JOIN public.referral_payouts rp ON rp.bounty_payout_id = bp.id
GROUP BY bp.id, bp.created_at, bp.updated_at, bp.contractor_id, c.name, c.email,
         c.solana_wallet, bp.status, bp.total_amount, bp.bounty_count, bp.payout_method,
         bp.payout_address, bp.approved_by, bp.approved_at, bp.paid_at, bp.paid_tx_sig,
         bp.notes, bp.meta;

COMMENT ON VIEW public.bounty_payout_summary
    IS 'Enriched bounty payout requests with contractor info and linked payout status';


-- ── 6. VERIFICATION ────────────────────────────────────────────────
-- Run these to verify the migration was applied:
--   SELECT count(*) FROM information_schema.tables
--     WHERE table_schema = 'public' AND table_name IN ('bounty_payouts', 'referral_clicks');
--   SELECT count(*) FROM information_schema.views
--     WHERE table_schema = 'public' AND view_name IN ('referral_click_funnel', 'bounty_payout_summary');
