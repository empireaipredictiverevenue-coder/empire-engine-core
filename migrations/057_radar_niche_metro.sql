-- EMPIRE V49 · DDL MIGRATION 057: B2B LEADS COLUMNS ON RADAR_TARGETS
-- =================================================================
-- The b2b_lead_scraper / firecrawl_b2b_scraper / camofox_bbb_scraper
-- pipelines need to record the niche + metro + sub-niche of each lead.
-- radar_targets was missing these columns.
-- Adds:
--   - niche        (text)  primary B2B lane
--   - sub_niche    (text)  finer classification
--   - metro        (text)  city slug e.g. "dallas-tx"
--   - captured_at  (timestamptz)  when we first saw the lead
-- Run: python3 scripts/run_migrations.py migrations/057_radar_niche_metro.sql

ALTER TABLE public.radar_targets
    ADD COLUMN IF NOT EXISTS niche        text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS sub_niche    text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS metro        text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS captured_at  timestamptz DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_radar_targets_niche_metro
    ON public.radar_targets (niche, metro)
    WHERE niche IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_radar_targets_metro
    ON public.radar_targets (metro)
    WHERE metro IS NOT NULL;