-- EMPIRE V49 · Contractor Priority Subscriptions
-- $99/mo Solana USDC tier. Tracks contractor signups, payment verification,
-- and activation status. Operator verifies on-chain and activates manually.
CREATE TABLE IF NOT EXISTS contractor_priority_subscriptions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    name            text NOT NULL,
    company         text NOT NULL,
    email           text NOT NULL,
    phone           text NOT NULL,
    metro           text NOT NULL,
    solana_wallet   text,
    tx_signature    text NOT NULL,
    amount_usdc     numeric(10,2) NOT NULL DEFAULT 99,
    status          text NOT NULL DEFAULT 'pending_verification'
        CHECK (status IN ('pending_verification','verified','active','cancelled','expired')),
    verified_by     text,
    verified_at     timestamptz,
    activated_at    timestamptz,
    cancelled_at    timestamptz,
    meta            jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_priority_email ON contractor_priority_subscriptions(email);
CREATE INDEX IF NOT EXISTS idx_priority_status ON contractor_priority_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_priority_tx ON contractor_priority_subscriptions(tx_signature);
