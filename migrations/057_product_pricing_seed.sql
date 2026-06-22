-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Product Pricing Seed (migration 057)
--
-- Migration 029 created the product_pricing table and seeded forecast tiers.
-- This migration seeds pricing entries for ALL remaining products that have
-- product_metadata but no product_pricing rows.
--
-- Products seeded: seo_optimizer, inbound_router, data_vault, buyer_spy,
-- all_products, lead_score, compliant, hexstrike, analyzer, market_eye,
-- content_pulse, contractor_exchange, meetily, elite_scraper, ai_closer,
-- white_label
--
-- Uses a JSONB features column for per-product feature toggles instead of
-- per-product boolean columns (avoids the ALTER TABLE treadmill of 030-032).
--
-- Dependencies: migration 029 (creates product_pricing table), migration 020
-- (creates product_metadata catalog)
-- Run: python3 scripts/run_migrations.py
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 0. ADD features JSONB COLUMN FOR EXTENSIBILITY ──────────────────────────
-- Older product migrations (030, 031, 032) assumed per-product boolean columns
-- (brief_enabled, alerts_enabled, etc.) that don't exist in the current table.
-- A single features JSONB column handles all product-specific toggles without
-- requiring ALTER TABLE per product.
ALTER TABLE public.product_pricing
    ADD COLUMN IF NOT EXISTS features jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.product_pricing.features
    IS 'Product-specific feature toggles as JSONB (e.g. {"narrative": true, "alerts": false, "vetting": true})';


