-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Forecast Product (migration 029)
-- Predictive revenue forecasting as a standalone product
-- Tiers: FORECAST_LITE ($199/mo), FORECAST_PRO ($499/mo), FORECAST_ENTERPRISE ($999/mo)
--
-- NOTE: This migration expects migrations 018 and 020 to be applied first.
-- Migration 018 creates: product_subscriptions, product_feature_flags, product_usage_log
-- Migration 020 creates: product_metadata
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 0. Extend CHECK constraints from migration 018 to allow forecast tiers ──
-- Migration 018's product_subscriptions CHECK on tier_level only allows:
--   'ROUTER_SaaS', 'DATA_ENTERPRISE', 'SPY_DATA', 'ALL_ACCESS'
-- We need to add FORECAST_* tiers without dropping/recreating the table.
--
-- Supabase (PostgreSQL) doesn't allow ALTER TABLE ... ALTER CONSTRAINT
-- to change a CHECK constraint's definition. We must DROP and re-add it.
ALTER TABLE IF EXISTS public.product_subscriptions
    DROP CONSTRAINT IF EXISTS product_subscriptions_tier_level_check;

ALTER TABLE IF EXISTS public.product_subscriptions
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

-- Also extend product_usage_log CHECK constraint to allow 'forecast' product_name
ALTER TABLE IF EXISTS public.product_usage_log
    DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

ALTER TABLE IF EXISTS public.product_usage_log
    ADD CONSTRAINT product_usage_log_product_name_check
    CHECK (product_name IN (
        'inbound_router', 'data_vault', 'buyer_spy',
        'omni_bridge', 'agent_orchestrator', 'b2b_pro',
        'seo_optimizer', 'lead_score', 'compliant',
        'strike_campaigns', 'forecast', 'market_eye',
        'content_pulse', 'contractor_exchange', 'hexstrike',
        'analyzer', 'meetily', 'elite_scraper', 'ai_closer'
    ));


-- ── 1. product_metadata ──────────────────────────────────────────────────────
-- Insert forecast product metadata matching schema from migration 020.
-- Columns: tier (PK), product_name, display_name, description,
--          monthly_price_usd, price_per_unit, features (JSONB),
--          sort_order, is_public, is_active
INSERT INTO public.product_metadata AS pm (
    tier, product_name, display_name, description,
    monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active
) VALUES
('FORECAST_LITE', 'forecast', 'Forecast Lite',
 'Predictive revenue projections with per-lane breakdowns and accuracy tracking. Up to 500 checks/month.',
 199.00, NULL,
 '[{"label": "Revenue Forecasts", "value": "500/month"}, {"label": "Per-Lane Breakdown", "value": "Enabled"}, {"label": "Accuracy Tracking", "value": "Enabled"}, {"label": "LLM Narrative", "value": "Disabled"}]'::jsonb,
 200, true, true),

('FORECAST_PRO', 'forecast', 'Forecast Pro',
 'Professional forecasting with AI-generated narrative insights. Up to 2,000 checks/month.',
 499.00, NULL,
 '[{"label": "Revenue Forecasts", "value": "2,000/month"}, {"label": "Per-Lane Breakdown", "value": "Enabled"}, {"label": "Accuracy Tracking", "value": "Enabled"}, {"label": "LLM Narrative", "value": "Enabled"}]'::jsonb,
 210, true, true),

