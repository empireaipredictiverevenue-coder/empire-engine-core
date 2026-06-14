-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 021: LEADSCORE AI PRODUCT
-- =============================================================================
-- Adds the LeadScore AI product to the product catalog. LeadScore AI is a
-- standalone lead enrichment & scoring engine that wraps the existing SI-powered
-- lead enricher agent into a productized API service.
--
-- Tiers:
--   LEADSCORE_STARTER  — $299/mo, 500 scored leads/mo, basic enrichment
--   LEADSCORE_GROWTH   — $599/mo, 2,000 scored leads/mo, custom thresholds + API
--   LEADSCORE_ENTERPRISE — $999/mo, 10,000 scored leads/mo, custom models + SI genome
--
-- Changes:
--   1. Adds LEADSCORE_STARTER/GROWTH/ENTERPRISE to product_metadata
--   2. Adds leadscore_enabled + leadscore_max_scored_leads to product_feature_flags
--   3. Adds 'lead_score' to product_usage_log product_name check constraint
--   4. Seeds demo account subscriptions
--
-- Idempotent: All INSERTs use ON CONFLICT. Safe to re-run.
-- =============================================================================


-- ── 1. PRODUCT METADATA ────────────────────────────────────────────
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

('LEADSCORE_STARTER', 'lead_score', 'LeadScore AI · Starter',
 'Bayesian lead scoring engine — 500 scored leads/month with SI-powered probability calibration and basic enrichment',
 299.00, '$0.50 per additional scored lead',
 '[{"label": "Scored Leads", "value": "500/month"}, {"label": "Enrichment Fields", "value": "Basic (5 fields)"}, {"label": "Scoring Method", "value": "Bayesian Probability"}, {"label": "API Access", "value": "REST Endpoint"}, {"label": "Historical Calibration", "value": "30-day rolling"}]'::jsonb,
 35, true, true),

('LEADSCORE_GROWTH', 'lead_score', 'LeadScore AI · Growth',
 'Growth-tier lead scoring — 2,000 scored leads/month with custom threshold config, priority ranking, and full API access',
 599.00, '$0.30 per additional scored lead',
 '[{"label": "Scored Leads", "value": "2,000/month"}, {"label": "Enrichment Fields", "value": "Full (10+ fields)"}, {"label": "Scoring Method", "value": "Bayesian + SI Core"}, {"label": "API Access", "value": "Full REST + Batch"}, {"label": "Custom Thresholds", "value": "Configurable"}, {"label": "Priority Ranking", "value": "Auto-sorted"}, {"label": "Historical Calibration", "value": "90-day rolling"}]'::jsonb,
 36, true, true),

('LEADSCORE_ENTERPRISE', 'lead_score', 'LeadScore AI · Enterprise',
 'Enterprise lead scoring — 10,000 scored leads/month with custom models, SI genome integration, dedicated pipeline, and SLA-backed uptime',
 999.00, '$0.20 per additional scored lead',
 '[{"label": "Scored Leads", "value": "10,000/month"}, {"label": "Enrichment Fields", "value": "Custom pipeline"}, {"label": "Scoring Method", "value": "Custom SI Model"}, {"label": "SI Genome Integration", "value": "Enabled"}, {"label": "API Access", "value": "Full REST + Batch + Webhook"}, {"label": "Custom Thresholds", "value": "Per-niche"}, {"label": "Dedicated Pipeline", "value": "Included"}, {"label": "SLA", "value": "99.9% uptime"}]'::jsonb,
 37, true, true)

ON CONFLICT (tier) DO NOTHING;


-- ── 2. FEATURE FLAGS ───────────────────────────────────────────────
-- Add leadscore_enabled + leadscore_max_scored_leads columns to the
-- existing product_feature_flags table.
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS leadscore_enabled integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS leadscore_max_scored_leads integer DEFAULT 0;


-- ── 3. USAGE LOG PRODUCT NAME ──────────────────────────────────────
-- Need to alter the CHECK constraint on product_usage_log to include
-- 'lead_score' as a valid product_name. Since Supabase doesn't support
-- ALTER CONSTRAINT directly, we drop and recreate.
-- (This is safe to re-run due to IF NOT EXISTS patterns.)
DO $$
BEGIN
    -- Drop the old constraint if it exists
    ALTER TABLE public.product_usage_log
        DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

    -- Recreate with 'lead_score' added
    ALTER TABLE public.product_usage_log
        ADD CONSTRAINT product_usage_log_product_name_check
        CHECK (product_name IN (
            'inbound_router', 'data_vault', 'buyer_spy',
            'omni_bridge', 'agent_orchestrator', 'b2b_pro',
            'lead_score'
        ));
EXCEPTION WHEN OTHERS THEN
    -- If the constraint doesn't exist yet, that's fine
    NULL;
END $$;


-- ── 4. UPDATE CHECK CONSTRAINT ─────────────────────────────────────
-- The existing check constraint on product_subscriptions.tier_level only
-- allows the original 4 tiers. We need to add the new LeadScore tiers.
-- Use the same DO block pattern as the usage_log constraint update above.
DO $$
BEGIN
    ALTER TABLE public.product_subscriptions
        DROP CONSTRAINT IF EXISTS product_subscriptions_tier_level_check;

    ALTER TABLE public.product_subscriptions
        ADD CONSTRAINT product_subscriptions_tier_level_check
        CHECK (tier_level IN (
            'ROUTER_SaaS', 'DATA_ENTERPRISE', 'SPY_DATA', 'ALL_ACCESS',
            'SEO_STARTER', 'SEO_GROWTH', 'SEO_PRO',
            'LEADSCORE_STARTER', 'LEADSCORE_GROWTH', 'LEADSCORE_ENTERPRISE'
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
    ('demo_leadscore_starter', 'LEADSCORE_STARTER', 'ACTIVE',
     299.00, 1,
     now() + interval '30 days',
     'Demo account — LeadScore Starter tier (500 scored leads/mo)'),
    ('demo_leadscore_growth', 'LEADSCORE_GROWTH', 'ACTIVE',
     599.00, 10,
     now() + interval '30 days',
     'Demo account — LeadScore Growth tier (2,000 scored leads/mo)'),
    ('demo_leadscore_enterprise', 'LEADSCORE_ENTERPRISE', 'ACTIVE',
     999.00, 20,
     now() + interval '30 days',
     'Demo account — LeadScore Enterprise tier (10,000 scored leads/mo)')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, leadscore_enabled, leadscore_max_scored_leads,
    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled
) VALUES
    ('demo_leadscore_starter', 1, 500, 0, 0, 0),
    ('demo_leadscore_growth', 1, 2000, 0, 0, 0),
    ('demo_leadscore_enterprise', 1, 10000, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- SELECT tier, display_name, monthly_price_usd
-- FROM public.product_metadata
-- WHERE product_name = 'lead_score' AND is_active = true
-- ORDER BY sort_order;
-- =============================================================================
