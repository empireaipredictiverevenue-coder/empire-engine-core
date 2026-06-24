-- Migration: media_pipeline_runs table for media-hub-orchestrator polling queue
-- Created 2026-06-24
-- The orchestrator polls this table for rows with status='pending'
-- and executes them via MediaOrchestrator.run_pipeline().

CREATE TABLE IF NOT EXISTS media_pipeline_runs (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL UNIQUE,          -- uuid, unique per pipeline run
    pipeline_name TEXT NOT NULL,              -- e.g. 'short-form', 'b2b-explainer'
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | running | ok | failed
    context     JSONB DEFAULT '{}',           -- input ctx for run_pipeline (topic, script, etc.)
    result      JSONB DEFAULT '{}',           -- pipeline output (populated on completion)
    error       TEXT,                         -- error message if failed
    stage_name  TEXT,                         -- current stage name (optional, for progress)
    claimed_by  TEXT,                         -- orchestrator instance that claimed it
    claimed_at  TIMESTAMPTZ,                  -- when the job was claimed
    created_at  TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    duration_ms FLOAT
);

CREATE INDEX IF NOT EXISTS idx_media_pipeline_runs_status
    ON media_pipeline_runs (status) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_media_pipeline_runs_created
    ON media_pipeline_runs (created_at);
