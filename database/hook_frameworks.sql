-- =============================================================================
-- EMPIRE AI · HOOK & TRAINING FORMULA REGISTRY
-- =============================================================================
-- Logs core viral frameworks, records structural code formulas,
-- maps psychological triggers, and tracks real-time retention data scores.
--
-- Used by:
--   hook_analytics.py  — FastAPI microservice (port 8046)
--   scripts/deploy_hooks.sh  — Deployment + schema migration
-- =============================================================================

-- ── Viral Hook Formulas Registry ─────────────────────────────────────
-- Stores the core framework templates that score high on retention benchmarks.
CREATE TABLE IF NOT EXISTS viral_hook_formulas (
    formula_id                  TEXT PRIMARY KEY,
    formula_name                TEXT NOT NULL,                -- Contrarian Open, Identity Callout, Curiosity Gap
    verbal_template             TEXT NOT NULL,                -- The actual hook script template
    psychological_trigger       TEXT NOT NULL,                -- Cognitive Dissonance, Loss Aversion
    training_video_reference_url TEXT DEFAULT '',
    target_retention_benchmark  REAL DEFAULT 0.70,            -- 2026 standard requires >= 70% intro retention
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Incoming Trend Telemetry ─────────────────────────────────────────
-- Captures real-time hook patterns detected in the wild, scores their
-- velocity, and determines viability for paid campaign backing.
CREATE TABLE IF NOT EXISTS incoming_trend_telemetry (
    trend_id                    TEXT PRIMARY KEY,
    niche_category              TEXT NOT NULL,                -- mass_tort, roofing, financial
    hook_text_detected          TEXT NOT NULL,                -- The actual hook string observed
    sample_size_videos          INTEGER DEFAULT 0,            -- Number of videos observed with this pattern
    average_velocity_multiplier REAL DEFAULT 1.0,             -- View acceleration tracking
    trend_viability_score       REAL DEFAULT 0.0,             -- Final computed formula strength
    evaluated_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trend_telemetry_niche
    ON incoming_trend_telemetry (niche_category, evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_trend_telemetry_score
    ON incoming_trend_telemetry (trend_viability_score DESC);

-- ── Seed Core High-Intent Hook Frameworks ────────────────────────────
-- These are the master hook templates loaded on every migration.
INSERT OR IGNORE INTO viral_hook_formulas (formula_id, formula_name, verbal_template, psychological_trigger, target_retention_benchmark)
VALUES
    ('frm_001', 'Contrarian Statement',
     'Most operators are completely wrong about [Y commonly held belief]. Here is why.',
     'Cognitive Dissonance', 0.72),
    ('frm_002', 'Identity Callout',
     'If you are a [Specific Identity/ICP], stop scrolling right now.',
     'Self-Relevance Filtering', 0.75),
    ('frm_003', 'Curiosity Gap',
     'We generated [Specific Result] in 48 hours. The unexpected part is how we bypassed the networks.',
     'Zeigarnik Effect', 0.70);
