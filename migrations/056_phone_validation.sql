-- EMPIRE V49 · DDL MIGRATION 056: PHONE VALIDATION COLUMNS ON CONTRACTORS
-- =====================================================================
-- PhoneInfoga pipeline needs to store OSINT scan results on the
-- contractor record. Adds:
--   - phone_validation_json (jsonb)  full phoneinfoga scan output
--   - phone_validated_at    (timestamptz)  last scan timestamp
--   - phone_provider        (text)  carrier/network detected by phoneinfoga
--   - phone_country_code    (text)  e.g. "US", "GB"
--   - phone_line_type       (text)  mobile/landline/voip
-- Run: python3 scripts/run_migrations.py migrations/056_phone_validation.sql
--   or: psql "$SUPABASE_DB_URL" -f migrations/056_phone_validation.sql

ALTER TABLE public.contractors
    ADD COLUMN IF NOT EXISTS phone_validation_json jsonb DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS phone_validated_at   timestamptz DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS phone_provider       text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS phone_country_code   text DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS phone_line_type      text DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_contractors_phone_validated
    ON public.contractors (phone_validated_at)
    WHERE phone_validated_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contractors_phone_validation_pending
    ON public.contractors (phone)
    WHERE phone IS NOT NULL AND phone_validation_json IS NULL;