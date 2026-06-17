-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 048: HEXSTRIKE + ANALYZER PRODUCTS
-- =============================================================================
-- Seeds HexStrike AI (security scanning) and Analyzer Agent (OSINT/recon)
-- into the product catalog with tier pricing, feature descriptions, demo
-- subscriptions, and feature flag columns.
--
-- Tiers:
--   HEXSTRIKE_STARTER    — $99/mo,  100 scans/mo, container + API scans
--   HEXSTRIKE_GROWTH     — $249/mo, 500 scans/mo, all scan types + scheduling
--   HEXSTRIKE_ENTERPRISE — $499/mo, unlimited, custom targets, SLA, priority alerts
--   ANALYZER_LITE        — $49/mo,  100 ops/mo, email + phone recon
--   ANALYZER_GROWTH      — $149/mo, 500 ops/mo, + social + Google intel
--   ANALYZER_ENTERPRISE  — $399/mo, unlimited, deep OSINT + Shodan
--
-- Idempotent: All INSERTs use ON CONFLICT. Safe to re-run.
-- =============================================================================

-- ── 1. HEXSTRIKE PRODUCT METADATA ──────────────────────────────────
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

('HEXSTRIKE_STARTER', 'hexstrike', 'HexStrike AI · Starter',
 'Automated security scanning — 100 scans/month with container security audits and API endpoint probing. Monthly security reports with severity-scored findings.',
 99.00, '$1.50 per additional scan',
 '[{"label": "Security Scans", "value": "100/month"}, {"label": "Container Audit", "value": "Included"}, {"label": "API Probing", "value": "Included"}, {"label": "Severity Scoring", "value": "Critical/High/Medium/Low"}, {"label": "Security Reports", "value": "Monthly"}, {"label": "REST API", "value": "Full access"}]'::jsonb,
 44, true, true),

('HEXSTRIKE_GROWTH', 'hexstrike', 'HexStrike AI · Growth',
 'Full security suite — 500 scans/month with secrets leak detection, pipeline integrity checks, and weekly automated scanning. All scan types enabled.',
 249.00, '$0.75 per additional scan',
 '[{"label": "Security Scans", "value": "500/month"}, {"label": "Container Audit", "value": "Included"}, {"label": "API Probing", "value": "Included"}, {"label": "Secrets Detection", "value": "Included"}, {"label": "Pipeline Checks", "value": "Included"}, {"label": "Weekly Schedule", "value": "Automated"}, {"label": "Severity Scoring", "value": "All levels"}, {"label": "Security Reports", "value": "Weekly + Monthly"}, {"label": "REST API", "value": "Full access"}]'::jsonb,
 45, true, true),

