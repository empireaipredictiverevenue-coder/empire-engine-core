-- EMPIRE V49 · DDL MIGRATION 009: AFFILIATE PORTAL
-- ==================================================
-- Creates the affiliate tracking infrastructure:
--   1. affiliate_links — unique referral codes per buyer/partner
--   2. Add affiliate_code to inbound_leads for attribution
--   3. Add affiliate_code to call_logs for payout tracking
--   4. Create affiliate_stats view for dashboard queries
--
-- Run: psql "$SUPABASE_DB_URL" -f migrations/009_affiliate_portal.sql

-- ── 1. AFFILIATE LINKS ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.affiliate_links (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    buyer_id    uuid NOT NULL REFERENCES public.buyers(id) ON DELETE CASCADE,
    code        text NOT NULL UNIQUE,
    label       text NOT NULL DEFAULT '',
    active      boolean NOT NULL DEFAULT true,
    last_click  timestamptz,
    click_count integer NOT NULL DEFAULT 0,
    conversion_count integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS affiliate_links_buyer_idx
    ON public.affiliate_links (buyer_id);
CREATE INDEX IF NOT EXISTS affiliate_links_code_idx
    ON public.affiliate_links (code);

COMMENT ON TABLE  public.affiliate_links IS 'Unique referral codes per buyer for the affiliate tracking portal';
COMMENT ON COLUMN public.affiliate_links.code IS 'Short unique referral code (e.g. apex-roof-2026)';
COMMENT ON COLUMN public.affiliate_links.label IS 'Human-readable label for the link (e.g. \"Apex Roofing — Houston Landing\")';

-- ── 2. INBOUND LEADS AFFILIATE COLUMN ────────────────────────────────
ALTER TABLE public.inbound_leads
    ADD COLUMN IF NOT EXISTS affiliate_code text;

CREATE INDEX IF NOT EXISTS inbound_leads_affiliate_idx
    ON public.inbound_leads (affiliate_code);

COMMENT ON COLUMN public.inbound_leads.affiliate_code IS 'Optional referral code linking this lead to an affiliate link';

-- ── 3. CALL LOGS AFFILIATE COLUMN ────────────────────────────────────
ALTER TABLE public.call_logs
    ADD COLUMN IF NOT EXISTS affiliate_code text;

CREATE INDEX IF NOT EXISTS call_logs_affiliate_idx
    ON public.call_logs (affiliate_code);

COMMENT ON COLUMN public.call_logs.affiliate_code IS 'Referral code for affiliate payout attribution';

-- ── 4. AFFILIATE STATS VIEW (read-only, auto-refreshing) ────────────
CREATE OR REPLACE VIEW public.affiliate_stats AS
SELECT
    l.buyer_id,
    l.code                                                              AS affiliate_code,
    b.buyer_name,
    b.email                                                             AS affiliate_email,
    b.fee_rate,
    b.base_payout,
    b.status                                                            AS buyer_status,
    b.is_active                                                         AS buyer_active,
    COUNT(DISTINCT il.id)                                               AS total_leads,
    COUNT(DISTINCT cl.id)                                               AS total_calls,
    COUNT(DISTINCT cl.id) FILTER (WHERE cl.qualified)                   AS qualified_calls,
    COALESCE(SUM(cl.fee_earned), 0)                                     AS total_revenue,
    COALESCE(SUM(cl.fee_earned * b.fee_rate), 0)                       AS commission_earned,
    COUNT(DISTINCT l.id)                                                AS link_count
FROM public.affiliate_links l
LEFT JOIN public.buyers b              ON b.id = l.buyer_id
LEFT JOIN public.inbound_leads il      ON il.affiliate_code = l.code
LEFT JOIN public.call_logs cl          ON cl.affiliate_code = l.code
GROUP BY l.buyer_id, l.code, b.buyer_name, b.email, b.fee_rate, b.base_payout, b.status, b.is_active;

COMMENT ON VIEW public.affiliate_stats IS 'Aggregate stats per affiliate for the affiliate portal dashboard';

-- ── 5. SEED AFFILIATE LINKS FOR EXISTING ACTIVE BUYERS ───────────────
INSERT INTO public.affiliate_links (buyer_id, code, label)
SELECT
    b.id,
    LOWER(REGEXP_REPLACE(b.buyer_name, '[^a-zA-Z0-9]+', '-', 'g')) || '-' || LOWER(LEFT(b.niche, 12)),
    b.buyer_name || ' — Default Link'
FROM public.buyers b
WHERE b.is_active = true
  AND b.id NOT IN (SELECT buyer_id FROM public.affiliate_links)
ON CONFLICT (code) DO NOTHING;

-- ── 6. VERIFY ─────────────────────────────────────────────────────────
-- SELECT * FROM public.affiliate_stats ORDER BY total_revenue DESC;
