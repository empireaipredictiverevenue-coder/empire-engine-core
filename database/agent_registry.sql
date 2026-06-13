-- =============================================================================
-- EMPIRE AI · AUTONOMOUS AGENT REGISTRY
-- =============================================================================
-- Tracks autonomous agent lifetimes and task execution paths for
-- billing, orchestration visibility, and cost attribution.
--
-- Tables also present in database/empire_suite_extension.sql (full suite migration).
-- This file is for standalone deployment when only agent tracking is needed.
-- =============================================================================

CREATE TABLE IF NOT EXISTS autonomous_agents (
    agent_id            TEXT PRIMARY KEY,
    agent_name          TEXT NOT NULL,
    assigned_niche      TEXT NOT NULL,  -- mass_tort, commercial_roofing, etc.
    current_status      TEXT DEFAULT 'IDLE',  -- IDLE, EXECUTING, CRASHED, SUCCESS
    total_tasks_completed INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_task_ledger (
    task_id             TEXT PRIMARY KEY,
    associated_agent_id TEXT NOT NULL,
    task_instruction    TEXT NOT NULL,
    execution_log       TEXT,
    step_count          INTEGER DEFAULT 1,
    billing_cost_units  REAL DEFAULT 0.0000,
    completed_at        TIMESTAMP,
    FOREIGN KEY (associated_agent_id) REFERENCES autonomous_agents(agent_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_status ON autonomous_agents(current_status);
CREATE INDEX IF NOT EXISTS idx_task_agent ON agent_task_ledger(associated_agent_id);
