-- EMPIRE V49 · MIGRATION 060: CLAIM VIDEO RENDER JOB RPC
-- ======================================================
-- Atomic job claiming for the Buffy Worker. Prevents race conditions
-- when multiple worker instances poll for the same RENDER_TRIGGERED job.
--
-- Called by buffy_worker.py:
--     sb.rpc("claim_video_render_job", {"p_worker_id": WORKER_ID}).execute()
--
-- Returns the full job row on success, empty set if no jobs available.

CREATE OR REPLACE FUNCTION claim_video_render_job(p_worker_id text)
RETURNS SETOF video_automation_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    claimed_job video_automation_jobs;
BEGIN
    WITH candidate AS (
        SELECT id
        FROM video_automation_jobs
        WHERE status = 'RENDER_TRIGGERED'
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE video_automation_jobs AS j
    SET
        status         = 'PROCESSING',
        worker_id      = p_worker_id,
        started_at     = now(),
        last_heartbeat = now(),
        updated_at     = now()
    FROM candidate
    WHERE j.id = candidate.id
    RETURNING j.*
    INTO claimed_job;

    IF claimed_job.id IS NOT NULL THEN
        RETURN NEXT claimed_job;
    END IF;

    RETURN;
END;
$$;
