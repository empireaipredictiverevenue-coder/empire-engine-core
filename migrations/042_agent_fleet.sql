-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 042: AGENT FLEET — Role-Based Agent Management
-- ────────────────────────────────────────────────────────────────────────
-- Formal role definitions for the entire agent fleet. Every running agent
-- has a role with defined capabilities, parent hierarchy, and priority.
-- ────────────────────────────────────────────────────────────────────────

-- Agent roles — the canonical role definitions
CREATE TABLE IF NOT EXISTS agent_roles (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),

    role_name           text NOT NULL UNIQUE,         -- 'traffic_director', 'ppc_specialist', etc.
    display_name        text,                          -- 'Traffic Director', 'PPC Specialist'
    description         text,                          -- What this role does

    -- Hierarchy
    parent_role         text REFERENCES agent_roles(role_name),  -- parent for grouping
    priority            integer DEFAULT 5,             -- 1 (highest) to 10 (lowest)

    -- Capabilities (what this role can do)
    capabilities        jsonb DEFAULT '[]'::jsonb,     -- ["manage_ppc", "analyze_budgets", ...]

    -- Routing
    task_types          text[] DEFAULT '{}',           -- What task types this role handles
    source_module       text,                          -- Which .py file implements this role

    -- Health
    expected_interval_minutes integer DEFAULT 30,      -- Expected heartbeat interval
    auto_restart        boolean DEFAULT true,          -- Whether to auto-restart on failure

    -- Status
    is_active           boolean DEFAULT true,
    is_core             boolean DEFAULT false,         -- Core roles always run

    meta                jsonb DEFAULT '{}'::jsonb
);

-- Add role column to existing agent_registry if it exists
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'agent_registry') THEN
        ALTER TABLE agent_registry ADD COLUMN IF NOT EXISTS role_name text REFERENCES agent_roles(role_name);
        ALTER TABLE agent_registry ADD COLUMN IF NOT EXISTS capabilities jsonb DEFAULT '[]'::jsonb;
        ALTER TABLE agent_registry ADD COLUMN IF NOT EXISTS task_types text[] DEFAULT '{}';
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS agent_roles_parent_idx ON agent_roles (parent_role);
CREATE INDEX IF NOT EXISTS agent_roles_priority_idx ON agent_roles (priority, is_active);
CREATE INDEX IF NOT EXISTS agent_roles_capabilities_idx ON agent_roles USING gin (capabilities);

COMMENT ON TABLE agent_roles IS 'Canonical role definitions for the entire agent fleet';
