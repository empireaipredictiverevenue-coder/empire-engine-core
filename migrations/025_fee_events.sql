-- Migration 025: fee_events (in-app representation of settled-claim fees)
--
-- One row per settled claim. amount_usd = claim_amount, fee_usd =
-- claim_amount * 0.03, status='pending' until payout. Reconciles with
-- the on-chain empire_revenue_ledger (Solana USDC) when the payment
-- arrives.

CREATE TABLE IF NOT EXISTS public.fee_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    claim_id        text,                            -- external claim ref (carrier or hub)
    contractor_id   uuid REFERENCES public.contractors(id),
    lead_id         uuid,                            -- the enriched_lead that became the claim
    claim_amount    numeric(12,2) NOT NULL,
    fee_amount      numeric(12,2) NOT NULL,
    fee_percent     numeric(5,4) NOT NULL DEFAULT 0.0300,
    currency        text NOT NULL DEFAULT 'USD',
    settled_at      timestamptz,
    source          text NOT NULL DEFAULT 'fee_watcher',  -- which agent produced it
    status          text NOT NULL DEFAULT 'pending',       -- pending | paid | invoiced | cancelled
    meta            jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS fee_events_settled_at_idx
    ON public.fee_events (settled_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS fee_events_status_idx
    ON public.fee_events (status);

CREATE INDEX IF NOT EXISTS fee_events_contractor_id_idx
    ON public.fee_events (contractor_id);
