-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 019: SEO OPTIMIZER PRODUCT TIERS
-- =============================================================================
-- Productizes the SEO Optimizer Agent (bots/seo_agent.py) as 3 sellable
-- subscription tiers: Starter ($99/mo), Growth ($199/mo), Pro ($499/mo).
--
-- Adds to both product systems:
--   1. strike_packs — the product catalog for display/sales
--   2. product_subscriptions — billing/entitlement backend (tier + MRR)
--   3. product_feature_flags — SEO-specific feature toggles
--   4. product_usage_log — SEO optimizer usage events
--
-- The SEO agent already has full API coverage in hub.py:
--   /api/seo/performance  — audits, keywords, content, genome
--   /api/seo/research     — deep property/market/competitor/storm research
--   /api/seo/generate     — content + landing page generation
--   /api/seo/pipeline     — end-to-end research → generate
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.
-- =============================================================================


-- ── 1. UPDATE PRODUCT_SUBSCRIPTIONS TIER CHECK ─────────────────────────
-- Add SEO_STARTER, SEO_GROWTH, SEO_PRO to the valid tier_level values.
ALTER TABLE public.product_subscriptions
    DROP CONSTRAINT IF EXISTS product_subscriptions_tier_level_check;

ALTER TABLE public.product_subscriptions
    ADD CONSTRAINT product_subscriptions_tier_level_check
    CHECK (tier_level IN (
        'ROUTER_SaaS', 'DATA_ENTERPRISE', 'SPY_DATA', 'ALL_ACCESS',
        'SEO_STARTER', 'SEO_GROWTH', 'SEO_PRO'
    ));


-- ── 2. ADD SEO COLUMNS TO PRODUCT_FEATURE_FLAGS ────────────────────────
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS seo_audits_enabled              integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seo_keyword_tracking_enabled    integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seo_content_generation_enabled  integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seo_research_pipeline_enabled   integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seo_landing_pages_enabled       integer DEFAULT 0;

-- Per-tier limits (0 = unlimited)
ALTER TABLE public.product_feature_flags
    ADD COLUMN IF NOT EXISTS seo_audits_per_month            integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seo_keywords_per_month          integer DEFAULT 0,
    ADD COLUMN IF NOT EXISTS seo_content_pieces_per_month    integer DEFAULT 0;

COMMENT ON COLUMN public.product_feature_flags.seo_audits_enabled IS 'Website audits (1=Active)';
COMMENT ON COLUMN public.product_feature_flags.seo_keyword_tracking_enabled IS 'Keyword tracking (1=Active)';
COMMENT ON COLUMN public.product_feature_flags.seo_content_generation_enabled IS 'Optimized content generation (1=Active)';
COMMENT ON COLUMN public.product_feature_flags.seo_research_pipeline_enabled IS 'Deep research pipeline (1=Active)';
COMMENT ON COLUMN public.product_feature_flags.seo_landing_pages_enabled IS 'Landing page generation (1=Active)';
COMMENT ON COLUMN public.product_feature_flags.seo_audits_per_month IS 'Monthly audit limit (0=unlimited)';
COMMENT ON COLUMN public.product_feature_flags.seo_keywords_per_month IS 'Monthly keyword tracking limit (0=unlimited)';
COMMENT ON COLUMN public.product_feature_flags.seo_content_pieces_per_month IS 'Monthly content generation limit (0=unlimited)';


-- ── 3. UPDATE PRODUCT_USAGE_LOG CHECK CONSTRAINT ───────────────────────
-- Add 'seo_optimizer' as a valid product_name value.
ALTER TABLE public.product_usage_log
    DROP CONSTRAINT IF EXISTS product_usage_log_product_name_check;

ALTER TABLE public.product_usage_log
    ADD CONSTRAINT product_usage_log_product_name_check
    CHECK (product_name IN (
        'inbound_router', 'data_vault', 'buyer_spy',
        'omni_bridge', 'agent_orchestrator', 'b2b_pro',
        'seo_optimizer'
    ));


