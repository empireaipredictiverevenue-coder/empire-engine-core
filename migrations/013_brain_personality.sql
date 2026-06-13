-- BRAIN PERSONALITY
-- Operator-configurable persona per niche.
-- Each row defines a personality override for one niche (or global default).
-- The brain uses these profiles to adjust decision thresholds, prompt tone,
-- and LLM temperature per niche.

CREATE TABLE IF NOT EXISTS brain_personality (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz,
    niche           text NOT NULL DEFAULT '__global__',        -- '__global__' = default for all niches
    persona         text NOT NULL DEFAULT 'balanced'           -- 'conservative' | 'aggressive' | 'balanced'
        CHECK (persona IN ('conservative', 'aggressive', 'balanced')),
    confidence_threshold   numeric(4,3) DEFAULT 0.6,          -- minimum confidence for GO (0.0-1.0)
    urgency_floor          int DEFAULT 5,                      -- minimum urgency score (1-10)
    temperature            numeric(4,3) DEFAULT 0.1,           -- LLM temperature override (0.0-1.0)
    custom_prompt_suffix   text DEFAULT '',                     -- extra instructions appended to brain prompt
    operator_notes         text DEFAULT '',                     -- operator's rationale for this choice
    is_active              boolean DEFAULT true,
    UNIQUE (niche)
);

CREATE INDEX IF NOT EXISTS brain_personality_niche_idx
    ON brain_personality (niche);

-- OPERATOR PREFERENCE LOG
-- Records each time an operator changes a personality setting,
-- so the system can learn preferences over time.
CREATE TABLE IF NOT EXISTS operator_preference_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    operator_id     uuid REFERENCES operators(id),
    niche           text NOT NULL,
    field           text NOT NULL,          -- e.g. 'persona', 'confidence_threshold'
    old_value       text,
    new_value       text
);

CREATE INDEX IF NOT EXISTS operator_pref_log_created_idx
    ON operator_preference_log (created_at DESC);
