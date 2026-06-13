-- BRIDGE SESSIONS
-- Full-screen voice-first experience session log.
-- Each row represents one operator bridge session where the operator
-- interacts with the system via voice (Web Speech API or push-to-talk).

CREATE TABLE IF NOT EXISTS bridge_sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    ended_at        timestamptz,
    operator_id     uuid REFERENCES operators(id),
    duration_sec    int,
    actions_taken   int DEFAULT 0,
    commands_count  int DEFAULT 0,
    transcript      jsonb DEFAULT '[]'::jsonb,  -- ordered array of {role, text, timestamp}
    meta            jsonb DEFAULT '{}'::jsonb
);

-- Index for listing recent sessions
CREATE INDEX IF NOT EXISTS bridge_sessions_created_idx
    ON bridge_sessions (created_at DESC);

-- Index for active sessions (those without ended_at)
CREATE INDEX IF NOT EXISTS bridge_sessions_active_idx
    ON bridge_sessions (operator_id) WHERE ended_at IS NULL;
