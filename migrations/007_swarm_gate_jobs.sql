-- EMPIRE V49 · MIGRATION 007: SWARM GATE JOBS
-- Table for Swarm Gate job results — one row per processed lane.
-- Tracks the full pipeline: Script Engine → Kokoro TTS → FFmpeg 1080x1920 render.

CREATE TABLE IF NOT EXISTS swarm_gate_jobs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),

    -- Target identification
    target_id         uuid,
    warehouse_name    text NOT NULL DEFAULT '',
    metro             text NOT NULL DEFAULT '',
    niche             text NOT NULL DEFAULT '',

    -- Storm context
    risk_level        text DEFAULT '',

    -- Script Engine
    brain_decision    text DEFAULT '',
    brain_confidence  numeric(4,3) DEFAULT 0.0 CHECK (brain_confidence >= 0 AND brain_confidence <= 1),
    strategy          text DEFAULT '',
    script            text DEFAULT '',

    -- Kokoro Audio
    audio_path        text DEFAULT '',
    audio_duration_s  numeric(6,1) DEFAULT 0.0,

    -- FFmpeg Render
    video_path        text DEFAULT '',
    video_status      text DEFAULT '',

    -- Meta
    status            text NOT NULL DEFAULT 'queued',
    error             text DEFAULT '',
    started_at        timestamptz,
    completed_at      timestamptz,

    CHECK (status IN ('queued','scripting','audio','rendering','complete','failed'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_swarm_gate_jobs_target ON swarm_gate_jobs(target_id);
CREATE INDEX IF NOT EXISTS idx_swarm_gate_jobs_niche ON swarm_gate_jobs(niche);
CREATE INDEX IF NOT EXISTS idx_swarm_gate_jobs_status ON swarm_gate_jobs(status);
CREATE INDEX IF NOT EXISTS idx_swarm_gate_jobs_metro ON swarm_gate_jobs(metro);
CREATE INDEX IF NOT EXISTS idx_swarm_gate_jobs_created ON swarm_gate_jobs(created_at DESC);
