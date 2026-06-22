-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Forecast Feature Flags (migration 056)
--
-- Migration 029 seeded forecast product data but stored forecast-specific flags
-- in the `meta` JSONB column of product_feature_flags instead of dedicated
-- columns. This migration:
--   1. Adds forecast-specific columns to product_feature_flags
--   2. Migrates existing meta JSONB flag values into the new columns
--   3. Ensures product_usage_log CHECK constraint includes all product names
--   4. Ensures product_subscriptions tier_level CHECK includes all tiers
--
-- Dependencies: migration 029 (forecast_product), migration 048 (hexstrike+analyzer)
-- Run: python3 scripts/run_migrations.py
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. ADD FORECAST COLUMNS TO PRODUCT_FEATURE_FLAGS ─────────────────────────
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS forecast_enabled            integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS forecast_max_checks         integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS forecast_narrative_enabled  integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS forecast_what_if_enabled    integer DEFAULT 0;

COMMENT ON COLUMN public.product_feature_flags.forecast_enabled IS 'Forecast product access (1=Active)' ;
COMMENT ON COLUMN public.product_feature_flags.forecast_max_checks IS 'Monthly forecast API check limit (0=unlimited)';
COMMENT ON COLUMN public.product_feature_flags.forecast_narrative_enabled IS 'LLM-generated narrative insights (1=Active)';
COMMENT ON COLUMN public.product_feature_flags.forecast_what_if_enabled IS 'What-if scenario modeling (1=Active)';


