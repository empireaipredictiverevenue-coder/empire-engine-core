-- Add per-minute billing columns
-- Per-minute rate allows buyers to pay a per-minute fee alongside the
-- settlement fee (3%). The actual charge is the MAX of both.
--
-- Run: python3 scripts/run_migrations.py
-- Or: psql -f supabase/migrations/20260619_add_per_minute_billing.sql

ALTER TABLE buyers ADD COLUMN IF NOT EXISTS per_minute_rate numeric(6,2) DEFAULT NULL;
COMMENT ON COLUMN buyers.per_minute_rate IS 'Per-minute rate for pay-per-minute billing. NULL = settlement fee only. Example: 2.00 = $2/min.';

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS per_minute_fee numeric(12,2) DEFAULT 0.00;
COMMENT ON COLUMN call_logs.per_minute_fee IS 'Per-minute fee computed at billing time. 0.00 if no per_minute_rate set on buyer.';

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS settlement_fee numeric(12,2) DEFAULT 0.00;
COMMENT ON COLUMN call_logs.settlement_fee IS 'Settlement fee computed at billing time (payout * fee_rate). 0.00 if no buyer.';

-- Index for per-minute billing queries
CREATE INDEX IF NOT EXISTS call_logs_billing_type_idx ON call_logs (per_minute_fee, settlement_fee);
