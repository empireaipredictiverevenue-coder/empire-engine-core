-- Add niche/vertical tracking for scale/expand
ALTER TABLE enriched_leads ADD COLUMN IF NOT EXISTS niche text;
ALTER TABLE enriched_leads ADD COLUMN IF NOT EXISTS vertical text;
ALTER TABLE contractors ADD COLUMN IF NOT EXISTS niche text;
ALTER TABLE contractors ADD COLUMN IF NOT EXISTS trade text;
COMMENT ON COLUMN enriched_leads.niche IS 'Roofing, Restoration, Public Adjuster, etc.';
COMMENT ON COLUMN enriched_leads.vertical IS 'Storm, Mass Tort, Commercial, etc.';
