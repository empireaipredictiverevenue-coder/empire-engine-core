-- 050: Subscription tiers + per-dispatch invoicing
-- The two monetization paths:
--   1. contractor_subscriptions: monthly USDC payment → tier (free/basic/pro/enterprise)
--   2. dispatch_invoices: per-lead USDC charge for outreach to non-subscribers

CREATE TABLE IF NOT EXISTS contractor_subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id uuid REFERENCES contractors(id),
    tier text NOT NULL DEFAULT 'free',                  -- free | basic | pro | enterprise
    monthly_amount_usdc numeric DEFAULT 0,
    status text NOT NULL DEFAULT 'pending',               -- pending | active | lapsed | cancelled
    wallet_address text,                                  -- contractor's solana wallet
    started_at timestamptz,
    expires_at timestamptz,
    last_payment_at timestamptz,
    last_payment_tx_sig text,
    next_payment_due_at timestamptz,
    notes text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sub_contractor ON contractor_subscriptions(contractor_id);
CREATE INDEX IF NOT EXISTS idx_sub_status ON contractor_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_sub_expires ON contractor_subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sub_wallet ON contractor_subscriptions(wallet_address);

CREATE TABLE IF NOT EXISTS dispatch_invoices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dispatch_id uuid,
    contractor_id uuid REFERENCES contractors(id),
    amount_usdc numeric NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'unpaid',                 -- unpaid | paid | expired | cancelled
    paid_at timestamptz,
    paid_tx_sig text,
    memo text,
    created_at timestamptz DEFAULT now(),
    expires_at timestamptz DEFAULT now() + interval '7 days'
);
CREATE INDEX IF NOT EXISTS idx_inv_dispatch ON dispatch_invoices(dispatch_id);
CREATE INDEX IF NOT EXISTS idx_inv_contractor ON dispatch_invoices(contractor_id);
CREATE INDEX IF NOT EXISTS idx_inv_status ON dispatch_invoices(status);

-- Tier definitions table (single source of truth for pricing)
CREATE TABLE IF NOT EXISTS subscription_tiers (
    id text PRIMARY KEY,                                  -- free | basic | pro | enterprise
    name text NOT NULL,
    monthly_usdc numeric NOT NULL,
    features jsonb NOT NULL DEFAULT '{}'::jsonb,
    dispatch_priority int DEFAULT 0,                       -- 0 = lowest, higher = faster routing
    leads_per_month int DEFAULT 0,                         -- 0 = unlimited
    active boolean DEFAULT true,
    sort_order int DEFAULT 0
);
INSERT INTO subscription_tiers (id, name, monthly_usdc, features, dispatch_priority, leads_per_month, sort_order) VALUES
    ('free', 'Free', 0, '{"lead_delay_minutes":1440,"history_days":7,"analytics":false}', 0, 3, 0),
    ('basic', 'Basic', 99, '{"lead_delay_minutes":60,"history_days":30,"analytics":false,"priority":true}', 1, 50, 1),
    ('pro', 'Pro', 299, '{"lead_delay_minutes":0,"history_days":90,"analytics":true,"priority":true}', 2, 200, 2),
    ('enterprise', 'Enterprise', 499, '{"lead_delay_minutes":0,"history_days":365,"analytics":true,"priority":true,"dedicated_rep":true}', 3, 0, 3)
ON CONFLICT (id) DO UPDATE SET
    monthly_usdc = EXCLUDED.monthly_usdc,
    features = EXCLUDED.features,
    dispatch_priority = EXCLUDED.dispatch_priority,
    leads_per_month = EXCLUDED.leads_per_month;