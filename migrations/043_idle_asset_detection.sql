-- 043_idle_asset_detection.sql
-- Idle Asset Detection — Logistics Compound Discovery + Waste Scoring
--
-- Tables:
--   logistics_compounds  — discovered truck yards, warehouses, distribution centers
--   idle_asset_scans     — scan run history with stats

CREATE TABLE IF NOT EXISTS logistics_compounds (
    compound_id TEXT PRIMARY KEY,
    name TEXT,
    address TEXT,
    city TEXT,
    state TEXT DEFAULT 'TX',
    metro TEXT,
    lat FLOAT8,
    lon FLOAT8,
    compound_type TEXT,              -- truck_yard, warehouse, distribution, loading_dock
    area_sq_meters FLOAT8 DEFAULT 0,
    trailer_capacity_est INTEGER DEFAULT 0,
    idle_score FLOAT8 DEFAULT 0.0,   -- 0-1 waste probability
    idle_indicators JSONB DEFAULT '[]'::jsonb,
    source TEXT DEFAULT 'osm_overpass',
    last_scanned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_logistics_compounds_metro 
    ON logistics_compounds(metro);
CREATE INDEX IF NOT EXISTS idx_logistics_compounds_score 
    ON logistics_compounds(idle_score DESC);
CREATE INDEX IF NOT EXISTS idx_logistics_compounds_type 
    ON logistics_compounds(compound_type);

CREATE TABLE IF NOT EXISTS idle_asset_scans (
    id SERIAL PRIMARY KEY,
    scan_started_at TIMESTAMPTZ DEFAULT NOW(),
    scan_completed_at TIMESTAMPTZ,
    compounds_discovered INTEGER DEFAULT 0,
    metros_scanned INTEGER DEFAULT 0,
    highest_idle_score FLOAT8,
    top_compound_id TEXT REFERENCES logistics_compounds(compound_id),
    status TEXT DEFAULT 'running',
    error TEXT,
    meta JSONB DEFAULT '{}'::jsonb
);
