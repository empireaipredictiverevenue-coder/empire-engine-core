-- ────────────────────────────────────────────────────────────────────────
-- MIGRATION 038: NATIVE ADS NETWORK
-- ────────────────────────────────────────────────────────────────────────
-- Full native ads serving system: campaigns, creatives, ad slots,
-- impression/click tracking, and publisher payouts.
-- ────────────────────────────────────────────────────────────────────────

-- Ad campaigns — one per advertiser per niche
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Identity
    name                text NOT NULL,
    advertiser_id       uuid,                    -- references affiliate/operator
    niche               text NOT NULL,           -- e.g. "Roofing Restoration", "HVAC"

    -- Budget & pacing
    daily_budget        numeric(10,2) DEFAULT 100.00,  -- USD per day
    total_budget        numeric(10,2),                 -- lifetime cap (null = unlimited)
    spent_today         numeric(10,2) DEFAULT 0.00,
    spent_total         numeric(10,2) DEFAULT 0.00,

    -- Targeting
    target_metros       text[] DEFAULT '{}',     -- metro areas to target
    target_url          text,                     -- where the ad points to
    target_specialties  text[] DEFAULT '{}',      -- contractor specialties

    -- Status
    status              text NOT NULL DEFAULT 'paused'
        CHECK (status IN ('active', 'paused', 'ended', 'archived')),
    start_at            timestamptz,
    end_at              timestamptz,

    -- Meta
    notes               text,
    meta                jsonb DEFAULT '{}'::jsonb
);

-- Ad creatives — the actual ad content
CREATE TABLE IF NOT EXISTS ad_creatives (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    campaign_id         uuid NOT NULL REFERENCES ad_campaigns(id) ON DELETE CASCADE,

    -- Content
    headline            text NOT NULL,           -- Max 80 chars
    body                text NOT NULL,           -- Max 200 chars
    image_url           text,
    cta_text            text DEFAULT 'Learn More',
    destination_url     text NOT NULL,           -- Where click goes

    -- Display
    ad_size             text DEFAULT '300x250',  -- Pixels (width x height)
    ad_format           text DEFAULT 'native'
        CHECK (ad_format IN ('native', 'banner', 'skyscraper', 'video')),

    -- Performance (updated by tracking)
    impressions         bigint DEFAULT 0,
    clicks              bigint DEFAULT 0,
    conversions         bigint DEFAULT 0,
    spend               numeric(10,2) DEFAULT 0.00,

    -- Status
    status              text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'rejected')),

    meta                jsonb DEFAULT '{}'::jsonb
);

-- Ad slots — publisher placements where ads can appear
CREATE TABLE IF NOT EXISTS ad_slots (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),

    -- Publisher identity
    publisher_id        text NOT NULL,           -- e.g. "empire-ai-splash", "contractor-portal"
    publisher_name      text,                    -- display name
    slot_name           text NOT NULL,           -- e.g. "sidebar-top", "content-mid"

    -- Slot configuration
    ad_size             text DEFAULT '300x250',
    ad_format           text DEFAULT 'native',
    niches              text[] DEFAULT '{}',     -- which niches this slot targets
    is_active           boolean DEFAULT true,

    -- Revenue share
    revenue_share_pct   numeric(5,2) DEFAULT 70.00, -- publisher gets 70%

    meta                jsonb DEFAULT '{}'::jsonb,
    UNIQUE (publisher_id, slot_name)
);

-- Impression tracking
CREATE TABLE IF NOT EXISTS ad_impressions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    creative_id         uuid NOT NULL REFERENCES ad_creatives(id),
    campaign_id         uuid NOT NULL REFERENCES ad_campaigns(id),
    slot_id             uuid REFERENCES ad_slots(id),

    -- Session/visitor
    visitor_id          text,                    -- anonymous fingerprint
    ip_hash             text,                    -- hashed IP for frequency capping
    user_agent          text,
    referrer            text,

    -- Cost
    cost_per_impression numeric(8,6) DEFAULT 0.001,  -- CPM cost
    revenue_share_pct   numeric(5,2) DEFAULT 70.00
);

-- Click tracking
CREATE TABLE IF NOT EXISTS ad_clicks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    impression_id       uuid REFERENCES ad_impressions(id),
    creative_id         uuid NOT NULL REFERENCES ad_creatives(id),
    campaign_id         uuid NOT NULL REFERENCES ad_campaigns(id),

    visitor_id          text,
    ip_hash             text,
    user_agent          text,
    referrer            text,

    -- Conversion tracking
    converted           boolean DEFAULT false,
    conversion_value    numeric(10,2),
    converted_at        timestamptz
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS ad_campaigns_status_idx ON ad_campaigns (status, niche);
CREATE INDEX IF NOT EXISTS ad_creatives_campaign_idx ON ad_creatives (campaign_id);
CREATE INDEX IF NOT EXISTS ad_impressions_creative_idx ON ad_impressions (creative_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ad_clicks_campaign_idx ON ad_clicks (campaign_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ad_slots_publisher_idx ON ad_slots (publisher_id, is_active);

-- Auto-update updated_at on ad_campaigns
CREATE OR REPLACE FUNCTION _ad_campaigns_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ad_campaigns_updated_at ON ad_campaigns;
CREATE TRIGGER ad_campaigns_updated_at
    BEFORE UPDATE ON ad_campaigns
    FOR EACH ROW EXECUTE FUNCTION _ad_campaigns_updated_at();

COMMENT ON TABLE ad_campaigns IS 'Native ad campaigns — one per advertiser per niche';
COMMENT ON TABLE ad_creatives IS 'Ad creatives — the actual ad content displayed to users';
COMMENT ON TABLE ad_slots IS 'Publisher placements — where ads can appear';
COMMENT ON TABLE ad_impressions IS 'Every time an ad is served to a visitor';
COMMENT ON TABLE ad_clicks IS 'Every click on a served ad';
