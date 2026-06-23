-- Empire AI · Revenue Ledger — Status Column
-- ===============================
-- Adds a `status` column to empire_revenue_ledger so every row is clearly
-- marked as either:
--
--   'accrued'  — recorded bookkeeping entry, not yet settled on-chain
--                 (sync_revenue_ledger, track_infra_costs, manual entries)
--   'settled'  — confirmed on-chain USDC transaction
--                 (Solana webhook via empire_solana_webhook.py)
--
-- This prevents the operator from confusing book entries with actual
-- blockchain settlements.
--
-- Usage:
--   psql "$SUPABASE_DB_URL" -f migrations/20260623_ledger_status.sql

-- 1. Add status column with CHECK constraint
ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS status TEXT
    DEFAULT 'accrued'
    CHECK (status IN ('accrued', 'settled'));

-- 2. Backfill: all existing rows without a transaction_signature
--    or with system sender are accrued (book entries)
UPDATE empire_revenue_ledger
    SET status = 'accrued'
    WHERE status IS NULL;

-- 3. Index for fast status filtering
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_status
    ON empire_revenue_ledger (status);

-- 4. Composite index for status + logged_at (daily reports)
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_status_logged
    ON empire_revenue_ledger (status, logged_at DESC);

-- Add UNIQUE constraint on transaction_signature so that on_conflict
-- upserts work correctly in empire_solana_webhook.py and vault_watcher.py.
-- Without this, upserts silently become inserts and duplicates accumulate.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class rel ON con.conrelid = rel.oid
        JOIN pg_namespace nsp ON rel.relnamespace = nsp.oid
        WHERE nsp.nspname = 'public'
        AND rel.relname = 'empire_revenue_ledger'
        AND con.conname = 'uq_revenue_ledger_tx_sig'
    ) THEN
        ALTER TABLE empire_revenue_ledger
        ADD CONSTRAINT uq_revenue_ledger_tx_sig UNIQUE (transaction_signature);
        RAISE NOTICE 'Created UNIQUE constraint uq_revenue_ledger_tx_sig';
    ELSE
        RAISE NOTICE 'UNIQUE constraint uq_revenue_ledger_tx_sig already exists';
    END IF;
END $$;
