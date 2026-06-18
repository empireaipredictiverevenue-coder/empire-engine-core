-- EMPIRE V49 · DDL MIGRATION 049: CONTRACTOR REFERRAL BOUNTY
-- ===========================================================
-- Adds a $500 referral bounty program: existing contractors refer
-- other contractors. When the referred contractor signs up and
-- closes their first settled claim, the referrer gets paid $500.
--
-- Run: python3 scripts/run_migrations.py
--   or: psql "$SUPABASE_DB_URL" -f migrations/049_contractor_referral_bounty.sql

-- ── 1. ADD REFERRAL_CODE TO CONTRACTORS ─────────────────────────────
ALTER TABLE public.contractors
    ADD COLUMN IF NOT EXISTS referral_code text UNIQUE;

CREATE INDEX IF NOT EXISTS contractors_referral_code_idx
    ON public.contractors (referral_code);

COMMENT ON COLUMN public.contractors.referral_code
    IS 'Unique referral code for the contractor-to-contractor $500 bounty program';

-- ── 2. EXTEND contractor_referrals WITH BOUNTY TRACKING ─────────────
ALTER TABLE public.contractor_referrals
    ADD COLUMN IF NOT EXISTS referral_code       text,
    ADD COLUMN IF NOT EXISTS bounty_amount       numeric NOT NULL DEFAULT 500.00,
    ADD COLUMN IF NOT EXISTS bounty_status       text NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS bounty_paid_at      timestamptz,
    ADD COLUMN IF NOT EXISTS referred_contractor_id uuid REFERENCES public.contractors(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS referred_email      text;

COMMENT ON COLUMN public.contractor_referrals.referral_code
    IS 'The referrer''s unique referral code (for URL-based tracking)';
COMMENT ON COLUMN public.contractor_referrals.bounty_amount
    IS 'Flat $500 bounty paid to referrer when referred contractor closes first deal';
COMMENT ON COLUMN public.contractor_referrals.bounty_status
    IS 'pending | earned | paid | cancelled';
COMMENT ON COLUMN public.contractor_referrals.referred_contractor_id
    IS 'Set when the referred contractor completes self-onboarding';

CREATE INDEX IF NOT EXISTS idx_contractor_referrals_bounty_status
    ON public.contractor_referrals (bounty_status);
CREATE INDEX IF NOT EXISTS idx_contractor_referrals_referral_code
    ON public.contractor_referrals (referral_code);
CREATE INDEX IF NOT EXISTS idx_contractor_referrals_referred_contractor
    ON public.contractor_referrals (referred_contractor_id);

-- ── 3. REFERRAL CODE GENERATION FUNCTION ────────────────────────────
CREATE OR REPLACE FUNCTION public.generate_contractor_referral_code(company_name text)
RETURNS text AS $$
DECLARE
    base text;
    suffix text;
    code text;
BEGIN
    base := LOWER(REGEXP_REPLACE(TRIM(company_name), '[^a-zA-Z0-9 ]+', '', 'g'));
    base := REPLACE(base, ' ', '-');
    base := LEFT(base, 20);
    suffix := UPPER(SUBSTR(MD5(RANDOM()::text), 1, 4));
    code := base || '-' || suffix;
    RETURN code;
END;
$$ LANGUAGE plpgsql;

-- ── 4. CREATE REFERRAL PAYOUTS TABLE ────────────────────────────────
CREATE TABLE IF NOT EXISTS public.referral_payouts (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    contractor_referral_id uuid NOT NULL REFERENCES public.contractor_referrals(id) ON DELETE CASCADE,
    referrer_contractor_id uuid REFERENCES public.contractors(id) ON DELETE SET NULL,
    bounty_amount         numeric NOT NULL DEFAULT 500.00,
    status                text NOT NULL DEFAULT 'earned',    -- earned | paid | cancelled
    paid_at               timestamptz,
    payout_method         text DEFAULT 'usdc',
    payout_tx_id          text,
    notes                 text DEFAULT '',
    meta                  jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_referral_payouts_status
    ON public.referral_payouts (status);
CREATE INDEX IF NOT EXISTS idx_referral_payouts_referrer
    ON public.referral_payouts (referrer_contractor_id);

COMMENT ON TABLE public.referral_payouts
    IS '$500 referral bounties earned by contractors who refer other contractors that close their first deal';
COMMENT ON COLUMN public.referral_payouts.bounty_amount
    IS 'Flat $500 default bounty per referred contractor';

-- ── 5. REFERRAL VIEW FOR DASHBOARD ─────────────────────────────────
CREATE OR REPLACE VIEW public.contractor_referral_view AS
SELECT
    cr.id,
    cr.created_at,
    cr.referrer_contractor_id,
    cr.referrer_phone,
    cr.referred_name,
    cr.referred_phone,
    cr.referred_company,
    cr.referred_metro,
    cr.referral_code,
    cr.bounty_amount,
    cr.bounty_status,
    cr.bounty_paid_at,
    cr.referred_contractor_id,
    cr.referred_email,
    cr.status AS referral_status,
    -- Referrer info
    c.name AS referrer_name,
    c.metro AS referrer_metro,
    -- Payout info
    rp.id AS payout_id,
    rp.status AS payout_status,
    rp.paid_at AS payout_paid_at
FROM public.contractor_referrals cr
LEFT JOIN public.contractors c ON c.id = cr.referrer_contractor_id
LEFT JOIN public.referral_payouts rp ON rp.contractor_referral_id = cr.id;

COMMENT ON VIEW public.contractor_referral_view
    IS 'Contractor referral dashboard data with referrer info and payout status';

-- ── 6. BACKFILL: GENERATE REFERRAL CODES FOR EXISTING CONTRACTORS ──
UPDATE public.contractors
SET referral_code = public.generate_contractor_referral_code(name)
WHERE referral_code IS NULL;

-- ── 7. VERIFY ─────────────────────────────────────────────────────────
-- SELECT * FROM public.contractor_referral_view ORDER BY created_at DESC;
