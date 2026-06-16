-- Add voice-call outcome tracking to contractors
-- 2026-06-16: tracks the outcome of AI voice calls placed by
-- contractor_outreach agent. Without this, we have no visibility
-- into whether the voice lane produces anything.

ALTER TABLE contractors
  ADD COLUMN IF NOT EXISTS voice_outcome text,
  ADD COLUMN IF NOT EXISTS last_voice_call_at timestamptz,
  ADD COLUMN IF NOT EXISTS voice_call_count int DEFAULT 0;

-- voice_outcome values:
--   'no_answer'  — phone rang, no human
--   'voicemail'  — went to voicemail
--   'talked'     — human answered
--   'signed_up'  — contractor onboarded
--   'opted_out'   — pressed 9 / said stop
--   'callback'   — asked us to call back later

COMMENT ON COLUMN contractors.voice_outcome IS
  'Outcome of the most recent AI voice call placed to this contractor. See agents/contractor_outreach/outreach.py';
COMMENT ON COLUMN contractors.last_voice_call_at IS
  'Timestamp of the most recent placed voice call. Set by the dialer.';
COMMENT ON COLUMN contractors.voice_call_count IS
  'Total voice calls placed to this contractor. Used to detect over-dialing.';
