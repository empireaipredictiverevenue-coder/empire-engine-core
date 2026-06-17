-- =============================================================================
-- EMPIRE V49 · DDL MIGRATION 047: CRYPTO PAYMENT STATUS UPDATE
-- =============================================================================
-- Updates the CHECK constraint on crypto_payment_requests to include the new
-- status values introduced by the state machine refactor:
--   - activation_pending  (payment detected, subscription being activated)
--   - activation_failed   (payment received but subscription activation failed)
--
-- Also adds an index on the memo column for exact memo matching.
--
-- Run AFTER migration 046. Safe to re-run (idempotent).
-- =============================================================================

-- ── Update the CHECK constraint to include activation_pending and activation_failed ──
DO $$
BEGIN
    ALTER TABLE public.crypto_payment_requests
        DROP CONSTRAINT IF EXISTS crypto_payment_requests_status_check;

    ALTER TABLE public.crypto_payment_requests
        ADD CONSTRAINT crypto_payment_requests_status_check
        CHECK (status IN ('pending', 'partial', 'activation_pending', 'completed', 'expired', 'activation_failed', 'failed'));
END $$;

-- ── Index on memo for exact memo matching (the primary matching strategy) ──
CREATE INDEX IF NOT EXISTS crypto_pay_req_memo_idx
    ON public.crypto_payment_requests (memo)
    WHERE memo IS NOT NULL;
