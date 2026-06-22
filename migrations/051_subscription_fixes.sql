-- 051: Fix subscription + invoice tables
-- Add unique constraint on contractor_subscriptions.contractor_id for upsert
-- and ensure dispatch_invoices has all required defaults

-- One subscription per contractor
CREATE UNIQUE INDEX IF NOT EXISTS uq_sub_contractor ON contractor_subscriptions(contractor_id);

-- A dispatch_id may be invoiced multiple times if retried, so no unique on it.
-- But ensure the table exists with the right shape (re-runs safe via IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS dispatch_invoices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dispatch_id uuid,
    contractor_id uuid REFERENCES contractors(id),
    amount_usdc numeric NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'unpaid',
    paid_at timestamptz,
    paid_tx_sig text,
    memo text,
    created_at timestamptz DEFAULT now(),
    expires_at timestamptz DEFAULT now() + interval '7 days'
);