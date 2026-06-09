-- Add billing columns to call_logs table
-- The table is created implicitly by Supabase on first insert,
-- so these columns may not exist. Using IF NOT EXISTS ensures idempotency.

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS is_billable   boolean DEFAULT false;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS fee_earned    numeric(12,2) DEFAULT 0.00;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS payout_value  numeric(12,2) DEFAULT 0.00;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS qualified     boolean DEFAULT false;

-- Index for billing queries
CREATE INDEX IF NOT EXISTS call_logs_billable_idx ON call_logs (is_billable) WHERE is_billable = true;
