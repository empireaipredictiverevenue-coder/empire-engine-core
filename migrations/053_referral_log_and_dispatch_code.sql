-- EMPIRE V49 · DDL MIGRATION 053: REFERRAL LOG + DISPATCH CODE
-- ============================================================
-- Adds: 1) referral_log table for tracking all referral events
--        2) referral_code column on dispatches for traceability
--
-- Run: python3 scripts/run_migrations.py migrations/053_referral_log_and_dispatch_code.sql

-- ── 1. REFERRAL_LOG TABLE ──────────────────────────────────────────────
-- Tracks every referral-related event end-to-end: click → signup → dispatch
-- → fee_event → bounty_earned. Provides full audit trail for the bounty
-- pipeline and referrer attribution.
CREATE TABLE IF NOT EXISTS public.referral_log (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              timestamptz NOT NULL DEFAULT now(),
    event_type              text NOT NULL,   -- click | signup | dispatch | fee_event | bounty_earned | payout_requested | payout_paid
    referral_code           text,            -- the unique code that was used
    referrer_contractor_id  uuid REFERENCES public.contractors(id) ON DELETE SET NULL,
    referred_contractor_id  uuid REFERENCES public.contractors(id) ON DELETE SET NULL,
    contractor_referral_id  uuid REFERENCES public.contractor_referrals(id) ON DELETE SET NULL,
    ip_address              text,
    user_agent              text,
    referrer_url            text,
    landing_page            text,
    meta                    jsonb DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.referral_log
    IS 'Full audit trail for the contractor referral bounty pipeline — click through payout';

CREATE INDEX IF NOT EXISTS idx_referral_log_event_type
    ON public.referral_log (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_referral_log_referral_code
    ON public.referral_log (referral_code);

CREATE INDEX IF NOT EXISTS idx_referral_log_referrer
    ON public.referral_log (referrer_contractor_id);

CREATE INDEX IF NOT EXISTS idx_referral_log_referred
    ON public.referral_log (referred_contractor_id);

-- ── 2. ADD REFERRAL_CODE TO DISPATCHES ─────────────────────────────────
ALTER TABLE public.dispatches
    ADD COLUMN IF NOT EXISTS referral_code text;

COMMENT ON COLUMN public.dispatches.referral_code
    IS 'The referral code used by this contractor to sign up (for bounty attribution traceability)';

CREATE INDEX IF NOT EXISTS idx_dispatches_referral_code
    ON public.dispatches (referral_code);

-- ── 3. REFERRAL LOG VIEW FOR ANALYSIS ──────────────────────────────────
CREATE OR REPLACE VIEW public.referral_funnel_view AS
SELECT
    rl.id,
    rl.created_at,
    rl.event_type,
    rl.referral_code,
    -- Referrer info
    rc.name AS referrer_name,
    rc.phone AS referrer_phone,
    rc.metro AS referrer_metro,
    -- Referred info
    rtd.name AS referred_name,
    rtd.phone AS referred_phone,
    rtd.metro AS referred_metro,
    -- Extra context
    rl.meta ->> 'bounty_amount' AS bounty_amount,
    rl.meta ->> 'dispatch_id' AS dispatch_id,
    rl.meta ->> 'fee_event_id' AS fee_event_id,
    rl.meta ->> 'source' AS source
FROM public.referral_log rl
LEFT JOIN public.contractors rc ON rc.id = rl.referrer_contractor_id
LEFT JOIN public.contractors rtd ON rtd.id = rl.referred_contractor_id
ORDER BY rl.created_at DESC;

COMMENT ON VIEW public.referral_funnel_view
    IS 'Enriched referral log with referrer and referred contractor details';

-- ── 4. VERIFICATION ─────────────────────────────────────────────────────
-- SELECT event_type, COUNT(*) FROM referral_log GROUP BY event_type ORDER BY COUNT(*) DESC;
-- SELECT COUNT(*) FROM dispatches WHERE referral_code IS NOT NULL;
