-- Migration 028: add meta to agent_activity
ALTER TABLE public.agent_activity ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;
