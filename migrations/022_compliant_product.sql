-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 022: COMPLIANT PRODUCT
-- =============================================================================
-- Adds Compliant (compliance-as-a-service) to the product catalog. Compliant
-- wraps the existing deterministic compliance rules engine (compliance.py) and
-- the outreach compliance gate (agents/outreach/compliance.py) into a
-- productized API service for TCPA/DNC/opt-out checking.
--
-- Tiers:
--   COMPLIANT_STARTER   — $199/mo, 500 checks/mo, basic TCPA/DNC/opt-out
--   COMPLIANT_GROWTH    — $499/mo, 2,000 checks/mo, full suite + quiet hours
--   COMPLIANT_ENTERPRISE — $999/mo, 10,000 checks/mo, audit logging + custom rules
--
-- Changes:
--   1. Adds COMPLIANT_STARTER/GROWTH/ENTERPRISE to product_metadata
--   2. Adds compliant_enabled + compliant_max_checks to product_feature_flags
--   3. Adds 'compliant' to product_usage_log product_name check constraint
--   4. Updates product_subscriptions tier_level CHECK constraint
--   5. Seeds demo account subscriptions + feature flags
--
-- Idempotent: All INSERTs use ON CONFLICT. Safe to re-run.
-- =============================================================================


-- ── 1. PRODUCT METADATA ────────────────────────────────────────────
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

('COMPLIANT_STARTER', 'compliant', 'Compliant · Starter',
 'TCPA/DNC compliance engine — 500 checks/month with deterministic rule checking: opt-out registry, DNC list, and consent validation',
 199.00, '$0.50 per additional check',
 '[{"label": "Compliance Checks", "value": "500/month"}, {"label": "Opt-Out Registry", "value": "Included"}, {"label": "DNC List Check", "value": "Included"}, {"label": "Consent Validation", "value": "Included"}, {"label": "API Access", "value": "REST Endpoint"}, {"label": "Rule Engine", "value": "Deterministic"}]'::jsonb,
 38, true, true),

('COMPLIANT_GROWTH', 'compliant', 'Compliant · Growth',
 'Full compliance suite — 2,000 checks/month with quiet hours enforcement, rate limiting, audit logging, and per-lead TCPA consent tracking',
 499.00, '$0.30 per additional check',
 '[{"label": "Compliance Checks", "value": "2,000/month"}, {"label": "Opt-Out Registry", "value": "Included"}, {"label": "DNC List Check", "value": "Included"}, {"label": "Consent Validation", "value": "Per-lead TCPA"}, {"label": "Quiet Hours Enforced", "value": "Timezone-aware"}, {"label": "Rate Limiting", "value": "Per-number per-day"}, {"label": "Audit Logging", "value": "Full trail"}, {"label": "API Access", "value": "Full REST + Batch"}, {"label": "Call Window Check", "value": "8am-9pm local"}]'::jsonb,
 39, true, true),

('COMPLIANT_ENTERPRISE', 'compliant', 'Compliant · Enterprise',
 'Enterprise compliance — 10,000 checks/month with custom rules, bulk batch checking, SI strategy integration, dedicated audit pipeline, and SLA-backed uptime',
 999.00, '$0.20 per additional check',
 '[{"label": "Compliance Checks", "value": "10,000/month"}, {"label": "Full Suite", "value": "All checks included"}, {"label": "Custom Rules", "value": "Configurable"}, {"label": "Batch Checking", "value": "Bulk API"}, {"label": "SI Strategy Integration", "value": "Enabled"}, {"label": "Dedicated Audit Pipeline", "value": "Included"}, {"label": "Compliance Dashboard", "value": "Real-time"}, {"label": "SLA", "value": "99.9% uptime"}]'::jsonb,
 40, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 2. FEATURE FLAGS ───────────────────────────────────────────────
-- Add compliant_enabled + compliant_max_checks columns to the existing
-- product_feature_flags table.
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS compliant_enabled integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS compliant_max_checks integer DEFAULT 0;


-- ── 3. USAGE LOG PRODUCT NAME ──────────────────────────────────────
-- Need to alter the CHECK constraint on product_usage_log to include
-- 'compliant' as a valid product_name.
DO $$
BEGIN
    ALTER TABLE public.product_usage_log
        DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

    ALTER TABLE public.product_usage_log
        ADD CONSTRAINT product_usage_log_product_name_check
        CHECK (product_name IN (
            'inbound_router', 'data_vault', 'buyer_spy',
            'omni_bridge', 'agent_orchestrator', 'b2b_pro',
            'lead_score', 'compliant'
        ));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;


-- ── 4. UPDATE CHECK CONSTRAINT ─────────────────────────────────────
-- Update product_subscriptions.tier_level CHECK constraint to include
-- the new Compliant tiers.
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
            'COMPLIANT_STARTER', 'COMPLIANT_GROWTH', 'COMPLIANT_ENTERPRISE'
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
    ('demo_compliant_starter', 'COMPLIANT_STARTER', 'ACTIVE',
     199.00, 1,
     now() + interval '30 days',
     'Demo account — Compliant Starter tier (500 checks/mo)'),
    ('demo_compliant_growth', 'COMPLIANT_GROWTH', 'ACTIVE',
     499.00, 10,
     now() + interval '30 days',
     'Demo account — Compliant Growth tier (2,000 checks/mo)'),
    ('demo_compliant_enterprise', 'COMPLIANT_ENTERPRISE', 'ACTIVE',
     999.00, 20,
     now() + interval '30 days',
     'Demo account — Compliant Enterprise tier (10,000 checks/mo)')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, compliant_enabled, compliant_max_checks,
    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled
) VALUES
    ('demo_compliant_starter', 1, 500, 0, 0, 0),
    ('demo_compliant_growth', 1, 2000, 0, 0, 0),
    ('demo_compliant_enterprise', 1, 10000, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- SELECT tier, display_name, monthly_price_usd
-- FROM public.product_metadata
-- WHERE product_name = 'compliant' AND is_active = true
-- ORDER BY sort_order;
-- =============================================================================
