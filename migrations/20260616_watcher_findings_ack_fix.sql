-- Add acknowledged/fixed tracking columns to watcher_findings
-- Created 2026-06-16 after code review flagged missing columns

ALTER TABLE watcher_findings
  ADD COLUMN IF NOT EXISTS acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS fixed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS fixed_at TIMESTAMPTZ;

-- Index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_watcher_findings_acknowledged ON watcher_findings (acknowledged);
CREATE INDEX IF NOT EXISTS idx_watcher_findings_fixed ON watcher_findings (fixed);
