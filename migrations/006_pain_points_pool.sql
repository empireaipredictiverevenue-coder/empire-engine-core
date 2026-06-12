-- ================================================================
-- EMPIRE V49 · PAIN POINTS POOL TABLE + AI CLOSER DECISIONS COLUMN
-- Created: 2026-06-12
-- ================================================================
-- pain_points_pool: tracks pain point effectiveness per niche.
-- Written by empire_pain_points.PainPointLibrary._persist_outcome().
-- Read by the SPA Pain Points tab for analytics.
--
-- Also adds pain_points_used column to ai_closer_decisions
-- (idempotent — uses ADD COLUMN IF NOT EXISTS pattern).

-- 1. Pain points pool (niche × pain_point_id = compound key)
CREATE TABLE IF NOT EXISTS pain_points_pool (
    niche             text NOT NULL,
    pain_point_id     text NOT NULL,
    label             text NOT NULL DEFAULT '',
    weight            numeric(4,3) NOT NULL DEFAULT 0.500
        CHECK (weight >= 0 AND weight <= 1),
    attempts          integer NOT NULL DEFAULT 0,
    successes         integer NOT NULL DEFAULT 0,
    last_success_ts   timestamptz,
    updated_at        timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (niche, pain_point_id)
);

-- Lookup all pain points for a niche ordered by effectiveness
CREATE INDEX IF NOT EXISTS idx_pain_points_niche_weight
    ON pain_points_pool (niche, weight DESC);

-- 2. Add pain_points_used column to ai_closer_decisions (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'ai_closer_decisions' AND column_name = 'pain_points_used'
    ) THEN
        ALTER TABLE ai_closer_decisions
        ADD COLUMN pain_points_used text[] DEFAULT '{}'::text[];
    END IF;
END $$;

-- Index for querying which pain points were used
CREATE INDEX IF NOT EXISTS idx_ai_closer_decisions_pain_points
    ON ai_closer_decisions USING gin (pain_points_used);
