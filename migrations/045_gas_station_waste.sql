-- 045_gas_station_waste.sql
-- Gas Station Waste Detection — Discovery + Enrichment + Outreach
--
-- Tables:
--   gas_station_compounds  — discovered gas stations with waste scores
--   gas_station_enriched   — enriched stations with business identity + 3-model scores
--   gas_station_outreach   — outreach attempts per station/channel/business model

CREATE TABLE IF NOT EXISTS gas_station_compounds (
    station_id TEXT PRIMARY KEY,
    name TEXT,
    brand TEXT,
    operator TEXT,
    address TEXT,
    city TEXT,
    state TEXT DEFAULT 'TX',
    metro TEXT,
    lat FLOAT8,
    lon FLOAT8,
    station_type TEXT,               -- active_station, truck_stop, abandoned_station, station_with_shop
    pump_count_est INTEGER DEFAULT 0,
    area_sq_meters FLOAT8 DEFAULT 0,
    has_shop BOOLEAN DEFAULT FALSE,
    has_car_wash BOOLEAN DEFAULT FALSE,
    is_truck_stop BOOLEAN DEFAULT FALSE,
    is_abandoned BOOLEAN DEFAULT FALSE,
    waste_score FLOAT8 DEFAULT 0.0,  -- 0-1 overall waste probability
    waste_indicators JSONB DEFAULT '[]'::jsonb,
    source TEXT DEFAULT 'osm_overpass',
    last_scanned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_gas_station_compounds_metro
    ON gas_station_compounds(metro);
CREATE INDEX IF NOT EXISTS idx_gas_station_compounds_waste_score
    ON gas_station_compounds(waste_score DESC);
CREATE INDEX IF NOT EXISTS idx_gas_station_compounds_abandoned
    ON gas_station_compounds(is_abandoned);

CREATE TABLE IF NOT EXISTS gas_station_enriched (
    station_id TEXT PRIMARY KEY REFERENCES gas_station_compounds(station_id),
    business_name TEXT,
    brand TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    fuel_types TEXT,
    lead_gen_score FLOAT8 DEFAULT 0.0,
    consulting_score FLOAT8 DEFAULT 0.0,
    marketplace_score FLOAT8 DEFAULT 0.0,
    best_model TEXT,
    enrichment_source TEXT DEFAULT 'osm_metadata',
    enrichment_confidence FLOAT8 DEFAULT 0.0,
    status TEXT DEFAULT 'enriched',
    enriched_at TIMESTAMPTZ DEFAULT NOW(),
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_gas_station_enriched_best_model
    ON gas_station_enriched(best_model);
CREATE INDEX IF NOT EXISTS idx_gas_station_enriched_lead_gen_score
    ON gas_station_enriched(lead_gen_score DESC);

CREATE TABLE IF NOT EXISTS gas_station_outreach (
    station_id TEXT REFERENCES gas_station_compounds(station_id),
    channel TEXT NOT NULL,
    business_model TEXT NOT NULL,
    status TEXT DEFAULT 'enrolled',
    sequence_id TEXT,
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    last_contact_at TIMESTAMPTZ,
    meta JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (station_id, channel, business_model)
);

CREATE INDEX IF NOT EXISTS idx_gas_station_outreach_status
    ON gas_station_outreach(status);
CREATE INDEX IF NOT EXISTS idx_gas_station_outreach_model
    ON gas_station_outreach(business_model);
