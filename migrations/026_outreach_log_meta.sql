-- Migration 026: add meta to outreach_log
ALTER TABLE public.outreach_log ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;
