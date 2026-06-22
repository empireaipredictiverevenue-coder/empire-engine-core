-- ──────────────────────────────────────────────────────────────────────────────
-- Empire AI · Content Pulse Product (migration 031)
-- Automated SEO content & landing page generation
-- Tiers: CONTENT_PULSE_STARTER ($99) · CONTENT_PULSE_GROWTH ($249) · CONTENT_PULSE_ENTERPRISE ($499)
-- ──────────────────────────────────────────────────────────────────────────────

-- ── 1. product_metadata ──────────────────────────────────────────────────────
INSERT INTO product_metadata (product_slug, product_name, description, category, default_tier, active)
VALUES (
    'content_pulse',
    'Content Pulse',
    'AI-generated SEO-optimized content — landing pages, articles, service area pages, and email content.',
    'marketing',
    'CONTENT_PULSE_STARTER',
    1
)
ON CONFLICT (product_slug) DO NOTHING;

-- ── 2. product_pricing ───────────────────────────────────────────────────────
INSERT INTO product_pricing (product_slug, tier, mrr_usd, checks_per_month, landing_pages_enabled, bulk_enabled)
VALUES
    ('content_pulse', 'CONTENT_PULSE_STARTER',   99,  500,  1, 0),
    ('content_pulse', 'CONTENT_PULSE_GROWTH',    249, 2000, 1, 1),
    ('content_pulse', 'CONTENT_PULSE_ENTERPRISE', 499, 10000,1, 1)
ON CONFLICT (product_slug, tier) DO NOTHING;

-- ── 3. Demo subscriptions ────────────────────────────────────────────────────
INSERT INTO product_subscriptions (subscription_id, customer_account_id, tier_level, monthly_recurring_revenue, billing_anchor_day, current_period_end, notes)
VALUES
    ('sub_demo_content_starter',   'demo_content_starter',   'CONTENT_PULSE_STARTER',   99.00,  1, NOW() + INTERVAL '30 days', 'Demo — Content Pulse Starter'),
    ('sub_demo_content_growth',    'demo_content_growth',    'CONTENT_PULSE_GROWTH',    249.00, 1, NOW() + INTERVAL '30 days', 'Demo — Content Pulse Growth'),
    ('sub_demo_content_enterprise','demo_content_enterprise','CONTENT_PULSE_ENTERPRISE',499.00, 15,NOW() + INTERVAL '30 days', 'Demo — Content Pulse Enterprise')
ON CONFLICT (subscription_id) DO NOTHING;

-- ── 4. Demo feature flags ────────────────────────────────────────────────────
INSERT INTO product_feature_flags (customer_account_id, content_pulse_enabled, content_pulse_max_checks, content_pulse_landing_pages_enabled, content_pulse_bulk_enabled)
VALUES
    ('demo_content_starter',   1, 500,  1, 0),
    ('demo_content_growth',    1, 2000, 1, 1),
    ('demo_content_enterprise',1, 10000,1, 1)
ON CONFLICT (customer_account_id) DO NOTHING;
