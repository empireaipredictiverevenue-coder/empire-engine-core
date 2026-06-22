-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION: SOVEREIGN AGI MATRIX PRODUCT
-- =============================================================================
-- Seeds the Sovereign AGI Matrix into the product catalog with 3 tiers.
-- The Sovereign AGI Matrix exposes 5 v7.0.0 API endpoints for fleet
-- intelligence, self-awareness, and autonomous decision-making.
--
-- Endpoints:
--   POST /api/v6/matrix/strategy-decide  — AGI Governor strategy decisions
--   POST /api/v6/matrix/self-aware       — Full-system introspection snapshot
--   POST /api/v6/matrix/niche-analyze    — Bayesian niche analysis + win-rate
--   POST /api/v6/matrix/regime-detect    — KL divergence market regime detection
--   POST /api/v6/matrix/agi-optimize     — LLM parameter/weight optimization
--
-- Tiers:
--   SOVEREIGN_STARTER    — $199/mo,  500 API calls/mo, strategy-decide + self-aware
--   SOVEREIGN_GROWTH     — $499/mo,  2,500 calls/mo, all 5 endpoints + historical analytics
--   SOVEREIGN_ENTERPRISE — $999/mo,  unlimited, custom AGI training + dedicated support
--
-- Idempotent: All INSERTs use ON CONFLICT. Safe to re-run.
-- =============================================================================

-- ── 1. SOVEREIGN AGI MATRIX PRODUCT METADATA ───────────────────────
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

('SOVEREIGN_STARTER', 'sovereign_agi_matrix', 'Sovereign AGI Matrix · Starter',
 'Fleet intelligence API — 500 calls/month. Access strategy-decide (AGI Governor with self-awareness anomaly gate) and self-aware (full-system introspection snapshot: agent health, lane performance, revenue state, PM2 service health). Powered by local Ollama inference.',
 199.00, '$0.50 per additional API call',
 '[{"label": "API Calls", "value": "500/month"}, {"label": "Strategy-Decide", "value": "AGI Governor + anomaly gate"}, {"label": "Self-Aware", "value": "Full-system snapshot"}, {"label": "Inference Engine", "value": "Ollama (local)"}, {"label": "REST API", "value": "Full access"}, {"label": "JSON Reports", "value": "Structured output"}]'::jsonb,
 190, true, true),

('SOVEREIGN_GROWTH', 'sovereign_agi_matrix', 'Sovereign AGI Matrix · Growth',
 'Full fleet intelligence suite — 2,500 calls/month across all 5 endpoints: strategy-decide, self-aware, niche-analyze (Bayesian win-rate prediction), regime-detect (KL divergence market shift detection), and agi-optimize (LLM parameter tuning). Includes 90-day historical analytics.',
 499.00, '$0.25 per additional API call',
 '[{"label": "API Calls", "value": "2,500/month"}, {"label": "All 5 Endpoints", "value": "Full suite"}, {"label": "Strategy-Decide", "value": "AGI Governor + self-awareness"}, {"label": "Self-Aware", "value": "Full-system snapshot"}, {"label": "Niche-Analyze", "value": "Bayesian + win-rate"}, {"label": "Regime-Detect", "value": "KL divergence detection"}, {"label": "AGI-Optimize", "value": "LLM weight tuning"}, {"label": "Historical Analytics", "value": "90-day retention"}, {"label": "REST API", "value": "Full access"}]'::jsonb,
 191, true, true),

('SOVEREIGN_ENTERPRISE', 'sovereign_agi_matrix', 'Sovereign AGI Matrix · Enterprise',
 'Enterprise fleet intelligence — unlimited API calls across all 5 endpoints with custom AGI Governor training (per-niche strategy calibration), white-label API branding, SLA-backed 99.9% uptime, and dedicated support. Full historical analytics with no retention limits.',
 999.00, 'Unlimited API calls',
 '[{"label": "API Calls", "value": "Unlimited"}, {"label": "All 5 Endpoints", "value": "Full suite"}, {"label": "Strategy-Decide", "value": "AGI Governor + anomaly gate"}, {"label": "Self-Aware", "value": "Full-system snapshot"}, {"label": "Niche-Analyze", "value": "Bayesian + win-rate"}, {"label": "Regime-Detect", "value": "KL divergence detection"}, {"label": "AGI-Optimize", "value": "LLM weight tuning"}, {"label": "Custom AGI Training", "value": "Per-niche calibration"}, {"label": "White-Label API", "value": "Custom domain + branding"}, {"label": "SLA", "value": "99.9% uptime"}, {"label": "Dedicated Support", "value": "Included"}, {"label": "Historical Analytics", "value": "Unlimited retention"}]'::jsonb,
 192, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 2. FEATURE FLAGS ───────────────────────────────────────────────
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS sovereign_agi_matrix_enabled integer DEFAULT 0;


-- ── 3. USAGE LOG PRODUCT NAME CONSTRAINT ───────────────────────────
DO $$
BEGIN
    ALTER TABLE public.product_usage_log
        DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

    ALTER TABLE public.product_usage_log
        ADD CONSTRAINT product_usage_log_product_name_check
        CHECK (product_name IN (
            'inbound_router', 'data_vault', 'buyer_spy',
            'omni_bridge', 'agent_orchestrator', 'b2b_pro',
            'lead_score', 'compliant', 'strike_campaigns',
            'forecast', 'market_eye', 'content_pulse',
            'contractor_exchange', 'hexstrike', 'analyzer',
            'seo_optimizer', 'meetily', 'elite_scraper',
            'sovereign_agi_matrix'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 4. TIER LEVEL CHECK CONSTRAINT ─────────────────────────────────
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
            'SOVEREIGN_STARTER', 'SOVEREIGN_GROWTH', 'SOVEREIGN_ENTERPRISE'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 5. SEED DEMO SUBSCRIPTIONS ─────────────────────────────────────
INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_end, notes
) VALUES
    ('demo_sovereign_starter', 'SOVEREIGN_STARTER', 'ACTIVE',
     199.00, 1, now() + interval '30 days',
     'Demo account — Sovereign AGI Matrix Starter (500 calls/mo, strategy-decide + self-aware)'),
    ('demo_sovereign_growth', 'SOVEREIGN_GROWTH', 'ACTIVE',
     499.00, 10, now() + interval '30 days',
     'Demo account — Sovereign AGI Matrix Growth (2,500 calls/mo, all 5 endpoints)'),
    ('demo_sovereign_enterprise', 'SOVEREIGN_ENTERPRISE', 'ACTIVE',
     999.00, 20, now() + interval '30 days',
     'Demo account — Sovereign AGI Matrix Enterprise (unlimited, custom AGI training)')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for sovereign demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, sovereign_agi_matrix_enabled,
    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled
) VALUES
    ('demo_sovereign_starter', 1, 0, 0, 0),
    ('demo_sovereign_growth', 1, 0, 0, 0),
    ('demo_sovereign_enterprise', 1, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- SELECT tier, display_name, monthly_price_usd
-- FROM public.product_metadata
-- WHERE product_name = 'sovereign_agi_matrix' AND is_active = true
-- ORDER BY sort_order;
-- =============================================================================
