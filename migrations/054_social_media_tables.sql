-- 054_social_media_tables.sql
-- Social Media Management tables for the Empire Social Agent
-- Creates: content_calendar, social_mentions, social_metrics, social_campaigns
-- Run: `python3 scripts/run_migrations.py`

-- ── Content Calendar ────────────────────────────────────────────────
-- Schedules content for publishing across all social platforms
CREATE TABLE IF NOT EXISTS content_calendar (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL CHECK (platform IN ('instagram', 'tiktok', 'linkedin', 'twitter', 'youtube', 'facebook')),
    content_type TEXT NOT NULL CHECK (content_type IN ('post', 'reel', 'story', 'video', 'shorts', 'tweet', 'article', 'carousel')),
    content JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'published', 'failed', 'cancelled')),
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    post_url TEXT,
    platform_post_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_calendar_status ON content_calendar(status);
CREATE INDEX IF NOT EXISTS idx_content_calendar_platform ON content_calendar(platform);
CREATE INDEX IF NOT EXISTS idx_content_calendar_scheduled ON content_calendar(scheduled_at) WHERE status = 'scheduled';

-- ── Social Mentions ─────────────────────────────────────────────────
-- Tracks mentions, comments, replies that need engagement
CREATE TABLE IF NOT EXISTS social_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL CHECK (platform IN ('instagram', 'tiktok', 'linkedin', 'twitter', 'youtube', 'facebook')),
    mention_type TEXT NOT NULL CHECK (mention_type IN ('comment', 'reply', 'mention', 'dm', 'tag')),
    author_handle TEXT NOT NULL,
    author_name TEXT,
    author_profile_url TEXT,
    text TEXT NOT NULL,
    platform_post_id TEXT,
    platform_comment_id TEXT,
    parent_comment_id UUID,
    sentiment TEXT CHECK (sentiment IN ('positive', 'negative', 'neutral', 'unclassified')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'replied', 'ignored', 'flagged')),
    response_text TEXT,
    replied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_social_mentions_status ON social_mentions(status);
CREATE INDEX IF NOT EXISTS idx_social_mentions_platform ON social_mentions(platform);
CREATE INDEX IF NOT EXISTS idx_social_mentions_created ON social_mentions(created_at DESC);

-- ── Social Media Metrics ────────────────────────────────────────────
-- Time-series metrics for growth tracking
CREATE TABLE IF NOT EXISTS social_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL CHECK (platform IN ('instagram', 'tiktok', 'linkedin', 'twitter', 'youtube', 'facebook')),
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    metadata JSONB DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_social_metrics_platform ON social_metrics(platform);
CREATE INDEX IF NOT EXISTS idx_social_metrics_metric ON social_metrics(metric);
CREATE INDEX IF NOT EXISTS idx_social_metrics_recorded ON social_metrics(recorded_at DESC);

-- ── Social Campaigns ────────────────────────────────────────────────
-- Marketing campaigns running on social platforms
CREATE TABLE IF NOT EXISTS social_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL CHECK (platform IN ('instagram', 'tiktok', 'linkedin', 'twitter', 'youtube', 'facebook')),
    name TEXT NOT NULL,
    objective TEXT NOT NULL CHECK (objective IN ('awareness', 'engagement', 'leads', 'sales', 'retention')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'running', 'paused', 'completed', 'cancelled')),
    config JSONB NOT NULL DEFAULT '{}',
    target_audience JSONB DEFAULT '{}',
    budget_cents INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    results JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_social_campaigns_status ON social_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_social_campaigns_platform ON social_campaigns(platform);
