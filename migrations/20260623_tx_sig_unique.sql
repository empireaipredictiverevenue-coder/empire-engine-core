-- 20260623_tx_sig_unique.sql
-- Add UNIQUE constraint on transaction_signature so that
-- upserts via on_conflict='transaction_signature' work in:
--   empire_solana_webhook.py  (Helius webhook writes status='settled')
--   scripts/vault_watcher.py  (cron poll writes status='settled')
--
-- Without this, on_conflict silently becomes plain INSERT and
-- duplicate rows accumulate for the same on-chain transaction.

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
        -- Deduplicate existing rows before adding the constraint
        -- Keep the row with the most data (longest tracking_memo)
        DELETE FROM empire_revenue_ledger a
        USING empire_revenue_ledger b
        WHERE a.id > b.id
        AND a.transaction_signature = b.transaction_signature;

        ALTER TABLE empire_revenue_ledger
        ADD CONSTRAINT uq_revenue_ledger_tx_sig
        UNIQUE (transaction_signature);

        RAISE NOTICE 'Created UNIQUE constraint uq_revenue_ledger_tx_sig';
    ELSE
        RAISE NOTICE 'UNIQUE constraint uq_revenue_ledger_tx_sig already exists';
    END IF;
END $$;
