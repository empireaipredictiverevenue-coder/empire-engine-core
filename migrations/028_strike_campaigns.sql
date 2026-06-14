-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 028: STRIKE CAMPAIGNS PRODUCT
-- =============================================================================
-- Adds Strike Campaigns (multi-touch SMS/email sequence builder) to the
-- product catalog. Strike Campaigns wraps the existing SMSSequenceEngine
-- and EmailSequenceEngine into a unified campaign builder with tier-based
-- rate limits, A/B testing, and analytics.
--
-- Tiers:
--   STRIKE_STARTER   — $99/mo, 500 campaign runs/mo, basic SMS + email sequences
--   STRIKE_GROWTH    — $249/mo, 2,000 runs/mo, multi-channel sequencing, analytics
--   STRIKE_ENTERPRISE — $499/mo, 10,000 runs/mo, A/B testing, custom templates, SLA
--
-- Changes:
--   1. Adds STRIKE_STARTER/GROWTH/ENTERPRISE to product_metadata
--   2. Adds strike_campaigns_enabled + strike_campaigns_max_runs to product_feature_flags
--   3. Adds 'strike_campaigns' to product_usage_log product_name check constraint
--   4. Updates product_subscriptions tier_level CHECK constraint
--   5. Seeds demo account subscriptions + feature flags
--
-- Idempotent: All INSERTs use ON CONFLICT. Safe to re-run.
-- =============================================================================


-- ── 1. PRODUCT METADATA ────────────────────────────────────────────
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

('STRIKE_STARTER', 'strike_campaigns', 'Strike Campaigns · Starter',
 'Multi-touch SMS & email campaign builder — 500 campaign runs/month with 5-touch SMS sequences and 4-touch email sequences. TCPA/CAN-SPAM compliant out of the box.',
 99.00, '$0.10 per additional run',
 '[{"label": "Campaign Runs", "value": "500/month"}, {"label": "SMS Sequences", "value": "5-touch"}, {"label": "Email Sequences", "value": "4-touch"}, {"label": "Compliance", "value": "TCPA + CAN-SPAM"}, {"label": "API Access", "value": "REST Endpoint"}, {"label": "Campaign Templates", "value": "Storm Strike"}, {"label": "Quiet Hours", "value": "Auto-enforced"}]'::jsonb,
 41, true, true),

('STRIKE_GROWTH', 'strike_campaigns', 'Strike Campaigns · Growth',
 'Growth-tier campaign builder — 2,000 campaign runs/month with multi-channel sequencing (SMS + email combined), campaign analytics, reply tracking, and custom schedules.',
 249.00, '$0.08 per additional run',
 '[{"label": "Campaign Runs", "value": "2,000/month"}, {"label": "SMS Sequences", "value": "5-touch"}, {"label": "Email Sequences", "value": "4-touch"}, {"label": "Multi-Channel", "value": "SMS + Email"}, {"label": "Campaign Analytics", "value": "Per-sequence"}, {"label": "Reply Tracking", "value": "Real-time"}, {"label": "Custom Schedules", "value": "Configurable"}, {"label": "Compliance", "value": "TCPA + CAN-SPAM"}, {"label": "Bulk Enroll", "value": "API endpoint"}]'::jsonb,
 42, true, true),

('STRIKE_ENTERPRISE', 'strike_campaigns', 'Strike Campaigns · Enterprise',
 'Enterprise campaign builder — 10,000 campaign runs/month with A/B testing, custom message templates, SI strategy genome integration, dedicated compliance audit pipeline, and SLA-backed uptime.',
 499.00, '$0.05 per additional run',
 '[{"label": "Campaign Runs", "value": "10,000/month"}, {"label": "SMS Sequences", "value": "Custom"}, {"label": "Email Sequences", "value": "Custom"}, {"label": "Multi-Channel", "value": "SMS + Email"}, {"label": "Campaign Analytics", "value": "Full dashboard"}, {"label": "Reply Tracking", "value": "Real-time"}, {"label": "A/B Testing", "value": "Enabled"}, {"label": "Custom Templates", "value": "Full editor"}, {"label": "SI Strategy Integration", "value": "Enabled"}, {"label": "Compliance Audit", "value": "Dedicated pipeline"}, {"label": "Bulk Enroll", "value": "Unlimited"}, {"label": "SLA", "value": "99.9% uptime"}]'::jsonb,
 43, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 2. FEATURE FLAGS ───────────────────────────────────────────────
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS strike_campaigns_enabled integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS strike_campaigns_max_runs integer DEFAULT 0;


-- ── 3. USAGE LOG PRODUCT NAME ──────────────────────────────────────
DO $$
BEGIN
    ALTER TABLE public.product_usage_log
        DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

    ALTER TABLE public.product_usage_log
        ADD CONSTRAINT product_usage_log_product_name_check
        CHECK (product_name IN (
            'inbound_router', 'data_vault', 'buyer_spy',
            'omni_bridge', 'agent_orchestrator', 'b2b_pro',
            'lead_score', 'compliant', 'strike_campaigns'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 4. UPDATE CHECK CONSTRAINT ─────────────────────────────────────
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
            'STRIKE_STARTER', 'STRIKE_GROWTH', 'STRIKE_ENTERPRISE'
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
    ('demo_strike_starter', 'STRIKE_STARTER', 'ACTIVE',
     99.00, 1,
     now() + interval '30 days',
     'Demo account — Strike Campaigns Starter tier (500 runs/mo)'),
    ('demo_strike_growth', 'STRIKE_GROWTH', 'ACTIVE',
     249.00, 10,
     now() + interval '30 days',
     'Demo account — Strike Campaigns Growth tier (2,000 runs/mo)'),
    ('demo_strike_enterprise', 'STRIKE_ENTERPRISE', 'ACTIVE',
     499.00, 20,
     now() + interval '30 days',
     'Demo account — Strike Campaigns Enterprise tier (10,000 runs/mo)')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, strike_campaigns_enabled, strike_campaigns_max_runs,
    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled
) VALUES
    ('demo_strike_starter', 1, 500, 0, 0, 0),
    ('demo_strike_growth', 1, 2000, 0, 0, 0),
    ('demo_strike_enterprise', 1, 10000, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- SELECT tier, display_name, monthly_price_usd
-- FROM public.product_metadata
-- WHERE product_name = 'strike_campaigns' AND is_active = true
-- ORDER BY sort_order;
-- =============================================================================
