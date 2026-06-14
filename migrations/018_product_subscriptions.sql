-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 018: PRODUCT SUBSCRIPTIONS (SUITE ENGINE)
-- =============================================================================
-- Creates the product subscription tables for the Suite Subscription Engine
-- in Supabase. These tables track who's subscribed to what product tier,
-- feature flag entitlements, usage metering for billing, and per-pipeline
-- cost attribution.
--
-- Previously these lived only in local SQLite (products/data/storm_alerts.sqlite).
-- This migration creates the Supabase equivalents so the dashboard and APIs
-- can read/write subscription data centrally.
--
-- Tables:
--   1. product_subscriptions   — subscription tiers, MRR, billing periods
--   2. product_feature_flags   — per-account feature entitlements
--   3. product_usage_log       — usage metering events for billing
--   4. customer_usage_ledger   — per-pipeline billing/cost attribution
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.
-- =============================================================================


-- ── 1. PRODUCT SUBSCRIPTIONS ─────────────────────────────────────────
-- One row per customer subscription. Tracks tier level, MRR, and billing
-- period. Used by SuiteSubscriptionEngine for entitlement checks and
-- the MRR dashboard widget.
CREATE TABLE IF NOT EXISTS public.product_subscriptions (
    subscription_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),

    -- Customer identity
    customer_account_id         text NOT NULL UNIQUE,

    -- Tier & status
    tier_level                  text NOT NULL CHECK (tier_level IN (
                                    'ROUTER_SaaS', 'DATA_ENTERPRISE', 'SPY_DATA', 'ALL_ACCESS'
                                )),
    subscription_status         text DEFAULT 'ACTIVE' CHECK (
                                    subscription_status IN ('ACTIVE', 'PAST_DUE', 'CANCELED', 'TRIALING')
                                ),

    -- MRR (Monthly Recurring Revenue in USD)
    monthly_recurring_revenue   numeric(12,2) DEFAULT 0.00,

    -- Billing
    billing_anchor_day          integer DEFAULT 1,   -- day of month billing starts
    current_period_start        timestamptz DEFAULT now(),
    current_period_end          timestamptz,
    trial_end                   timestamptz,

    -- Stripe integration
    stripe_customer_id          text,
    stripe_subscription_id      text UNIQUE,

    -- Notes
    notes                       text DEFAULT ''
);

COMMENT ON TABLE  public.product_subscriptions IS 'Suite subscription tiers: ROUTER_SaaS, DATA_ENTERPRISE, SPY_DATA, ALL_ACCESS';
COMMENT ON COLUMN public.product_subscriptions.monthly_recurring_revenue IS 'MRR in USD — used for actual MRR tracking on dashboard';
COMMENT ON COLUMN public.product_subscriptions.customer_account_id IS 'Stable account identifier referenced by product_feature_flags and usage logs';

CREATE INDEX IF NOT EXISTS product_subs_account_idx ON public.product_subscriptions (customer_account_id);
CREATE INDEX IF NOT EXISTS product_subs_status_idx   ON public.product_subscriptions (subscription_status);
CREATE INDEX IF NOT EXISTS product_subs_tier_idx      ON public.product_subscriptions (tier_level);


-- ── 2. PRODUCT FEATURE FLAGS ─────────────────────────────────────────
-- Per-account feature entitlements. Each row maps to one subscription.
-- The SuiteGuard reads these to gate access to product features.
CREATE TABLE IF NOT EXISTS public.product_feature_flags (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),

    -- Who
    customer_account_id         text NOT NULL UNIQUE
                                REFERENCES public.product_subscriptions(customer_account_id),

    -- Feature toggles (0 = Locked, 1 = Active)
    inbound_router_enabled      integer DEFAULT 0,
    data_retention_enabled      integer DEFAULT 0,
    buyer_spy_enabled           integer DEFAULT 0,
    omni_bridge_enabled         integer DEFAULT 0,
    agent_orchestrator_enabled  integer DEFAULT 0,
    b2b_pro_enabled             integer DEFAULT 0,

    -- Per-feature limits (0 = unlimited)
    inbound_router_max_calls    integer DEFAULT 0,
    data_retention_days         integer DEFAULT 90,
    buyer_spy_analyze_per_day   integer DEFAULT 100,

    -- Additional account config (JSON)
    meta                        jsonb DEFAULT '{}'::jsonb
);

COMMENT ON TABLE  public.product_feature_flags IS 'Per-account feature entitlements. Read by SuiteGuard for access control.';
COMMENT ON COLUMN public.product_feature_flags.customer_account_id IS 'Maps to product_subscriptions.customer_account_id';


