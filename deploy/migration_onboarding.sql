-- ═══════════════════════════════════════════════════════════════════════════
-- EMPIRE V49 · PARTNER ONBOARDING SCHEMA MIGRATION
-- ═══════════════════════════════════════════════════════════════════════════
-- Adds columns to existing `buyers` table for status-based approval workflow.
-- Creates `compliance_audit_logs` table for Compliance-as-Code audit trail.
--
-- Run: psql $DATABASE_URL -f deploy/migration_onboarding.sql
-- Or:  paste into Supabase SQL Editor.
-- ═══════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────
-- 1. BUYERS TABLE — add status workflow columns
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS status        text NOT NULL DEFAULT 'active'
    CHECK (status IN ('pending_review', 'active', 'rejected'));

ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS email         text;

ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS contact_name  text;

ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS notes         text;

ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS reviewed_at   timestamptz;

ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS reviewed_by   uuid;

-- ─────────────────────────────────────────────────────────────────────
-- 2. COMPLIANCE AUDIT LOGS — dedicated table for compliance events
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_audit_logs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  action        text NOT NULL,
  entity_type   text NOT NULL,
  entity_id     text,
  operator_id   text,
  operator_name text,
  details       jsonb DEFAULT '{}'::jsonb,
  ip            text
);

CREATE INDEX IF NOT EXISTS compliance_audit_logs_created_idx
  ON compliance_audit_logs (created_at DESC);

CREATE INDEX IF NOT EXISTS compliance_audit_logs_entity_idx
  ON compliance_audit_logs (entity_type, entity_id);

-- ─────────────────────────────────────────────────────────────────────
-- 3. EXISTING BUYERS — mark current active buyers so migration is safe
-- ─────────────────────────────────────────────────────────────────────
UPDATE buyers SET status = 'active' WHERE status IS NULL;


-- ═══════════════════════════════════════════════════════════════════════════
-- MIGRATION COMPLETE
-- ═══════════════════════════════════════════════════════════════════════════
-- Verify with:
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'buyers' ORDER BY ordinal_position;
-- Expected new columns: status, email, contact_name, notes, reviewed_at, reviewed_by
--   SELECT count(*) FROM information_schema.tables
--   WHERE table_name = 'compliance_audit_logs';
-- Expected: 1
-- ═══════════════════════════════════════════════════════════════════════════
