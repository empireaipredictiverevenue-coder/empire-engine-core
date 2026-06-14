-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 020: PRODUCT METADATA CATALOG
-- =============================================================================
-- Stores all suite product metadata (pricing, features, descriptions) in
-- Supabase so prices can be updated without code changes.
--
-- The /api/v1/products/catalog endpoint reads from this table instead of
-- hardcoded Python dicts. Add/update a row here to change product metadata
-- at runtime.
--
-- Table:
--   1. product_metadata  — one row per product tier, with pricing + features + descriptions
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.
-- =============================================================================


-- ── 1. PRODUCT METADATA ────────────────────────────────────────────
-- Single source of truth for suite product catalog data. Each row
-- represents one tier of a product with its pricing and feature list.
--
-- Columns:
--   tier              — unique tier key (e.g. 'SEO_STARTER', 'ROUTER_SaaS')
--   product_name      — logical product group (e.g. 'seo_optimizer', 'inbound_router')
--   display_name      — human-readable name shown in the UI (e.g. 'SEO Starter')
--   description       — short description of what this tier includes
--   monthly_price_usd — monthly subscription price in USD (integer cents avoided for clarity)
--   price_per_unit    — optional per-unit pricing description string (e.g. '$0.25 per routed call')
--   features          — JSON array of {label, value} feature descriptors
--   sort_order        — display ordering (lower = shown first)
--   is_public         — whether to show in the public catalog
--   is_active         — logical delete flag for deprecating old tiers
--   created_at        — row creation timestamp
--   updated_at        — last modification timestamp
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.product_metadata (
    tier                text PRIMARY KEY,
    product_name        text NOT NULL,
    display_name        text NOT NULL,
    description         text NOT NULL DEFAULT '',
    monthly_price_usd   numeric(10,2) NOT NULL DEFAULT 0.00,
    price_per_unit      text DEFAULT NULL,
    features            jsonb NOT NULL DEFAULT '[]'::jsonb,
    sort_order          integer NOT NULL DEFAULT 0,
    is_public           boolean NOT NULL DEFAULT true,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.product_metadata IS 'Suite product catalog: tier pricing, features, descriptions — editable at runtime via SQL UPDATE';
COMMENT ON COLUMN public.product_metadata.tier IS 'Unique tier key e.g. SEO_STARTER, ROUTER_SaaS';
COMMENT ON COLUMN public.product_metadata.product_name IS 'Logical product group e.g. seo_optimizer, inbound_router';
COMMENT ON COLUMN public.product_metadata.display_name IS 'Human-readable name shown in the UI';
COMMENT ON COLUMN public.product_metadata.monthly_price_usd IS 'Monthly subscription price in USD';
COMMENT ON COLUMN public.product_metadata.price_per_unit IS 'Optional per-unit pricing description';
COMMENT ON COLUMN public.product_metadata.features IS 'JSON array of {label, value} feature descriptors';

CREATE INDEX IF NOT EXISTS product_metadata_sort_idx ON public.product_metadata (sort_order);
CREATE INDEX IF NOT EXISTS product_metadata_active_idx ON public.product_metadata (is_active);


-- ── 2. SEED DATA ────────────────────────────────────────────────────
-- Bootstrap all 7 suite products with current pricing from empire_pricing.py.
-- Idempotent via ON CONFLICT (tier) DO NOTHING.
-- =============================================================================
INSERT INTO public.product_metadata AS pm (tier, product_name, display_name, description, monthly_price_usd, price_per_unit, features, sort_order, is_public, is_active) VALUES

-- SEO Suite — 3 tiers
('SEO_STARTER', 'seo_optimizer', 'SEO Starter',
 'Entry-level SEO with 5 audits, 50 keywords, 10 content pieces per month',
 99.00, NULL,
 '[{"label": "SEO Audits", "value": "5/month"}, {"label": "Keywords Tracked", "value": "50"}, {"label": "Content Pieces", "value": "10/month"}, {"label": "Keyword Tracking", "value": "Enabled"}]'::jsonb,
 10, true, true),

('SEO_GROWTH', 'seo_optimizer', 'SEO Growth',
 'Growth-tier SEO: 15 audits, 200 keywords, 20 content pieces, research pipeline & landing pages',
 199.00, NULL,
 '[{"label": "SEO Audits", "value": "15/month"}, {"label": "Keywords Tracked", "value": "200"}, {"label": "Content Pieces", "value": "20/month"}, {"label": "Research Pipeline", "value": "Enabled"}, {"label": "Landing Pages", "value": "Enabled"}]'::jsonb,
 20, true, true),

('SEO_PRO', 'seo_optimizer', 'SEO Pro',
 'Pro SEO with unlimited audits, unlimited keywords, full research & content pipeline',
 499.00, NULL,
 '[{"label": "SEO Audits", "value": "Unlimited"}, {"label": "Keywords Tracked", "value": "Unlimited"}, {"label": "Content Pieces", "value": "Unlimited"}, {"label": "Research Pipeline", "value": "Enabled"}, {"label": "Landing Pages", "value": "Enabled"}]'::jsonb,
 30, true, true),

-- Products
('ROUTER_SaaS', 'inbound_router', 'Inbound Router',
 'Inbound call routing with AI triage, Vonage PSTN integration, and entitlement metering',
 499.00, '$0.25 per routed call',
 '[{"label": "Inbound Calls", "value": "Metered"}, {"label": "AI Triage", "value": "Enabled"}, {"label": "Vonage PSTN", "value": "Included"}]'::jsonb,
 40, true, true),

('DATA_ENTERPRISE', 'data_vault', 'Data Vault',
 'Enterprise data vault with long-term retention, structured storage & secure API access',
 799.00, '$0.02 per stored record/mo',
 '[{"label": "Data Retention", "value": "90 days"}, {"label": "API Access", "value": "Enabled"}, {"label": "Structured Storage", "value": "Enabled"}]'::jsonb,
 50, true, true),

('SPY_DATA', 'buyer_spy', 'Buyer Spy AI',
 'Buyer intelligence: AI-powered transcript analysis, intent scoring & competitive tracking',
 1499.00, '$5 per analysis',
 '[{"label": "Transcript Analysis", "value": "100/day"}, {"label": "Intent Scoring", "value": "Enabled"}, {"label": "Competitive Tracking", "value": "Enabled"}]'::jsonb,
 60, true, true),

('ALL_ACCESS', 'all_products', 'All Access',
 'Full access to all Empire AI products: inbound routing, data vault, buyer spy & SEO suite',
 2499.00, NULL,
 '[{"label": "All Products", "value": "Included"}, {"label": "SEO Suite", "value": "Full Access"}, {"label": "Priority Support", "value": "Included"}]'::jsonb,
 100, true, true)

ON CONFLICT (tier) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- -- All active products ordered by sort_order:
-- SELECT tier, display_name, monthly_price_usd, product_name
-- FROM public.product_metadata
-- WHERE is_active = true
-- ORDER BY sort_order;
--
-- -- Update a price (no code change needed):
-- UPDATE public.product_metadata
-- SET monthly_price_usd = 149.00, updated_at = now()
-- WHERE tier = 'SEO_STARTER';
-- =============================================================================
