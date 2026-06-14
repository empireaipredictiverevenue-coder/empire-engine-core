-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Forecast Product (migration 029)
-- Predictive revenue forecasting as a standalone product
-- Tiers: FORECAST_LITE ($199/mo), FORECAST_PRO ($499/mo), FORECAST_ENTERPRISE ($999/mo)
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. product_metadata ──────────────────────────────────────────────────────
INSERT OR IGNORE INTO product_metadata (product_slug, product_name, description, category, default_tier, active)
VALUES (
    'forecast',
    'Forecast',
    'Predictive revenue projections with per-lane breakdowns, AI narrative, and accuracy tracking.',
    'analytics',
    'FORECAST_LITE',
    1
);

-- ── 2. product_pricing (3 tiers) ─────────────────────────────────────────────
INSERT OR IGNORE INTO product_pricing (product_slug, tier, mrr_usd, checks_per_month, narrative_enabled, what_if_enabled)
VALUES
    ('forecast', 'FORECAST_LITE',       199,  500,  0, 0),
    ('forecast', 'FORECAST_PRO',        499,  2000, 1, 0),
    ('forecast', 'FORECAST_ENTERPRISE', 999,  10000,1, 1);

-- ── 3. Update product_subscriptions CHECK constraint ─────────────────────────
DROP TABLE IF EXISTS _migration_helper;
CREATE TEMP TABLE _migration_helper AS
SELECT sql FROM sqlite_master
WHERE type='table' AND name='product_subscriptions';
INSERT OR IGNORE INTO product_subscriptions (subscription_id, customer_account_id, tier_level, monthly_recurring_revenue, billing_anchor_day, current_period_end, notes)
SELECT
    'sub_demo_forecast_lite', 'demo_forecast_lite', 'FORECAST_LITE', 199.00, 1,
    datetime('now', '+30 days'),
    'Demo account — Forecast Lite tier'
WHERE NOT EXISTS (
    SELECT 1 FROM product_subscriptions WHERE customer_account_id = 'demo_forecast_lite'
);

INSERT OR IGNORE INTO product_subscriptions (subscription_id, customer_account_id, tier_level, monthly_recurring_revenue, billing_anchor_day, current_period_end, notes)
SELECT
    'sub_demo_forecast_pro', 'demo_forecast_pro', 'FORECAST_PRO', 499.00, 1,
    datetime('now', '+30 days'),
    'Demo account — Forecast Pro tier (with LLM narrative)'
WHERE NOT EXISTS (
    SELECT 1 FROM product_subscriptions WHERE customer_account_id = 'demo_forecast_pro'
);

INSERT OR IGNORE INTO product_subscriptions (subscription_id, customer_account_id, tier_level, monthly_recurring_revenue, billing_anchor_day, current_period_end, notes)
SELECT
    'sub_demo_forecast_enterprise', 'demo_forecast_enterprise', 'FORECAST_ENTERPRISE', 999.00, 15,
    datetime('now', '+30 days'),
    'Demo account — Forecast Enterprise tier (what-if scenarios)'
WHERE NOT EXISTS (
    SELECT 1 FROM product_subscriptions WHERE customer_account_id = 'demo_forecast_enterprise'
);

-- ── 5. Demo feature flags ────────────────────────────────────────────────────
INSERT OR IGNORE INTO product_feature_flags (customer_account_id, forecast_enabled, forecast_max_checks, forecast_narrative_enabled, forecast_what_if_enabled)
VALUES
    ('demo_forecast_lite',      1, 500,  0, 0),
    ('demo_forecast_pro',       1, 2000, 1, 0),
    ('demo_forecast_enterprise',1, 10000,1, 1);

-- ── 6. product_usage_log CHECK constraint update ─────────────────────────────
INSERT OR IGNORE INTO product_usage_log (customer_account_id, product_name, usage_event, quantity, unit, metadata)
SELECT
    'demo_forecast_lite', 'forecast', 'snapshot_view', 1, 'count', '{"note": "seed_demo"}';
