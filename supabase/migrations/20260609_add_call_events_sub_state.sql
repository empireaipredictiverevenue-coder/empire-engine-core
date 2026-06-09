-- Add sub_state column to call_events for AMD detection sub_state (beep_start, beep_timeout)
ALTER TABLE call_events ADD COLUMN IF NOT EXISTS sub_state text;

-- Index for querying events by sub_state
CREATE INDEX IF NOT EXISTS call_events_sub_state_idx ON call_events (sub_state) WHERE sub_state IS NOT NULL;
