-- 20260616: Add template_variant column to outreach tables
-- Enables A/B testing: compare conversion rates between generic vs
-- warehouse/abandoned-specific email templates.

-- Idle Asset Outreach
ALTER TABLE IF EXISTS idle_asset_outreach
  ADD COLUMN IF NOT EXISTS template_variant TEXT DEFAULT 'generic';

-- Gas Station Outreach
ALTER TABLE IF EXISTS gas_station_outreach
  ADD COLUMN IF NOT EXISTS template_variant TEXT DEFAULT 'generic';

-- Index for querying A/B test results by variant
CREATE INDEX IF NOT EXISTS idx_idle_outreach_variant
  ON idle_asset_outreach (template_variant);

CREATE INDEX IF NOT EXISTS idx_gas_outreach_variant
  ON gas_station_outreach (template_variant);
