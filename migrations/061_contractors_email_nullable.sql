-- Migration 061: allow nullable email on contractors, drop NOT NULL + UNIQUE constraint,
-- add partial unique index only when email is present.
-- This unblocks prospector_bridge from creating rows without placeholder emails
-- (real email discovered later via contact_discovery / enrichment).

ALTER TABLE contractors ALTER COLUMN email DROP NOT NULL;
ALTER TABLE contractors DROP CONSTRAINT IF EXISTS contractors_email_key;

CREATE UNIQUE INDEX IF NOT EXISTS contractors_email_unique_when_present
  ON contractors (email)
  WHERE email IS NOT NULL AND email != '';

INSERT INTO schema_migrations (name) VALUES ('061_contractors_email_nullable.sql')
  ON CONFLICT (name) DO NOTHING;