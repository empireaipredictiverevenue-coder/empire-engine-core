-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Contractor Exchange Product (migration 032)
-- Vetted contractor marketplace with trust scoring and automated matching
-- Tiers: CONTRACTOR_EXCHANGE_STARTER ($299) · CONTRACTOR_EXCHANGE_GROWTH ($599)
--        CONTRACTOR_EXCHANGE_ENTERPRISE ($999)
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. product_metadata ──────────────────────────────────────────────────────
INSERT INTO product_metadata (product_slug, product_name, description, category, default_tier, active)
VALUES (
    'contractor_exchange',
    'Contractor Exchange',
    'Vetted contractor marketplace with trust scoring, reputation system, and automated job matching.',
    'operations',
    'CONTRACTOR_EXCHANGE_STARTER',
    1
)
ON CONFLICT (product_slug) DO NOTHING;

-- ── 2. product_pricing ───────────────────────────────────────────────────────
INSERT INTO product_pricing (product_slug, tier, mrr_usd, checks_per_month, matching_enabled, vetting_enabled)
VALUES
    ('contractor_exchange', 'CONTRACTOR_EXCHANGE_STARTER',    299,  500,  1, 0),
    ('contractor_exchange', 'CONTRACTOR_EXCHANGE_GROWTH',     599,  2000, 1, 1),
    ('contractor_exchange', 'CONTRACTOR_EXCHANGE_ENTERPRISE', 999,  10000,1, 1)
ON CONFLICT (product_slug, tier) DO NOTHING;

-- ── 3. Demo subscriptions ────────────────────────────────────────────────────
INSERT INTO product_subscriptions (subscription_id, customer_account_id, tier_level, monthly_recurring_revenue, billing_anchor_day, current_period_end, notes)
VALUES
    ('sub_demo_ce_starter',   'demo_ce_starter',   'CONTRACTOR_EXCHANGE_STARTER',    299.00, 1,  NOW() + INTERVAL '30 days', 'Demo — Contractor Exchange Starter'),
    ('sub_demo_ce_growth',    'demo_ce_growth',    'CONTRACTOR_EXCHANGE_GROWTH',     599.00, 1,  NOW() + INTERVAL '30 days', 'Demo — Contractor Exchange Growth'),
    ('sub_demo_ce_enterprise','demo_ce_enterprise','CONTRACTOR_EXCHANGE_ENTERPRISE', 999.00, 15, NOW() + INTERVAL '30 days', 'Demo — Contractor Exchange Enterprise')
ON CONFLICT (subscription_id) DO NOTHING;

-- ── 4. Demo feature flags ────────────────────────────────────────────────────
INSERT INTO product_feature_flags (customer_account_id, contractor_exchange_enabled, contractor_exchange_max_checks, contractor_exchange_matching_enabled, contractor_exchange_vetting_enabled)
VALUES
    ('demo_ce_starter',   1, 500,  1, 0),
    ('demo_ce_growth',    1, 2000, 1, 1),
    ('demo_ce_enterprise',1, 10000,1, 1)
ON CONFLICT (customer_account_id) DO NOTHING;
