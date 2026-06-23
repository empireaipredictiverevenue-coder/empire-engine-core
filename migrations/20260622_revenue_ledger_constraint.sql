-- Empire AI · Revenue Ledger: Fix upsert constraint
-- ===================================================
-- PostgREST's on_conflict requires a proper UNIQUE constraint (not just a
-- unique index) on (source_type, source_id) for upserts to work.
--
-- A UNIQUE constraint in PostgreSQL allows multiple NULLs (NULL != NULL),
-- so existing Solana entries with NULL source_type/source_id are unaffected.
--
-- Idempotent: safe to run multiple times.

-- ─────────────────────────────────────────────────────────────────────
-- 1. Drop the partial unique index (replaced by constraint below)
-- ─────────────────────────────────────────────────────────────────────
DROP INDEX IF EXISTS idx_revenue_ledger_source_unique;

-- ─────────────────────────────────────────────────────────────────────
-- 2. Backfill source_type for existing Solana entries
--    (so future syncs can use (source_type, source_id) dedup)
-- ─────────────────────────────────────────────────────────────────────
UPDATE empire_revenue_ledger
SET
    source_type = COALESCE(source_type, 'solana'),
    description = COALESCE(description, 'Solana USDC payment')
WHERE source_type IS NULL;

UPDATE empire_revenue_ledger
SET amount = COALESCE(amount, usdc_amount)
WHERE amount IS NULL AND usdc_amount IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────
-- 3. Add UNIQUE constraint on (source_type, source_id)
--    PostgREST detects this for ?on_conflict=source_type,source_id
--    NULLs are allowed (PostgreSQL treats NULL != NULL in UNIQUE)
-- ─────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'empire_revenue_ledger'
        AND constraint_type = 'UNIQUE'
        AND constraint_name = 'empire_revenue_ledger_source_unique'
    ) THEN
        ALTER TABLE empire_revenue_ledger
            ADD CONSTRAINT empire_revenue_ledger_source_unique
            UNIQUE (source_type, source_id);
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────
-- 4. Recreate supporting index on source_type for filtered queries
-- ─────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_source_type
    ON empire_revenue_ledger (source_type);