-- ── 1. SEO OPTIMIZER ─────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('seo_optimizer', 'SEO_STARTER',   99,   500,  '{}'::jsonb),
    ('seo_optimizer', 'SEO_GROWTH',    199,  2000, '{}'::jsonb),
    ('seo_optimizer', 'SEO_PRO',       499,  0,    '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 2. INBOUND ROUTER ────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('inbound_router', 'ROUTER_SaaS', 499, 0, '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 3. DATA VAULT ────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('data_vault', 'DATA_ENTERPRISE', 799, 0, '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 4. BUYER SPY ─────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('buyer_spy', 'SPY_DATA', 1499, 0, '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 5. ALL ACCESS ────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('all_products', 'ALL_ACCESS', 2499, 0, '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 6. LEAD SCORE AI ─────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('lead_score', 'LEADSCORE_STARTER',    299, 500,  '{}'::jsonb),
    ('lead_score', 'LEADSCORE_GROWTH',     599, 2000, '{}'::jsonb),
    ('lead_score', 'LEADSCORE_ENTERPRISE', 999, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 7. COMPLIANT ─────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('compliant', 'COMPLIANT_STARTER',    199, 500,  '{}'::jsonb),
    ('compliant', 'COMPLIANT_GROWTH',     499, 2000, '{}'::jsonb),
    ('compliant', 'COMPLIANT_ENTERPRISE', 999, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 8. HEXSTRIKE AI ──────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('hexstrike', 'HEXSTRIKE_STARTER',    99,  100,  '{}'::jsonb),
    ('hexstrike', 'HEXSTRIKE_GROWTH',     249, 500,  '{}'::jsonb),
    ('hexstrike', 'HEXSTRIKE_ENTERPRISE', 499, 0,    '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 9. ANALYZER AGENT ─────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('analyzer', 'ANALYZER_LITE',       49,  100, '{}'::jsonb),
    ('analyzer', 'ANALYZER_GROWTH',     149, 500, '{}'::jsonb),
    ('analyzer', 'ANALYZER_ENTERPRISE', 399, 0,   '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 10. MARKET EYE ────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('market_eye', 'MARKET_EYE_STARTER',    199, 500,  '{}'::jsonb),
    ('market_eye', 'MARKET_EYE_GROWTH',     499, 2000, '{}'::jsonb),
    ('market_eye', 'MARKET_EYE_ENTERPRISE', 999, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 11. CONTENT PULSE ────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('content_pulse', 'CONTENT_PULSE_STARTER',    99,  500,  '{}'::jsonb),
    ('content_pulse', 'CONTENT_PULSE_GROWTH',     249, 2000, '{}'::jsonb),
    ('content_pulse', 'CONTENT_PULSE_ENTERPRISE', 499, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 12. STRIKE CAMPAIGNS ──────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('strike_campaigns', 'STRIKE_STARTER',    99,  500,  '{}'::jsonb),
    ('strike_campaigns', 'STRIKE_GROWTH',     249, 2000, '{}'::jsonb),
    ('strike_campaigns', 'STRIKE_ENTERPRISE', 499, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 13. CONTRACTOR EXCHANGE ──────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('contractor_exchange', 'CONTRACTOR_EXCHANGE_STARTER',    299, 500,  '{}'::jsonb),
    ('contractor_exchange', 'CONTRACTOR_EXCHANGE_GROWTH',     599, 2000, '{}'::jsonb),
    ('contractor_exchange', 'CONTRACTOR_EXCHANGE_ENTERPRISE', 999, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 14. MEETILY ──────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('meetily', 'MEETILY_STARTER',   99,  100,  '{}'::jsonb),
    ('meetily', 'MEETILY_PRO',       249, 500,  '{}'::jsonb),
    ('meetily', 'MEETILY_ENTERPRISE',499, 2000, '{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 15. ELITE SCRAPER ────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('elite_scraper', 'SCRAPER_STARTER',    49,  100,  '{}'::jsonb),
    ('elite_scraper', 'SCRAPER_PRO',        149, 1000, '{}'::jsonb),
    ('elite_scraper', 'SCRAPER_ENTERPRISE', 399, 10000,'{}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 16. AI CLOSER ────────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('ai_closer', 'CLOSER_STARTER',    199, 100,  '{}'::jsonb),
    ('ai_closer', 'CLOSER_PRO',        499, 500,  '{}'::jsonb),
    ('ai_closer', 'CLOSER_ENTERPRISE', 999, 2000, '{}'::jsonb),
    ('ai_closer', 'EXECUTIVE_WHALE',   2499,0,    '{"whale_tier": true}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 17. WHITE LABEL ─────────────────────────────────────────────────────────
INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, features)
VALUES
    ('white_label', 'WHITE_LABEL_STARTER',    299, 0, '{"containers": 1, "sub_accounts": 10}'::jsonb),
    ('white_label', 'WHITE_LABEL_GROWTH',     799, 0, '{"containers": 3, "sub_accounts": 50}'::jsonb),
    ('white_label', 'WHITE_LABEL_ENTERPRISE', 1999,0, '{"containers": 10, "sub_accounts": 200}'::jsonb),
    ('white_label', 'WHITE_LABEL_AGENCY',     4999,0, '{"containers": 25, "sub_accounts": 1000}'::jsonb)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- -- All products with their pricing:
-- SELECT pp.product_slug, pp.tier, pp.mrr_usd, pp.checks_per_month, pm.display_name
-- FROM public.product_pricing pp
-- LEFT JOIN public.product_metadata pm ON pm.tier = pp.tier
-- ORDER BY pp.product_slug, pp.tier;
--
-- -- Total MRR from all product_pricing:
-- SELECT SUM(mrr_usd) AS total_mrr FROM public.product_pricing;
--
-- -- Products in metadata but not in pricing:
-- SELECT pm.tier, pm.product_name, pm.monthly_price_usd
-- FROM public.product_metadata pm
-- LEFT JOIN public.product_pricing pp ON pp.tier = pm.tier
-- WHERE pp.tier IS NULL
-- ORDER BY pm.tier;
--
-- -- Products in pricing but not in metadata:
-- SELECT pp.tier, pp.product_slug, pp.mrr_usd
-- FROM public.product_pricing pp
-- LEFT JOIN public.product_metadata pm ON pm.tier = pp.tier
-- WHERE pm.tier IS NULL
-- ORDER BY pp.tier;
-- =============================================================================
