-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 040: ADVERTISER PORTAL
-- ────────────────────────────────────────────────────────────────────────
-- Self-serve advertiser accounts for the native ad network. Advertisers
-- sign up, deposit ad credits, create campaigns + creatives, and monitor
-- performance.
-- ────────────────────────────────────────────────────────────────────────

-- Advertiser accounts
CREATE TABLE IF NOT EXISTS advertisers (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Identity
    email               text NOT NULL UNIQUE,
    company_name        text NOT NULL,
    contact_name        text NOT NULL,
    website             text,
    phone               text,

    -- Wallet / payment
    wallet_address      text,                    -- Solana/USDC wallet for deposits
    balance             numeric(12,2) DEFAULT 0.00,  -- Ad credit balance in USD

    -- Budget controls
    monthly_budget_cap  numeric(12,2),           -- Optional monthly cap
    auto_top_up         boolean DEFAULT false,    -- Auto-top-up when balance low
    auto_top_up_amount  numeric(10,2) DEFAULT 100.00,
    auto_top_up_threshold numeric(10,2) DEFAULT 50.00,

    -- Status
    status              text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'suspended')),
    is_active           boolean DEFAULT true,

    -- Meta
    notes               text,
    meta                jsonb DEFAULT '{}'::jsonb
);

-- Transaction history (deposits, spend, withdrawals)
CREATE TABLE IF NOT EXISTS advertiser_transactions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),

    advertiser_id       uuid NOT NULL REFERENCES advertisers(id) ON DELETE CASCADE,

    -- Transaction details
    amount              numeric(12,2) NOT NULL,  -- Positive = deposit, negative = spend/withdrawal
    currency            text DEFAULT 'USD',
    transaction_type    text NOT NULL
        CHECK (transaction_type IN ('deposit', 'spend', 'withdrawal', 'refund', 'bonus')),

    -- Reference
    reference_id        text,                    -- External reference (tx hash, invoice ID)
    campaign_id         uuid REFERENCES ad_campaigns(id) ON DELETE SET NULL,
    description         text,

    -- Balance snapshot
    balance_before      numeric(12,2),
    balance_after       numeric(12,2),

    meta                jsonb DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX IF NOT EXISTS advertisers_email_idx ON advertisers (email);
CREATE INDEX IF NOT EXISTS advertisers_status_idx ON advertisers (status, is_active);
CREATE INDEX IF NOT EXISTS adv_tx_advertiser_idx ON advertiser_transactions (advertiser_id, created_at DESC);
CREATE INDEX IF NOT EXISTS adv_tx_type_idx ON advertiser_transactions (transaction_type);

-- Auto-update updated_at on advertisers
CREATE OR REPLACE FUNCTION _advertisers_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS advertisers_updated_at ON advertisers;
CREATE TRIGGER advertisers_updated_at
    BEFORE UPDATE ON advertisers
    FOR EACH ROW EXECUTE FUNCTION _advertisers_updated_at();

COMMENT ON TABLE advertisers IS 'Advertiser accounts for the native ad network';
COMMENT ON TABLE advertiser_transactions IS 'Advertiser deposit/spend/withdrawal history';
