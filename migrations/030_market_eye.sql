-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Market Eye Product (migration 030)
-- Competitive intelligence & market monitoring
-- Tiers: MARKET_EYE_STARTER ($199) · MARKET_EYE_GROWTH ($499) · MARKET_EYE_ENTERPRISE ($999)
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. product_metadata ──────────────────────────────────────────────────────
INSERT OR IGNORE INTO product_metadata (product_slug, product_name, description, category, default_tier, active)
VALUES (
    'market_eye',
    'Market Eye',
    'Competitive intelligence — monitor competitor web/social/reviews, pricing shifts, and market trends.',
    'analytics',
    'MARKET_EYE_STARTER',
    1
);

-- ── 2. product_pricing (3 tiers) ─────────────────────────────────────────────
INSERT OR IGNORE INTO product_pricing (product_slug, tier, mrr_usd, checks_per_month, brief_enabled, alerts_enabled)
VALUES
    ('market_eye', 'MARKET_EYE_STARTER',    199,  500,  0, 0),
    ('market_eye', 'MARKET_EYE_GROWTH',     499,  2000, 1, 1),
    ('market_eye', 'MARKET_EYE_ENTERPRISE', 999,  10000,1, 1);

-- ── 3. Demo subscriptions ────────────────────────────────────────────────────
INSERT OR IGNORE INTO product_subscriptions (subscription_id, customer_account_id, tier_level, monthly_recurring_revenue, billing_anchor_day, current_period_end, notes)
VALUES
    ('sub_demo_market_eye_starter',   'demo_market_eye_starter',   'MARKET_EYE_STARTER',    199.00, 1, datetime('now', '+30 days'), 'Demo — Market Eye Starter'),
    ('sub_demo_market_eye_growth',    'demo_market_eye_growth',    'MARKET_EYE_GROWTH',     499.00, 1, datetime('now', '+30 days'), 'Demo — Market Eye Growth'),
    ('sub_demo_market_eye_enterprise','demo_market_eye_enterprise','MARKET_EYE_ENTERPRISE', 999.00, 15,datetime('now', '+30 days'), 'Demo — Market Eye Enterprise');

-- ── 4. Demo feature flags ────────────────────────────────────────────────────
INSERT OR IGNORE INTO product_feature_flags (customer_account_id, market_eye_enabled, market_eye_max_checks, market_eye_brief_enabled, market_eye_alerts_enabled)
VALUES
    ('demo_market_eye_starter',   1, 500,  0, 0),
    ('demo_market_eye_growth',    1, 2000, 1, 1),
    ('demo_market_eye_enterprise',1, 10000,1, 1);