('FORECAST_ENTERPRISE', 'forecast', 'Forecast Enterprise',
 'Enterprise forecasting with what-if scenario modeling. Up to 10,000 checks/month.',
 999.00, NULL,
 '[{"label": "Revenue Forecasts", "value": "10,000/month"}, {"label": "Per-Lane Breakdown", "value": "Enabled"}, {"label": "Accuracy Tracking", "value": "Enabled"}, {"label": "LLM Narrative", "value": "Enabled"}, {"label": "What-If Scenarios", "value": "Enabled"}]'::jsonb,
 220, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 2. product_pricing (NEW TABLE) ───────────────────────────────────────────
-- Per-tier pricing and feature limits for the forecast product.
-- Used by the subscription engine to look up limits by tier.
CREATE TABLE IF NOT EXISTS public.product_pricing (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_slug    text NOT NULL,
    tier            text NOT NULL,
    mrr_usd         numeric(10,2) NOT NULL DEFAULT 0.00,
    checks_per_month integer NOT NULL DEFAULT 0,
    narrative_enabled boolean NOT NULL DEFAULT false,
    what_if_enabled  boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (product_slug, tier)
);

COMMENT ON TABLE  public.product_pricing IS 'Per-tier pricing and feature limits for suite products';
COMMENT ON COLUMN public.product_pricing.product_slug IS 'Product identifier (e.g. forecast, lead_score)';
COMMENT ON COLUMN public.product_pricing.tier IS 'Tier key matching product_metadata.tier';
COMMENT ON COLUMN public.product_pricing.mrr_usd IS 'Monthly recurring revenue in USD';
COMMENT ON COLUMN public.product_pricing.checks_per_month IS 'API check/month limit (0 = unlimited)';
COMMENT ON COLUMN public.product_pricing.narrative_enabled IS 'Whether LLM-generated narrative is available';
COMMENT ON COLUMN public.product_pricing.what_if_enabled IS 'Whether what-if scenario modeling is available';

INSERT INTO public.product_pricing (product_slug, tier, mrr_usd, checks_per_month, narrative_enabled, what_if_enabled)
VALUES
    ('forecast', 'FORECAST_LITE',       199,  500,  false, false),
    ('forecast', 'FORECAST_PRO',        499,  2000, true,  false),
    ('forecast', 'FORECAST_ENTERPRISE', 999,  10000, true,  true)
ON CONFLICT (product_slug, tier) DO NOTHING;


-- ── 3. Seed demo subscriptions into product_subscriptions ──────────────────
-- Matches migration 018 schema: subscription_id (UUID, auto-gen),
-- customer_account_id (text, UNIQUE), tier_level (text, CHECK extended above),
-- subscription_status (text, CHECK), monthly_recurring_revenue (numeric),
-- billing_anchor_day, current_period_start, current_period_end, notes
INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_start, current_period_end, notes
)
SELECT
    'demo_forecast_lite', 'FORECAST_LITE', 'ACTIVE',
    199.00, 1,
    NOW(), NOW() + INTERVAL '30 days',
    'Demo account — Forecast Lite tier'
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_subscriptions WHERE customer_account_id = 'demo_forecast_lite'
);

INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_start, current_period_end, notes
)
SELECT
    'demo_forecast_pro', 'FORECAST_PRO', 'ACTIVE',
    499.00, 1,
    NOW(), NOW() + INTERVAL '30 days',
    'Demo account — Forecast Pro tier (with LLM narrative)'
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_subscriptions WHERE customer_account_id = 'demo_forecast_pro'
);

INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_start, current_period_end, notes
)
SELECT
    'demo_forecast_enterprise', 'FORECAST_ENTERPRISE', 'ACTIVE',
    999.00, 15,
    NOW(), NOW() + INTERVAL '30 days',
    'Demo account — Forecast Enterprise tier (what-if scenarios)'
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_subscriptions WHERE customer_account_id = 'demo_forecast_enterprise'
);


-- ── 4. Demo feature flags ──────────────────────────────────────────────────
-- product_feature_flags schema (migration 018) has core columns like
-- inbound_router_enabled, data_retention_enabled, etc. and a `meta` JSONB
-- column for extended flags. Forecast-specific flags go into `meta`.
INSERT INTO public.product_feature_flags (
    customer_account_id,
    meta,
    created_at, updated_at
)
SELECT
    'demo_forecast_lite',
    '{"forecast_enabled": true, "forecast_max_checks": 500, "forecast_narrative_enabled": false, "forecast_what_if_enabled": false}'::jsonb,
    NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_feature_flags WHERE customer_account_id = 'demo_forecast_lite'
);

INSERT INTO public.product_feature_flags (
    customer_account_id,
    meta,
    created_at, updated_at
)
SELECT
    'demo_forecast_pro',
    '{"forecast_enabled": true, "forecast_max_checks": 2000, "forecast_narrative_enabled": true, "forecast_what_if_enabled": false}'::jsonb,
    NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_feature_flags WHERE customer_account_id = 'demo_forecast_pro'
);

INSERT INTO public.product_feature_flags (
    customer_account_id,
    meta,
    created_at, updated_at
)
SELECT
    'demo_forecast_enterprise',
    '{"forecast_enabled": true, "forecast_max_checks": 10000, "forecast_narrative_enabled": true, "forecast_what_if_enabled": true}'::jsonb,
    NOW(), NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM public.product_feature_flags WHERE customer_account_id = 'demo_forecast_enterprise'
);


-- ── 5. Seed usage log entry ────────────────────────────────────────────────
-- product_usage_log schema (migration 018): customer_account_id, product_name
-- (CHECK extended above), usage_event, quantity, unit, metadata
INSERT INTO public.product_usage_log (
    customer_account_id, product_name, usage_event, quantity, unit, metadata
)
SELECT
    'demo_forecast_lite', 'forecast', 'snapshot_view', 1, 'count',
    '{"note": "seed_demo"}'::jsonb;
