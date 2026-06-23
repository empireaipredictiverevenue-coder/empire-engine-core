-- Empire Pulse storm_trigger_log table
-- Used by empire_pulse._fan_out_storm_sms to dedupe storm alerts
CREATE TABLE IF NOT EXISTS storm_trigger_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city TEXT,
    state TEXT,
    niche TEXT,
    urgency_score INT,
    contractors_targeted INT DEFAULT 0,
    errors INT DEFAULT 0,
    fired_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_storm_trigger_dedupe
    ON storm_trigger_log (city, niche, fired_at DESC);