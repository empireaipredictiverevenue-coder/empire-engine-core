-- ═══════════════════════════════════════════════════════════════════════════
-- EMPIRE V49 · HERMES PROTOCOL · AGENT TASK QUEUE
-- ═══════════════════════════════════════════════════════════════════════════
-- Idempotent · safe to re-run (uses IF NOT EXISTS everywhere).
-- ═══════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────
-- AGENT TASK QUEUE
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.agent_task_queue (
    ticket_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    task_type       text NOT NULL,
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
    status          text NOT NULL DEFAULT 'To-Do'
        CHECK (status IN ('To-Do', 'In Progress', 'Blocked', 'Done', 'Failed', 'Cancelled')),
    assigned_agent  text,
    priority        int NOT NULL DEFAULT 0,
    started_at      timestamptz,
    completed_at    timestamptz,
    result          jsonb DEFAULT '{}'::jsonb,
    error           text
);

-- Indexes for queue operations
CREATE INDEX IF NOT EXISTS idx_agent_task_queue_status
    ON public.agent_task_queue (status, priority DESC, created_at ASC)
    WHERE status = 'To-Do';
CREATE INDEX IF NOT EXISTS idx_agent_task_queue_type_status
    ON public.agent_task_queue (task_type, status)
    WHERE status IN ('To-Do', 'In Progress', 'Blocked');
CREATE INDEX IF NOT EXISTS idx_agent_task_queue_assigned
    ON public.agent_task_queue (assigned_agent, status)
    WHERE assigned_agent IS NOT NULL;

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_agent_task_queue_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_task_queue_updated_at ON public.agent_task_queue;
CREATE TRIGGER trg_agent_task_queue_updated_at
    BEFORE UPDATE ON public.agent_task_queue
    FOR EACH ROW
    EXECUTE FUNCTION public.update_agent_task_queue_updated_at();

COMMENT ON TABLE public.agent_task_queue IS 'Kanban task queue for the Hermes Protocol agent mesh';
COMMENT ON COLUMN public.agent_task_queue.task_type IS 'Task type identifier (scout.find_roofs, outreach.draft_email, studio.write_script, studio.render_reel, revenue.connect_buyer, revenue.score_call)';
COMMENT ON COLUMN public.agent_task_queue.status IS 'Kanban status: To-Do, In Progress, Blocked, Done, Failed, Cancelled';
COMMENT ON COLUMN public.agent_task_queue.priority IS 'Higher = more urgent (negative = low priority, 0 = normal, 5+ = urgent)';
COMMENT ON COLUMN public.agent_task_queue.assigned_agent IS 'Agent currently working this ticket or name of agent that should claim it';


-- ─────────────────────────────────────────────────────────────────────
-- ENHANCE AGENT REGISTRY (add capabilities column if missing)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE IF EXISTS public.agent_registry
    ADD COLUMN IF NOT EXISTS capabilities jsonb DEFAULT '[]'::jsonb;
ALTER TABLE IF EXISTS public.agent_registry
    ADD COLUMN IF NOT EXISTS task_types text[] DEFAULT '{}';
ALTER TABLE IF EXISTS public.agent_registry
    ADD COLUMN IF NOT EXISTS metrics jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.agent_registry.capabilities IS 'Array of capability tags (e.g. ["scout","outreach","copywriter","render","dispatcher","quality"])';
COMMENT ON COLUMN public.agent_registry.task_types IS 'Array of task_type patterns this agent can handle';
COMMENT ON COLUMN public.agent_registry.metrics IS 'Agent performance metrics (tasks_completed, avg_completion_time, success_rate)';


-- ─────────────────────────────────────────────────────────────────────
-- HELPER RPC: claim_next_task
-- ─────────────────────────────────────────────────────────────────────
-- Atomically claim the highest-priority 'To-Do' task matching the given
-- task_types for an agent. Uses a lock to prevent double-claim.
CREATE OR REPLACE FUNCTION public.claim_next_task(
    p_agent_name text,
    p_task_types text[]
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_ticket public.agent_task_queue%ROWTYPE;
    v_result jsonb;
BEGIN
    -- Take the highest-priority, oldest To-Do task that matches task_types
    SELECT * INTO v_ticket
    FROM public.agent_task_queue
    WHERE status = 'To-Do'
      AND (p_task_types IS NULL OR task_type = ANY(p_task_types))
    ORDER BY priority DESC, created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF v_ticket.ticket_id IS NULL THEN
        RETURN NULL;
    END IF;

    -- Claim it
    UPDATE public.agent_task_queue
    SET status = 'In Progress',
        assigned_agent = p_agent_name,
        started_at = now()
    WHERE ticket_id = v_ticket.ticket_id;

    -- Build result
    SELECT jsonb_build_object(
        'ticket_id', v_ticket.ticket_id,
        'task_type', v_ticket.task_type,
        'payload', v_ticket.payload,
        'priority', v_ticket.priority,
        'created_at', v_ticket.created_at
    ) INTO v_result;

    RETURN v_result;
END;
$$;

COMMENT ON FUNCTION public.claim_next_task IS 'Atomically claim next available task for an agent. Returns the task or null if none available.';


-- ─────────────────────────────────────────────────────────────────────
-- HELPER RPC: complete_task
-- ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.complete_task(
    p_ticket_id uuid,
    p_result jsonb DEFAULT '{}'::jsonb,
    p_error text DEFAULT NULL
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.agent_task_queue
    SET status = CASE WHEN p_error IS NOT NULL THEN 'Failed' ELSE 'Done' END,
        result = p_result,
        error = p_error,
        completed_at = now()
    WHERE ticket_id = p_ticket_id;

    RETURN FOUND;
END;
$$;

COMMENT ON FUNCTION public.complete_task IS 'Mark a task as Done or Failed with result/error data.';


-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFY
-- ═══════════════════════════════════════════════════════════════════════════
-- SELECT count(*) FROM information_schema.tables WHERE table_name = 'agent_task_queue';
-- ═══════════════════════════════════════════════════════════════════════════
