-- 036_email_tracking.sql
-- Track email opens, clicks, bounces, complaints, and unsubscribes.
-- Used by the EmailSequenceEngine to power campaign analytics.

CREATE TABLE IF NOT EXISTS email_tracking (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    email           text NOT NULL,
    event           text NOT NULL CHECK (event IN ('open','click','bounce','complaint','unsubscribe')),
    sequence_id     uuid,
    sequence_type   text NOT NULL DEFAULT 'storm_strike',
    step            int NOT NULL DEFAULT 0,
    link_url        text,
    user_agent      text,
    ip_address      inet,
    meta            jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS email_tracking_email_idx
    ON email_tracking (email, created_at DESC);
CREATE INDEX IF NOT EXISTS email_tracking_event_idx
    ON email_tracking (event, created_at DESC);
CREATE INDEX IF NOT EXISTS email_tracking_sequence_idx
    ON email_tracking (sequence_id, sequence_type);
