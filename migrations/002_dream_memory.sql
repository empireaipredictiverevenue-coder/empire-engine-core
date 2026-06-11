-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION: DREAM MEMORY TABLE
-- ============================================================================
-- Run this in the Supabase SQL Editor to create the table required by:
--   empire_dream.py  — DreamCollector, DreamProcessor, DreamMemory
-- ============================================================================

CREATE TABLE IF NOT EXISTS dream_memory (
    id                uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at        timestamptz DEFAULT now(),
    dream_cycle       int NOT NULL,
    sources_analyzed  jsonb DEFAULT '[]'::jsonb,
    sample_sizes      jsonb DEFAULT '{}'::jsonb,
    insights          jsonb DEFAULT '[]'::jsonb,
    rule_suggestions  jsonb DEFAULT '[]'::jsonb,
    wisdom_context    text DEFAULT '',
    narrative         text DEFAULT '',
    applied_rules     jsonb DEFAULT '[]'::jsonb,
    risk_flags        jsonb DEFAULT '[]'::jsonb,
    meta              jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dream_cycle ON dream_memory (dream_cycle DESC);
CREATE INDEX IF NOT EXISTS idx_dream_created ON dream_memory (created_at DESC);