-- ── 3. PRODUCT USAGE LOG ─────────────────────────────────────────────
-- Metered usage events for billing. Written by SuiteGuard.log_usage().
-- Used to compute overage charges and generate invoices.
CREATE TABLE IF NOT EXISTS public.product_usage_log (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at                  timestamptz NOT NULL DEFAULT now(),

    -- Who
    customer_account_id         text NOT NULL
                                REFERENCES public.product_subscriptions(customer_account_id),

    -- What
    product_name                text NOT NULL CHECK (product_name IN (
                                    'inbound_router', 'data_vault', 'buyer_spy',
                                    'omni_bridge', 'agent_orchestrator', 'b2b_pro'
                                )),
    usage_event                 text NOT NULL,   -- e.g. 'inbound_call', 'data_upload', 'spy_analysis'
    quantity                    integer DEFAULT 1,
    unit                        text DEFAULT 'count',

    -- Event payload
    metadata                    jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS product_usage_log_account_idx
    ON public.product_usage_log (customer_account_id, product_name, created_at DESC);
CREATE INDEX IF NOT EXISTS product_usage_log_event_idx
    ON public.product_usage_log (usage_event, created_at DESC);

COMMENT ON TABLE public.product_usage_log IS 'Metered usage events for billing. Written by SuiteGuard.';


-- ── 4. CUSTOMER USAGE LEDGER ─────────────────────────────────────────
-- Per-pipeline billing ledger for cost attribution. Each row records
-- an API call or pipeline execution and the computed cost.
CREATE TABLE IF NOT EXISTS public.customer_usage_ledger (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at                  timestamptz NOT NULL DEFAULT now(),

    -- Who
    customer_account_id         text NOT NULL
                                REFERENCES public.product_subscriptions(customer_account_id),

    -- What
    api_endpoint_accessed       text NOT NULL,
    computed_raw_cost           numeric(12,6) DEFAULT 0.0,
    client_billed_amount        numeric(12,6) DEFAULT 0.0,

    -- Event payload
    metadata                    jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS customer_usage_ledger_account_idx
    ON public.customer_usage_ledger (customer_account_id, created_at DESC);


-- ── 5. SEED TEST DATA ───────────────────────────────────────────────
-- Bootstrap a test subscription so the dashboard MRR widget has data.
-- Idempotent via ON CONFLICT.
INSERT INTO public.product_subscriptions (
    customer_account_id, tier_level, subscription_status,
    monthly_recurring_revenue, billing_anchor_day,
    current_period_end, notes
) VALUES
    ('demo_contractor', 'ROUTER_SaaS', 'ACTIVE',
     499.00, 1,
     now() + interval '30 days',
     'Demo account — Inbound Router SaaS tier'),
    ('demo_enterprise', 'ALL_ACCESS', 'ACTIVE',
     2499.00, 15,
     now() + interval '30 days',
     'Demo account — All Access enterprise tier')
ON CONFLICT (customer_account_id) DO NOTHING;

-- Seed feature flags for demo accounts
INSERT INTO public.product_feature_flags (
    customer_account_id, inbound_router_enabled, data_retention_enabled,
    buyer_spy_enabled, inbound_router_max_calls, data_retention_days
) VALUES
    ('demo_contractor', 1, 0, 0, 500, 30),
    ('demo_enterprise', 1, 1, 1, 10000, 365)
ON CONFLICT (customer_account_id) DO NOTHING;


-- =============================================================================
-- VERIFICATION QUERIES (run separately)
-- =============================================================================
-- -- All subscriptions with MRR:
-- SELECT customer_account_id, tier_level, subscription_status,
--        monthly_recurring_revenue AS mrr
-- FROM public.product_subscriptions
-- ORDER BY monthly_recurring_revenue DESC;
--
-- -- Total active MRR:
-- SELECT SUM(monthly_recurring_revenue) AS total_mrr
-- FROM public.product_subscriptions
-- WHERE subscription_status = 'ACTIVE';
--
-- -- Subscriptions with their feature flags:
-- SELECT ps.customer_account_id, ps.tier_level, ps.monthly_recurring_revenue,
--        pff.inbound_router_enabled, pff.data_retention_enabled, pff.buyer_spy_enabled
-- FROM public.product_subscriptions ps
-- LEFT JOIN public.product_feature_flags pff ON pff.customer_account_id = ps.customer_account_id
-- ORDER BY ps.monthly_recurring_revenue DESC;
-- =============================================================================