('HEXSTRIKE_ENTERPRISE', 'hexstrike', 'HexStrike AI · Enterprise',
 'Enterprise security — unlimited scans across all scan types with custom infrastructure targets, priority alerting via webhook/SMS/email, SLA-backed uptime, and dedicated support.',
 499.00, 'Unlimited scans',
 '[{"label": "Security Scans", "value": "Unlimited"}, {"label": "All Scan Types", "value": "Full suite"}, {"label": "Custom Targets", "value": "Configurable"}, {"label": "Secrets Detection", "value": "Included"}, {"label": "Pipeline Checks", "value": "Included"}, {"label": "Priority Alerts", "value": "Webhook + SMS + Email"}, {"label": "SLA", "value": "99.9% uptime"}, {"label": "Dedicated Support", "value": "Included"}, {"label": "Custom Integrations", "value": "Available"}]'::jsonb,
 46, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 2. ANALYZER AGENT PRODUCT METADATA ─────────────────────────────
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

('ANALYZER_LITE', 'analyzer', 'Analyzer Agent · Lite',
 'OSINT intelligence — 100 operations/month. Email registration checking on 120+ platforms (Holehe) and phone number validation with carrier info (PhoneInfoga).',
 49.00, '$0.75 per additional operation',
 '[{"label": "Operations", "value": "100/month"}, {"label": "Email Recon", "value": "120+ platforms"}, {"label": "Phone Validation", "value": "Carrier + line type"}, {"label": "REST API", "value": "Full access"}, {"label": "JSON Reports", "value": "Structured output"}]'::jsonb,
 47, true, true),

('ANALYZER_GROWTH', 'analyzer', 'Analyzer Agent · Growth',
 'Advanced intelligence — 500 operations/month. Adds username search across 3,000+ sites (Maigret) and Google account artifact discovery (GHunt). Build complete digital profiles.',
 149.00, '$0.40 per additional operation',
 '[{"label": "Operations", "value": "500/month"}, {"label": "Email Recon", "value": "120+ platforms"}, {"label": "Phone Validation", "value": "Carrier + line type"}, {"label": "Username Search", "value": "3,000+ sites"}, {"label": "Google Intel", "value": "Account discovery"}, {"label": "Monthly Reports", "value": "Digital dossier"}, {"label": "REST API", "value": "Full access"}, {"label": "JSON Reports", "value": "Structured output"}]'::jsonb,
 48, true, true),

('ANALYZER_ENTERPRISE', 'analyzer', 'Analyzer Agent · Enterprise',
 'Enterprise OSINT — unlimited operations with all tools enabled. Deep OSINT scans (SpiderFoot), internet device searching (Shodan), social media profiling (Social Analyzer), and priority support.',
 399.00, 'Unlimited operations',
 '[{"label": "Operations", "value": "Unlimited"}, {"label": "All Tools", "value": "Full suite"}, {"label": "Email Recon", "value": "120+ platforms"}, {"label": "Phone Validation", "value": "Carrier + line type"}, {"label": "Username Search", "value": "3,000+ sites"}, {"label": "Google Intel", "value": "Account discovery"}, {"label": "Shodan Scanning", "value": "Device search"}, {"label": "Deep OSINT", "value": "SpiderFoot scans"}, {"label": "Social Profiling", "value": "1,000+ sites"}, {"label": "Dedicated Support", "value": "Included"}]'::jsonb,
 49, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 3. FEATURE FLAGS ───────────────────────────────────────────────
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS hexstrike_enabled integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS analyzer_enabled integer DEFAULT 0;


-- ── 4. USAGE LOG PRODUCT NAME ──────────────────────────────────────
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
            'contractor_exchange', 'hexstrike', 'analyzer'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 5. TIER LEVEL CHECK CONSTRAINT ─────────────────────────────────
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
            'ANALYZER_LITE', 'ANALYZER_GROWTH', 'ANALYZER_ENTERPRISE'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 6. SEED DEMO SUBSCRIPTIONS — HEXSTRIKE ─────────────────────────
INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_end, notes
) VALUES
    ('demo_hexstrike_starter', 'HEXSTRIKE_STARTER', 'ACTIVE',
     99.00, 1, now() + interval '30 days',
     'Demo account — HexStrike Starter tier (100 scans/mo)'),
    ('demo_hexstrike_growth', 'HEXSTRIKE_GROWTH', 'ACTIVE',
     249.00, 10, now() + interval '30 days',
     'Demo account — HexStrike Growth tier (500 scans/mo)'),
    ('demo_hexstrike_enterprise', 'HEXSTRIKE_ENTERPRISE', 'ACTIVE',
     499.00, 20, now() + interval '30 days',
     'Demo account — HexStrike Enterprise tier (unlimited)')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for hexstrike demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, hexstrike_enabled,
    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled
) VALUES
    ('demo_hexstrike_starter', 1, 0, 0, 0),
    ('demo_hexstrike_growth', 1, 0, 0, 0),
    ('demo_hexstrike_enterprise', 1, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- ── 7. SEED DEMO SUBSCRIPTIONS — ANALYZER ──────────────────────────
INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_end, notes
) VALUES
    ('demo_analyzer_lite', 'ANALYZER_LITE', 'ACTIVE',
     49.00, 1, now() + interval '30 days',
     'Demo account — Analyzer Lite tier (100 ops/mo)'),
    ('demo_analyzer_growth', 'ANALYZER_GROWTH', 'ACTIVE',
     149.00, 10, now() + interval '30 days',
     'Demo account — Analyzer Growth tier (500 ops/mo)'),
    ('demo_analyzer_enterprise', 'ANALYZER_ENTERPRISE', 'ACTIVE',
     399.00, 20, now() + interval '30 days',
     'Demo account — Analyzer Enterprise tier (unlimited)')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for analyzer demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, analyzer_enabled,
    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled
) VALUES
    ('demo_analyzer_lite', 1, 0, 0, 0),
    ('demo_analyzer_growth', 1, 0, 0, 0),
    ('demo_analyzer_enterprise', 1, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- SELECT tier, display_name, monthly_price_usd
-- FROM public.product_metadata
-- WHERE product_name IN ('hexstrike', 'analyzer') AND is_active = true
-- ORDER BY sort_order;
-- =============================================================================
