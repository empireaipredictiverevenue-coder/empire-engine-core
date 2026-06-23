-- Migration: add meta jsonb column to sms_log
-- Required by tiered outreach system (hot/warm/cold lead routing)
-- Hot cap queries meta->>is_hot to count hot-lead SMS separately
ALTER TABLE sms_log ADD COLUMN IF NOT EXISTS meta jsonb DEFAULT '{}'::jsonb;

-- Index for hot cap queries (sms_log where meta->>is_hot = 'true')
CREATE INDEX IF NOT EXISTS idx_sms_log_meta_is_hot ON sms_log ((meta->>'is_hot')) WHERE meta->>'is_hot' = 'true';
