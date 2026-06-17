-- 20260616: watcher_findings table for the Error Watcher agent
--
-- The error_watcher bot (bots/error_watcher.py) monitors all agent
-- errors across the system, aggregates them, and saves structured
-- findings here for the predictive-revenue coder to pick up.
--
-- Migration is idempotent. Safe to run multiple times.
-- See also: bots/error_watcher.py

CREATE TABLE IF NOT EXISTS watcher_findings (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent_name        TEXT NOT NULL,
    finding_type      TEXT NOT NULL,
    severity          TEXT NOT NULL DEFAULT 'warning',
    title             TEXT NOT NULL,
    detail            TEXT,
    error_count       INTEGER DEFAULT 0,
    sample_errors     JSONB,
    recommended_action TEXT,
    source_table      TEXT,
    acknowledged      BOOLEAN DEFAULT FALSE,
    fixed_by          TEXT,
    fixed_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_watcher_findings_created
    ON watcher_findings (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_watcher_findings_agent
    ON watcher_findings (agent_name);

CREATE INDEX IF NOT EXISTS idx_watcher_findings_unacked
    ON watcher_findings (acknowledged, created_at DESC)
    WHERE acknowledged = FALSE;

COMMENT ON TABLE watcher_findings IS
  'Error Watcher agent findings — structured error reports for the predictive-revenue coder';
COMMENT ON COLUMN watcher_findings.finding_type IS
  'high_error_rate | pm2_log_errors | stale_heartbeat | infra_critical | skill_circuit_opened';
COMMENT ON COLUMN watcher_findings.severity IS
  'critical | warning | info';
COMMENT ON COLUMN watcher_findings.recommended_action IS
  'Human-readable action the coder or operator should take';
COMMENT ON COLUMN watcher_findings.acknowledged IS
  'False = needs coder attention; True = reviewed or fixed';