-- ── 2. MIGRATE DEMO ACCOUNT FLAGS FROM META JSONB → COLUMNS ───────────────
-- Migration 029 seeded forecast feature flags in the `meta` JSONB column
-- for three demo accounts. Now that we have dedicated columns, migrate
-- those values and clean up the redundant JSONB keys.
-- We use explicit values (known from migration 029's seeding logic) to
-- avoid JSONB type coercion issues (JSON boolean `true` → text 'true'
-- cannot be cast to integer).
UPDATE public.product_feature_flags
SET
    forecast_enabled           = 1,
    forecast_max_checks        = 500,
    forecast_narrative_enabled = 0,
    forecast_what_if_enabled   = 0,
    meta = meta - 'forecast_enabled'
               - 'forecast_max_checks'
               - 'forecast_narrative_enabled'
               - 'forecast_what_if_enabled'
WHERE customer_account_id = 'demo_forecast_lite'
  AND meta ? 'forecast_enabled';

UPDATE public.product_feature_flags
SET
    forecast_enabled           = 1,
    forecast_max_checks        = 2000,
    forecast_narrative_enabled = 1,
    forecast_what_if_enabled   = 0,
    meta = meta - 'forecast_enabled'
               - 'forecast_max_checks'
               - 'forecast_narrative_enabled'
               - 'forecast_what_if_enabled'
WHERE customer_account_id = 'demo_forecast_pro'
  AND meta ? 'forecast_enabled';

UPDATE public.product_feature_flags
SET
    forecast_enabled           = 1,
    forecast_max_checks        = 10000,
    forecast_narrative_enabled = 1,
    forecast_what_if_enabled   = 1,
    meta = meta - 'forecast_enabled'
               - 'forecast_max_checks'
               - 'forecast_narrative_enabled'
               - 'forecast_what_if_enabled'
WHERE customer_account_id = 'demo_forecast_enterprise'
  AND meta ? 'forecast_enabled';


-- ── 3. FIX PRODUCT_USAGE_LOG CHECK CONSTRAINT ────────────────────────────────
-- Migration 048's DO block dropped and re-added the constraint but may have
-- omitted product names added by later migrations. Use safe DO block pattern.
DO $$
BEGIN
    ALTER TABLE public.product_usage_log
        DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

    ALTER TABLE public.product_usage_log
        ADD CONSTRAINT product_usage_log_product_name_check
        CHECK (product_name IN (
            'inbound_router', 'data_vault', 'buyer_spy',
            'omni_bridge', 'agent_orchestrator', 'b2b_pro',
            'seo_optimizer', 'lead_score', 'compliant',
            'strike_campaigns', 'forecast', 'market_eye',
            'content_pulse', 'contractor_exchange', 'hexstrike',
            'analyzer', 'meetily', 'elite_scraper', 'ai_closer'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 4. FIX PRODUCT_SUBSCRIPTIONS TIER_LEVEL CHECK CONSTRAINT ─────────────────
-- Migration 048's DO block omitted MEETILY_*, SCRAPER_*, CLOSER_*, WHITE_LABEL_*
-- tiers that were validly registered. Restore the comprehensive tier list.
DO $$
BEGIN
    ALTER TABLE public.product_subscriptions
        DROP CONSTRAINT IF EXISTS product_subscriptions_tier_level_check;

    ALTER TABLE public.product_subscriptions
        ADD CONSTRAINT product_subscriptions_tier_level_check
        CHECK (tier_level IN (
            'ROUTER_SaaS', 'DATA_ENTERPRISE', 'SPY_DATA', 'ALL_ACCESS',
            'SEO_STARTER', 'SEO_GROWTH', 'SEO_PRO',
            'LEADSCORE_STARTER', 'LEADSCORE_GROWTH', 'LEADSCORE_ENTERPRISE',
            'COMPLIANT_STARTER', 'COMPLIANT_GROWTH', 'COMPLIANT_ENTERPRISE',
            'STRIKE_STARTER', 'STRIKE_GROWTH', 'STRIKE_ENTERPRISE',
            'FORECAST_LITE', 'FORECAST_PRO', 'FORECAST_ENTERPRISE',
            'MARKET_EYE_STARTER', 'MARKET_EYE_GROWTH', 'MARKET_EYE_ENTERPRISE',
            'CONTENT_PULSE_STARTER', 'CONTENT_PULSE_GROWTH', 'CONTENT_PULSE_ENTERPRISE',
            'CONTRACTOR_EXCHANGE_STARTER', 'CONTRACTOR_EXCHANGE_GROWTH', 'CONTRACTOR_EXCHANGE_ENTERPRISE',
            'HEXSTRIKE_STARTER', 'HEXSTRIKE_GROWTH', 'HEXSTRIKE_ENTERPRISE',
            'ANALYZER_LITE', 'ANALYZER_GROWTH', 'ANALYZER_ENTERPRISE',
            'MEETILY_STARTER', 'MEETILY_PRO', 'MEETILY_ENTERPRISE',
            'SCRAPER_STARTER', 'SCRAPER_PRO', 'SCRAPER_ENTERPRISE',
            'CLOSER_STARTER', 'CLOSER_PRO', 'CLOSER_ENTERPRISE', 'EXECUTIVE_WHALE',
            'WHITE_LABEL_STARTER', 'WHITE_LABEL_GROWTH', 'WHITE_LABEL_ENTERPRISE', 'WHITE_LABEL_AGENCY'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- -- Check the new forecast columns exist:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'product_feature_flags'
--   AND column_name LIKE 'forecast_%'
-- ORDER BY column_name;
--
-- -- Check forecast accounts have their flags set correctly:
-- SELECT customer_account_id,
--        forecast_enabled,
--        forecast_max_checks,
--        forecast_narrative_enabled,
--        forecast_what_if_enabled
-- FROM public.product_feature_flags
-- WHERE customer_account_id LIKE 'demo_forecast_%'
-- ORDER BY customer_account_id;
--
-- -- Verify all forecast-customer_account_ids have feature flags:
-- SELECT ps.customer_account_id AS sub_account,
--        pff.customer_account_id AS flags_account,
--        CASE WHEN pff.customer_account_id IS NULL THEN 'MISSING' ELSE 'OK' END AS status
-- FROM public.product_subscriptions ps
-- LEFT JOIN public.product_feature_flags pff
--     ON pff.customer_account_id = ps.customer_account_id
-- WHERE ps.customer_account_id LIKE 'demo_forecast_%';
-- =============================================================================
