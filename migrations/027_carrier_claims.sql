-- Migration 027: carrier_claims table
CREATE TABLE IF NOT EXISTS public.carrier_claims (
    id uuid PRIMARY KEY,
    dispatch_id uuid,
    status text NOT NULL DEFAULT 'open',
    loss_description text,
    asset_value numeric,
    filed_at timestamptz,
    created_at timestamptz,
    settled_at timestamptz,
    settled_amount numeric
);
CREATE INDEX IF NOT EXISTS idx_carrier_claims_status ON public.carrier_claims(status);
CREATE INDEX IF NOT EXISTS idx_carrier_claims_dispatch ON public.carrier_claims(dispatch_id);
