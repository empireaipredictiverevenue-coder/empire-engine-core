-- OPERATOR PERSONALITY OVERRIDES
-- Per-operator personality preferences that override the global (niche-level) defaults.
-- Allows different operators to have their own decision-making style per niche.
-- Falls back: operator + niche → operator __global__ → brain_personality (global) → __global__ → default

CREATE TABLE IF NOT EXISTS operator_personality (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz,
    operator_id     uuid NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    niche           text NOT NULL DEFAULT '__global__',        -- '__global__' = default for this operator across all niches
    persona         text NOT NULL DEFAULT 'balanced'
        CHECK (persona IN ('conservative', 'aggressive', 'balanced')),
    confidence_threshold   numeric(4,3),                       -- nullable; NULL = use global/niche default
    urgency_floor          int,                                -- nullable
    temperature            numeric(4,3),                       -- nullable
    custom_prompt_suffix   text DEFAULT '',
    is_active              boolean DEFAULT true,
    UNIQUE (operator_id, niche)
);

CREATE INDEX IF NOT EXISTS operator_personality_operator_idx
    ON operator_personality (operator_id);

CREATE INDEX IF NOT EXISTS operator_personality_niche_idx
    ON operator_personality (niche);
