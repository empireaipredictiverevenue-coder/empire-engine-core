-- Empire Engine: Schema for Conversion Tracking and Call Logs

-- 1. Variants Table (Tracks different versions of the banner)
CREATE TABLE variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    copy TEXT NOT NULL,
    bg_color TEXT DEFAULT '#FFFF00',
    text_color TEXT DEFAULT '#FF0000',
    ctr_total BIGINT DEFAULT 0,
    calls_total BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Conversions Table (Tracks every visit/click)
CREATE TABLE conversions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id UUID REFERENCES variants(id),
    event_type TEXT NOT NULL, -- 'view' or 'click'
    visitor_ip TEXT,
    user_agent TEXT,
    referrer TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Lead Sources Table (For Affiliate Management)
CREATE TABLE lead_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    affiliate_name TEXT NOT NULL,
    unique_slug TEXT UNIQUE NOT NULL,
    calls_count BIGINT DEFAULT 0,
    total_payout DECIMAL(10, 2) DEFAULT 0.00
);

-- 4. Calls Table (Logs from Vonage Webhooks)
CREATE TABLE calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vonage_call_id TEXT UNIQUE,
    from_number TEXT,
    to_number TEXT,
    duration_seconds INTEGER,
    status TEXT,
    recording_url TEXT,
    lead_source_id UUID REFERENCES lead_sources(id),
    variant_id UUID REFERENCES variants(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert a default Control Variant
INSERT INTO variants (name, copy) VALUES ('Control V1', 'URGENT PLUMBING EMERGENCY? CALL NOW!');
