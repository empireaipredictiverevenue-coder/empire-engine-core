-- EMPIRE V49 · MIGRATION 059: VIDEO AUTOMATION JOBS
-- ====================================================
-- Queue table for the Buffy Buffer concurrency controller.
-- Manages the full lifecycle of video render jobs across the fleet.
--
-- Status state machine (managed by Buffy Buffer + render workers):
--   BUFFY_BUFFERED     → Buffy has queued this job (server capacity full)
--   RENDER_TRIGGERED   → Buffy has released it to a free render lane
--   PROCESSING         → Render worker has picked it up
--   QUALITY_APPROVED   → Quality gate passed (reserved for future quality agent)
--   QUALITY_FAILED     → Quality gate failed (reserved for future quality agent)
--   DONE               → Render completed successfully
--   FAILED             → Render failed with error
--
-- Concurrency limit: MAX_CONCURRENT_RENDERS = 3 (enforced by buffy_buffer.py)
-- Poll interval: 3 seconds (buffy_buffer.py) / 30 seconds (buffy_worker.py)

CREATE TABLE IF NOT EXISTS video_automation_jobs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Submission metadata
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    source            text NOT NULL DEFAULT 'cli',
        -- Source of the job: 'cron', 'cli', 'api', 'mesh'

    -- Render parameters
    topic             text NOT NULL DEFAULT '',
        -- Short description / hook for the video
    script_text       text NOT NULL DEFAULT '',
        -- The full script to render (auto-generated from topic if empty)
    voice_provider    text NOT NULL DEFAULT 'kokoro',
        -- TTS engine: 'kokoro' or 'deepgram'
    bg_video          text NOT NULL DEFAULT '',
        -- Background video path (empty = use default fallback)

    -- Output
    output_path       text NOT NULL DEFAULT '',
        -- Path to the rendered MP4 (set on completion)
    duration_s        numeric(6,1) DEFAULT 0.0,
    size_kb           int DEFAULT 0,

    -- State machine
    status            text NOT NULL DEFAULT 'RENDER_TRIGGERED'
        CHECK (status IN (
            'BUFFY_BUFFERED',
            'RENDER_TRIGGERED',
            'PROCESSING',
            'QUALITY_APPROVED',
            'QUALITY_FAILED',
            'DONE',
            'FAILED'
        )),
    priority          int NOT NULL DEFAULT 0,
        -- Higher = processed first (default 0, urgent = 10)
    error             text DEFAULT '',

    -- Timestamps
    buffered_at       timestamptz,
        -- When the job entered the buffer
    released_at       timestamptz,
        -- When Buffy released it from buffer
    started_at        timestamptz,
        -- When a worker began processing
    completed_at      timestamptz,

    -- Worker identity
    worker_id         text DEFAULT '',
        -- Which worker instance ran this job (e.g. 'buffy-worker-0')

    -- Heartbeat / stuck detection
    last_heartbeat    timestamptz
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_video_jobs_status      ON video_automation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_video_jobs_priority     ON video_automation_jobs(priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_video_jobs_created      ON video_automation_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_video_jobs_buffered     ON video_automation_jobs(status, created_at)
    WHERE status = 'BUFFY_BUFFERED';
CREATE INDEX IF NOT EXISTS idx_video_jobs_releasable   ON video_automation_jobs(status, priority DESC, created_at)
    WHERE status IN ('RENDER_TRIGGERED');
CREATE INDEX IF NOT EXISTS idx_video_jobs_processing   ON video_automation_jobs(status)
    WHERE status = 'PROCESSING';

-- Auto-update updated_at on row modification
CREATE OR REPLACE FUNCTION update_video_jobs_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_video_jobs_updated_at ON video_automation_jobs;
CREATE TRIGGER trg_video_jobs_updated_at
    BEFORE UPDATE ON video_automation_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_video_jobs_updated_at();
