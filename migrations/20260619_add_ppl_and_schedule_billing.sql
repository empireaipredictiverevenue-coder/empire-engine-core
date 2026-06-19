-- Add Pay-Per-Lead (PPL) and Per-Schedule billing columns
-- PPL: buyer pays a flat fee per lead delivered (SMS/email from outreach)
-- Per-Schedule: buyer pays a flat fee per appointment scheduled
--
-- Run: python3 scripts/run_migrations.py
-- Or: psql -f migrations/20260619_add_ppl_and_schedule_billing.sql

ALTER TABLE buyers ADD COLUMN IF NOT EXISTS per_lead_rate numeric(6,2) DEFAULT NULL;
COMMENT ON COLUMN buyers.per_lead_rate IS 'Pay-per-lead rate. NULL = no PPL billing. Example: 5.00 = $5 per lead delivered.';

ALTER TABLE buyers ADD COLUMN IF NOT EXISTS per_schedule_rate numeric(6,2) DEFAULT NULL;
COMMENT ON COLUMN buyers.per_schedule_rate IS 'Pay-per-schedule rate. NULL = no per-schedule billing. Example: 15.00 = $15 per appointment scheduled.';

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS lead_fee numeric(12,2) DEFAULT 0.00;
COMMENT ON COLUMN call_logs.lead_fee IS 'Pay-per-lead fee computed at delivery time. 0.00 if no per_lead_rate set on buyer.';

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS schedule_fee numeric(12,2) DEFAULT 0.00;
COMMENT ON COLUMN call_logs.schedule_fee IS 'Per-schedule fee computed when appointment is booked. 0.00 if no per_schedule_rate set on buyer.';

CREATE INDEX IF NOT EXISTS call_logs_lead_fee_idx ON call_logs (lead_fee);
CREATE INDEX IF NOT EXISTS call_logs_schedule_fee_idx ON call_logs (schedule_fee);
