-- =============================================================================
-- EMPIRE V49 · NICHE SOCIAL TERRAIN
-- =============================================================================
-- Tables for mapping where each niche's audience hangs out, tracking social
-- observations, and persisting learned habit traits. Used by the Predictive
-- Cloud to know where to be, when, and with what content.
-- =============================================================================

-- ── Social Observations ───────────────────────────────────────────────────
-- Records from monitoring social communities: what people are saying,
-- engagement levels, sentiment. Feeds the habit learning engine.
CREATE TABLE IF NOT EXISTS social_observations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    niche             TEXT NOT NULL,
    platform          TEXT NOT NULL,
    community_name    TEXT NOT NULL DEFAULT '',
    observation_type  TEXT NOT NULL DEFAULT 'mention',  -- mention, thread, comment, post, review
    content           TEXT DEFAULT '',
    engagement_count  INTEGER DEFAULT 0,
    sentiment         TEXT DEFAULT 'neutral',            -- positive, negative, neutral
    source_url        TEXT DEFAULT '',
    observed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_social_obs_niche_platform
    ON social_observations (niche, platform, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_obs_sentiment
    ON social_observations (niche, sentiment, observed_at DESC);

-- ── Niche Habit Traits ───────────────────────────────────────────────────
-- Learned behavioral patterns per niche: peak hours, content preferences,
-- sentiment baselines, decision cycles. Updated by the habit learning engine.
CREATE TABLE IF NOT EXISTS niche_habit_traits (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    niche             TEXT NOT NULL,
    trait_key         TEXT NOT NULL,
    trait_value       TEXT NOT NULL,   -- JSON string for complex values
    confidence        REAL DEFAULT 0.5,
    source            TEXT DEFAULT 'seed',  -- seed, observation, discovery
    learned_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(niche, trait_key)
);

CREATE INDEX IF NOT EXISTS idx_habit_traits_niche
    ON niche_habit_traits (niche, trait_key);
