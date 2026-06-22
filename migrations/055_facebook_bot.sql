-- 055_facebook_bot.sql
-- Facebook Messenger chatbot data persistence
-- Creates: facebook_conversations, facebook_leads
-- Run: `python3 scripts/run_migrations.py`

-- ── Facebook Conversations ──────────────────────────────────────────
-- Stores every message exchange between the Empire Facebook bot and
-- Facebook Page visitors. Used for conversation history, lead tracking,
-- and debugging.
CREATE TABLE IF NOT EXISTS facebook_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    psid TEXT NOT NULL,
    message TEXT NOT NULL,
    reply TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_facebook_conversations_psid ON facebook_conversations(psid);
CREATE INDEX IF NOT EXISTS idx_facebook_conversations_created ON facebook_conversations(created_at DESC);

-- ── Facebook Leads ──────────────────────────────────────────────────
-- Qualified leads captured from Facebook Messenger conversations.
-- Includes location, damage type, urgency, and contact info for routing
-- to contractor dispatch.
CREATE TABLE IF NOT EXISTS facebook_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    psid TEXT,
    name TEXT NOT NULL DEFAULT 'Facebook Lead',
    location TEXT NOT NULL DEFAULT '',
    damage_type TEXT NOT NULL DEFAULT '',
    urgency TEXT NOT NULL DEFAULT 'medium' CHECK (urgency IN ('high', 'medium', 'low')),
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    qualified BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL DEFAULT 'facebook_messenger',
    metadata JSONB DEFAULT '{}',
    dispatched BOOLEAN NOT NULL DEFAULT FALSE,
    dispatched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_facebook_leads_location ON facebook_leads(location);
CREATE INDEX IF NOT EXISTS idx_facebook_leads_qualified ON facebook_leads(qualified) WHERE qualified = TRUE;
CREATE INDEX IF NOT EXISTS idx_facebook_leads_created ON facebook_leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_facebook_leads_psid ON facebook_leads(psid);
