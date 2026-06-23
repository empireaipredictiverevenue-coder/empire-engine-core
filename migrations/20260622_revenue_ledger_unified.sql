-- Empire AI · Unified Revenue Ledger
-- ===================================
-- Extends empire_revenue_ledger to track ALL revenue sources in one table:
--   - Solana USDC on-chain payments (existing)
--   - fee_events (settled-claim fees)
--   - call_logs (call revenue)
--
-- Migration is idempotent. Safe to run multiple times.
--
-- Usage:
--   psql "$SUPABASE_DB_URL" -f migrations/20260622_revenue_ledger_unified.sql
--   or paste into Supabase SQL Editor.

-- ─────────────────────────────────────────────────────────────────────
-- 1. Add unified columns to empire_revenue_ledger
-- ─────────────────────────────────────────────────────────────────────

-- Add UUID primary key (existing rows get auto-assigned)
ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS id uuid DEFAULT gen_random_uuid();
-- Make id the primary key — drop existing PK first if transaction_signature is PK
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'empire_revenue_ledger'
        AND constraint_type = 'PRIMARY KEY'
        AND constraint_name = 'empire_revenue_ledger_pkey'
    ) THEN
        ALTER TABLE empire_revenue_ledger DROP CONSTRAINT empire_revenue_ledger_pkey;
    END IF;
END $$;
-- Re-add as a constraint on id
ALTER TABLE empire_revenue_ledger
    ADD CONSTRAINT empire_revenue_ledger_pkey PRIMARY KEY (id);

-- Allow NULL transaction_signature (only solana entries have one)
ALTER TABLE empire_revenue_ledger
    ALTER COLUMN transaction_signature DROP NOT NULL;

-- Add source tracking columns
ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS source_type text;  -- 'solana', 'fee_event', 'call_log'
ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS source_id text;    -- UUID or ID in the source table

-- Unified amount column (USDC for solana, fee_amount for fee_events, fee_earned for call_logs)
ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS amount numeric(20,6);

-- Human-readable description
ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS description text;

-- Add indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_source_type
    ON empire_revenue_ledger (source_type);
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_source_id
    ON empire_revenue_ledger (source_id);
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_amount
    ON empire_revenue_ledger (amount DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_revenue_ledger_source_unique
    ON empire_revenue_ledger (source_type, source_id)
    WHERE source_type IS NOT NULL AND source_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────
-- 2. Backfill amounts for existing Solana entries
--    (copy usdc_amount → amount where amount is null)
-- ─────────────────────────────────────────────────────────────────────
UPDATE empire_revenue_ledger
SET
    amount = usdc_amount,
    source_type = COALESCE(source_type, 'solana'),
    description = COALESCE(description, 'Solana USDC payment')
WHERE amount IS NULL AND usdc_amount IS NOT NULL;