-- ── 4. SEED SEO PRODUCTS IN STRIKE_PACKS CATALOG ──────────────────────
-- Three SEO optimizer tiers. lane_count=0 and max_leads=0 since this is
-- not a lead-gen product — it's a SaaS optimization tool.
INSERT INTO public.strike_packs (slug, name, description, tier, monthly_price_cents, price_per_lead_cents, max_leads_per_day, max_leads_per_month, delivery_channels, target_buyer, features, lane_count, niches, sort_order)
VALUES
    ('seo_starter',
     'SEO Optimizer — Starter',
     'Automated website audits, keyword tracking, and AI content generation for contractors. 5 audits/mo, 50 keywords, 10 content pieces.',
     'standard', 9900, 0, 0, 0, '{dashboard,api}',
     'contractor',
     '["5 website audits per month", "50 keywords tracked", "10 AI-optimized content pieces", "SEO performance dashboard", "Keyword intent scoring"]',
     0, ARRAY['SEO'], 50),

    ('seo_growth',
     'SEO Optimizer — Growth',
     'Full SEO pipeline for growing businesses. 15 audits/mo, 200 keywords, 20 content pieces, plus landing page generation and deep research.',
     'standard', 19900, 0, 0, 0, '{dashboard,api}',
     'contractor',
     '["15 website audits per month", "200 keywords tracked", "20 AI-optimized content pieces", "Landing page generation", "Deep research pipeline (property + market)", "Genome evolution tracking"]',
     0, ARRAY['SEO'], 60),

    ('seo_pro',
     'SEO Optimizer — Pro',
     'Unlimited SEO optimization for enterprises. Full research pipeline, unlimited audits/keywords/content, landing page generation, priority support.',
     'standard', 49900, 0, 0, 0, '{dashboard,api,webhook}',
     'enterprise',
     '["Unlimited website audits", "Unlimited keyword tracking", "Unlimited content generation", "Full research pipeline (property + market + competitor + storm)", "Landing page generation (cinematic/modern/classic)", "Priority support + custom integrations", "Real-time genome evolution"]',
     0, ARRAY['SEO'], 70)

ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    monthly_price_cents = EXCLUDED.monthly_price_cents,
    delivery_channels = EXCLUDED.delivery_channels,
    features = EXCLUDED.features,
    sort_order = EXCLUDED.sort_order
RETURNING id, slug, name;


-- ── 5. SEED DEMO SEO SUBSCRIPTIONS IN PRODUCT_SUBSCRIPTIONS ───────────
-- Demo accounts so the MRR dashboard and product catalog populate.
INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_end, notes
) VALUES
    ('demo_seo_starter', 'SEO_STARTER', 'ACTIVE',
     99.00, 1,
     now() + interval '30 days',
     'Demo account — SEO Optimizer Starter tier (5 audits/mo)'),
    ('demo_seo_growth', 'SEO_GROWTH', 'ACTIVE',
     199.00, 10,
     now() + interval '30 days',
     'Demo account — SEO Optimizer Growth tier (15 audits/mo + landing pages)'),
    ('demo_seo_pro', 'SEO_PRO', 'ACTIVE',
     499.00, 20,
     now() + interval '30 days',
     'Demo account — SEO Optimizer Pro tier (unlimited)')
ON CONFLICT (customer_account_id) DO NOTHING;


-- ── 6. SEED FEATURE FLAGS FOR SEO DEMO ACCOUNTS ──────────────────────
INSERT INTO public.product_feature_flags (
    customer_account_id,
    seo_audits_enabled, seo_keyword_tracking_enabled,
    seo_content_generation_enabled, seo_research_pipeline_enabled,
    seo_landing_pages_enabled,
    seo_audits_per_month, seo_keywords_per_month, seo_content_pieces_per_month
) VALUES
    ('demo_seo_starter', 1, 1, 1, 0, 0, 5, 50, 10),
    ('demo_seo_growth',  1, 1, 1, 1, 1, 15, 200, 20),
    ('demo_seo_pro',     1, 1, 1, 1, 1, 0, 0, 0)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- -- All SEO strike packs in the catalog:
-- SELECT slug, name, monthly_price_cents / 100 AS price_usd,
--        features->>0 AS first_feature
-- FROM public.strike_packs
-- WHERE 'SEO' = ANY(niches)
-- ORDER BY sort_order;
--
-- -- All SEO product subscriptions:
-- SELECT customer_account_id, tier_level, monthly_recurring_revenue AS mrr
-- FROM public.product_subscriptions
-- WHERE tier_level LIKE 'SEO_%'
-- ORDER BY monthly_recurring_revenue;
--
-- -- Total SEO MRR:
-- SELECT SUM(monthly_recurring_revenue) AS total_seo_mrr
-- FROM public.product_subscriptions
-- WHERE subscription_status = 'ACTIVE' AND tier_level LIKE 'SEO_%';
-- =============================================================================
