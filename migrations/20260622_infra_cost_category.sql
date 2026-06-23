-- Empire AI · Infrastructure Cost Category
-- ==========================================
-- Adds cost_category to empire_revenue_ledger for P&L breakdown.
-- Categories: subscription, usage, inference
--
-- Idempotent: safe to run multiple times.

ALTER TABLE empire_revenue_ledger
    ADD COLUMN IF NOT EXISTS cost_category text;

-- Index for filtering costs vs revenue
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_cost_category
    ON empire_revenue_ledger (cost_category);

-- Index for service-level cost breakdown
CREATE INDEX IF NOT EXISTS idx_revenue_ledger_source_type_source_id
    ON empire_revenue_ledger (source_type, source_id);
