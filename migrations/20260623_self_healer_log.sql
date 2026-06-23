-- Empire self_healer_log table
-- Used by agents/self_healer.py to log every fix attempt (pm2 restart,
-- agent re-run, ollama kill, etc.) so the supervisor + telegram digest
-- can see what changed.
CREATE TABLE IF NOT EXISTS self_healer_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action TEXT NOT NULL,
    target TEXT,
    status TEXT NOT NULL,
    detail TEXT,
    fired_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_self_healer_dedupe
    ON self_healer_log (action, target, fired_at DESC);