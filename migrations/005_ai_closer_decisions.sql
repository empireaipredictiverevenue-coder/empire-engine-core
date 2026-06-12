-- ================================================================
-- EMPIRE V49 · AI CLOSER DECISIONS TABLE
-- Created: 2026-06-11
-- ================================================================
-- Stores every closer pipeline decision: BrainDecider scoring,
-- SI-evolved strategy selection, action taken (streaming call,
-- static call, nurture, no_go), and result summary.
--
-- Written by empire_ai_closer.AICloser._log_decision().
-- Read by the SPA / mission control for closer pipeline visibility.

CREATE TABLE IF NOT EXISTS ai_closer_decisions (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),

    -- Lead identity
    lead_name         text NOT NULL,
    lead_phone        text DEFAULT '',
    lead_email        text DEFAULT '',
    lead_address      text DEFAULT '',
    lead_city         text DEFAULT '',

    -- Niche classification (e.g. "Roofing Restoration", "Tornado Damage Repair")
    niche             text NOT NULL DEFAULT 'Roofing Restoration',

    -- BrainDecider output
    brain_decision    text NOT NULL DEFAULT 'NO_GO'
        CHECK (brain_decision IN ('GO', 'NO_GO')),
    brain_confidence  numeric(4,3) NOT NULL DEFAULT 0
        CHECK (brain_confidence >= 0 AND brain_confidence <= 1),
    brain_reasoning   text DEFAULT '',

    -- SI-evolved strategy selected by AGI Governor
    selected_strategy text NOT NULL DEFAULT 'AGGRESSIVE_STRIKE',

    -- Action taken
    action_taken      text NOT NULL DEFAULT 'no_go'
        CHECK (action_taken IN (
            'agi_stream_call', 'static_call', 'nurture', 'no_go',
            'compliance_blocked', 'no_phone'
        )),

    -- Full result payload (for debugging / analytics)
    result_summary    jsonb DEFAULT '{}'::jsonb
);

-- Lookups by lead for pipeline views
CREATE INDEX IF NOT EXISTS idx_ai_closer_decisions_lead
    ON ai_closer_decisions (lead_name, created_at DESC);

-- Lookups by niche for strategy evolution analytics
CREATE INDEX IF NOT EXISTS idx_ai_closer_decisions_niche
    ON ai_closer_decisions (niche, created_at DESC);

-- Lookups by brain decision for conversion rate analysis
CREATE INDEX IF NOT EXISTS idx_ai_closer_decisions_brain
    ON ai_closer_decisions (brain_decision, created_at DESC);

-- Lookups by action taken for funnel analytics
CREATE INDEX IF NOT EXISTS idx_ai_closer_decisions_action
    ON ai_closer_decisions (action_taken, created_at DESC);

-- Lookups by strategy for SI evolution feedback
CREATE INDEX IF NOT EXISTS idx_ai_closer_decisions_strategy
    ON ai_closer_decisions (selected_strategy);
