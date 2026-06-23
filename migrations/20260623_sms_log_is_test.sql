-- Add is_test column for filtering 555 sandbox responses
ALTER TABLE sms_log ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_sms_log_is_test ON sms_log (is_test, created_at DESC);