-- Empire AI · Predictive Revenue
-- Solana USDC Revenue Ledger
-- ===============================
-- Maps every on-chain USDC transaction to the Empire vault wallet into a
-- queryable Supabase table. Each row captures the sender, amount, campaign
-- memo, and block time so the dashboard can show real-time revenue inflows.
--
-- This is the **incoming** revenue side. The payout engine
-- (empire_payouts.py / payout_log) handles the **outgoing** split side.
--
-- Migration is idempotent. Safe to run multiple times.
--
-- Usage:
--   psql "$SUPABASE_DB_URL" -f migrations/20260614_revenue_ledger.sql
--   or paste into Supabase SQL Editor.

-- ─────────────────────────────────────────────────────────────────────
-- empire_revenue_ledger: one row per verified on-chain USDC transfer
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS empire_revenue_ledger (
    transaction_signature TEXT PRIMARY KEY,          -- Solana tx signature
    sender_address       TEXT NOT NULL,              -- wallet that sent the USDC
    destination_address  TEXT NOT NULL,              -- Empire vault wallet
    usdc_amount          NUMERIC(20,6) NOT NULL,     -- USDC amount (6 decimals)
    tracking_memo        TEXT,                       -- campaign / lead link ID
    block_time_stamp     TIMESTAMP WITH TIME ZONE,   -- Solana block time
    logged_at            TIMESTAMP WITH TIME ZONE
                         DEFAULT TIMEZONE('utc'::text, NOW()),
    meta                 JSONB DEFAULT '{}'::jsonb   -- extra: slot, fee, etc.
);

-- Index for dashboard revenue rollups by campaign
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_memo
    ON empire_revenue_ledger (tracking_memo);

-- Index for time-series queries (daily/weekly/monthly aggregates)
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_block_time
    ON empire_revenue_ledger (block_time_stamp DESC);

-- Index for sender analytics (who is sending us money?)
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_sender
    ON empire_revenue_ledger (sender_address);
