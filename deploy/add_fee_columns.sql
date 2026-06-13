-- EMPIRE V49 · Fee Model Migration
-- Adds monthly_retainer and per_call_fee columns to support:
--   Option 4: Monthly retainer + per-call fee model
--   Option 5: Tiered pricing per partner
--
-- Run this in the Supabase SQL Editor or via:
--   psql "$DATABASE_URL" -f deploy/add_fee_columns.sql

ALTER TABLE public.buyers 
  ADD COLUMN IF NOT EXISTS monthly_retainer numeric(12,2) NOT NULL DEFAULT 0;

ALTER TABLE public.buyers 
  ADD COLUMN IF NOT EXISTS per_call_fee numeric(12,2) NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.buyers.monthly_retainer IS 'Fixed monthly fee charged to partner (USD). 0 = no retainer.';
COMMENT ON COLUMN public.buyers.per_call_fee IS 'Flat per-call fee added on top of percentage fee (USD). 0 = no flat fee.';
COMMENT ON COLUMN public.buyers.fee_rate IS 'Percentage fee charged per-claim (default 0.03 = 3%, 0.05 = 5%).';

-- Verify columns were added
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'buyers'
  AND column_name IN ('monthly_retainer', 'per_call_fee', 'fee_rate')
ORDER BY column_name;
