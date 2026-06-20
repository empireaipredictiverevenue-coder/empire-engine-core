-- Migration: add auto-generated UUID default to carrier_claims.id
-- Fixes insert failures when the claim webhook doesn't provide an explicit id.

ALTER TABLE public.carrier_claims
    ALTER COLUMN id SET DEFAULT gen_random_uuid();
