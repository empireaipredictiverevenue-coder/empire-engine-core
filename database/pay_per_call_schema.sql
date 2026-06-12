-- EMPIRE V49 · PAY-PER-CALL SCHEMA
-- ================================
-- High-intent inbound lead tracking tables for the PPC inbound engine.
-- Run against the local SQLite database:
--   sqlite3 /root/empire-v49/data/storm_alerts.sqlite < database/pay_per_call_schema.sql

CREATE TABLE IF NOT EXISTS call_logs (
    call_id TEXT PRIMARY KEY,
    visitor_session_id TEXT NOT NULL,
    incoming_phone_number TEXT NOT NULL,
    traffic_source TEXT NOT NULL,            -- google_search, facebook_ads, youtube_video
    ad_creative_id TEXT NOT NULL,
    captured_zip_code TEXT NOT NULL,
    niche_category TEXT NOT NULL,             -- roofing, mass_tort
    sub_niche_vertical TEXT NOT NULL DEFAULT 'general',
    assigned_buyer_id TEXT DEFAULT 'aggregator_pool',
    call_duration_seconds INTEGER DEFAULT 0,
    payout_triggered INTEGER DEFAULT 0,      -- 0 = False, 1 = True
    revenue_generated REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_profiles (
    profile_id TEXT PRIMARY KEY,
    associated_call_id TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    niche_category TEXT NOT NULL,
    lead_retention_data TEXT NOT NULL,        -- PII, structured context variables
    monetization_cycle_count INTEGER DEFAULT 0,
    last_sms_blast_time TIMESTAMP,
    FOREIGN KEY(associated_call_id) REFERENCES call_logs(call_id)
);

CREATE INDEX IF NOT EXISTS idx_call_logs_phone ON call_logs(incoming_phone_number);
CREATE INDEX IF NOT EXISTS idx_call_logs_niche ON call_logs(niche_category, sub_niche_vertical);
CREATE INDEX IF NOT EXISTS idx_customer_profiles_phone ON customer_profiles(phone_number);
