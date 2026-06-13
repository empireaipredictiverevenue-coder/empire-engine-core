-- ═══════════════════════════════════════════════════════════════════════════
-- EMPIRE V49 · MASTER SCHEMA
-- ═══════════════════════════════════════════════════════════════════════════
-- Run this once in your Supabase SQL editor.
-- Idempotent · safe to re-run (uses IF NOT EXISTS everywhere).
--
-- Sections:
--   1. Extensions
--   2. Core lead generation (radar_targets, strike_log, brain_decisions)
--   3. Outreach (sms_*, email_*, call_events)
--   4. Contractors (contractors, contractor_applications, contractor_trust_log)
--   5. Matching & dispatch (dispatches, metro_adjacency)
--   6. Settlements & payouts (claim_outcomes, payout_rules, payout_log)
--   7. Multi-operator auth (operators, operator_sessions, audit_log)
--   8. Inbound calls (inbound_calls)
--   9. Brain learning (brain_memory, brain_config) · requires pgvector
--   10. RPC functions
--   11. Bootstrap seeds (you MUST edit before running)
-- ═══════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────
-- 1. EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "postgis";     -- for POINT() geometry (if using)
CREATE EXTENSION IF NOT EXISTS vector;        -- for brain memory embeddings


-- ─────────────────────────────────────────────────────────────────────
-- 2. CORE LEAD GENERATION
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS radar_targets (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  address          text NOT NULL,
  phone            text,
  email            text,
  source_url       text,
  city             text,
  location         text,                       -- POINT(lon lat) string
  status           text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','expired','converted','blocked')),
  damage_severity  text,
  urgency_score    int CHECK (urgency_score BETWEEN 0 AND 10),
  meta             jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS radar_targets_phone_idx ON radar_targets (phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS radar_targets_email_idx ON radar_targets (email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS radar_targets_status_idx ON radar_targets (status, created_at DESC);
CREATE INDEX IF NOT EXISTS radar_targets_city_idx ON radar_targets (city);

CREATE TABLE IF NOT EXISTS strike_log (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  target_id       uuid REFERENCES radar_targets(id),
  alert_event     text,
  alert_area      text,
  severity        text,
  distance_km     numeric(6,2),
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS strike_log_recent_idx ON strike_log (created_at DESC);

CREATE TABLE IF NOT EXISTS brain_decisions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  lead_id         uuid REFERENCES radar_targets(id),
  strike_id       uuid REFERENCES strike_log(id),
  decision        text NOT NULL CHECK (decision IN ('GO','NO_GO')),
  urgency         int,
  reasoning       text,
  asset_value     numeric(14,2),
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS brain_decisions_recent_idx ON brain_decisions (created_at DESC);


-- ─────────────────────────────────────────────────────────────────────
-- 3. OUTREACH (SMS, Email, Voice)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sms_sequences (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  phone           text NOT NULL UNIQUE,
  target_addr     text,
  sequence_type   text NOT NULL DEFAULT 'storm_strike',
  current_step    int NOT NULL DEFAULT 0,
  status          text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','paused','completed','opted_out','replied')),
  last_sent_at    timestamptz,
  next_send_at    timestamptz,
  replies_count   int DEFAULT 0,
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS sms_sequences_dispatch_idx
  ON sms_sequences (status, next_send_at);
CREATE INDEX IF NOT EXISTS sms_sequences_phone_idx ON sms_sequences (phone);

CREATE TABLE IF NOT EXISTS sms_opt_outs (
  phone      text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  reason     text DEFAULT 'STOP keyword',
  meta       jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS outbound_dnc (
  phone      text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  reason     text DEFAULT 'manual',
  meta       jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS sms_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  phone         text NOT NULL,
  direction     text CHECK (direction IN ('outbound','inbound')),
  body          text,
  step          int,
  message_uuid  text,
  delivered     boolean DEFAULT false
);
CREATE INDEX IF NOT EXISTS sms_log_phone_idx ON sms_log (phone, created_at DESC);

CREATE TABLE IF NOT EXISTS email_sequences (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  email           text NOT NULL UNIQUE,
  target_addr     text,
  sequence_type   text NOT NULL DEFAULT 'storm_strike',
  current_step    int NOT NULL DEFAULT 0,
  status          text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','paused','completed','unsubscribed','bounced','replied')),
  last_sent_at    timestamptz,
  next_send_at    timestamptz,
  bounces         int DEFAULT 0,
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS email_sequences_dispatch_idx
  ON email_sequences (status, next_send_at);

CREATE TABLE IF NOT EXISTS email_unsubscribes (
  email      text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  reason     text DEFAULT 'one-click unsubscribe',
  meta       jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS email_log (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  timestamptz NOT NULL DEFAULT now(),
  email       text NOT NULL,
  direction   text CHECK (direction IN ('outbound','bounce','reply')),
  subject     text,
  step        int,
  message_id  text,
  delivered   boolean DEFAULT false,
  meta        jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS email_log_email_idx ON email_log (email, created_at DESC);

CREATE TABLE IF NOT EXISTS call_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  timestamptz NOT NULL DEFAULT now(),
  call_uuid   text,
  status      text,
  direction   text,
  duration    int DEFAULT 0,
  sub_state   text,          -- AMD detection sub_state: beep_start, beep_timeout
  meta        jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS call_events_uuid_idx ON call_events (call_uuid);
CREATE INDEX IF NOT EXISTS call_events_recent_idx ON call_events (created_at DESC);


-- ─────────────────────────────────────────────────────────────────────
-- 4. CONTRACTORS
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contractors (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at          timestamptz NOT NULL DEFAULT now(),
  name                text NOT NULL,
  email               text NOT NULL UNIQUE,
  phone               text,
  metro               text,
  license_no          text,
  license_state       text,
  specialties         text[] DEFAULT '{}',
  active              boolean DEFAULT true,
  trust_score         numeric(4,2) DEFAULT 5.0,
  completed_jobs      int DEFAULT 0,
  max_concurrent      int DEFAULT 3,
  last_dispatched_at  timestamptz,
  solana_wallet       text,
  meta                jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS contractors_active_metro_idx
  ON contractors (active, metro) WHERE active = true;

CREATE TABLE IF NOT EXISTS contractor_applications (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  name              text NOT NULL,
  email             text NOT NULL,
  phone             text NOT NULL,
  company           text,
  metro             text NOT NULL,
  license_no        text,
  license_state     text,
  specialties       text[] DEFAULT '{}',
  years_in_biz      int,
  insurance_carrier text,
  ein               text,
  notes             text,
  status            text NOT NULL DEFAULT 'pending_email'
    CHECK (status IN ('pending_email','pending_review','approved','rejected','withdrawn')),
  approved_at       timestamptz,
  rejected_at       timestamptz,
  rejected_reason   text,
  contractor_id     uuid REFERENCES contractors(id),
  meta              jsonb DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS contractor_applications_active_email
  ON contractor_applications (email)
  WHERE status NOT IN ('rejected','withdrawn');
CREATE INDEX IF NOT EXISTS contractor_applications_status_idx
  ON contractor_applications (status, created_at DESC);

CREATE TABLE IF NOT EXISTS contractor_trust_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  contractor_id uuid NOT NULL REFERENCES contractors(id),
  outcome       text,
  delta         numeric(4,2),
  before        numeric(4,2),
  after         numeric(4,2),
  notes         text
);


-- ─────────────────────────────────────────────────────────────────────
-- 5. MATCHING & DISPATCH
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dispatches (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        timestamptz NOT NULL DEFAULT now(),
  lead_id           uuid REFERENCES radar_targets(id),
  contractor_id     uuid NOT NULL REFERENCES contractors(id),
  match_score       numeric(4,3),
  match_components  jsonb DEFAULT '{}'::jsonb,
  token             text UNIQUE,
  status            text NOT NULL DEFAULT 'sent'
    CHECK (status IN ('sent','accepted','rejected','expired','completed','ghosted')),
  accepted_at       timestamptz,
  completed_at      timestamptz,
  ghosted_at        timestamptz,
  payout_amount     numeric(12,2),
  meta              jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS dispatches_lead_idx       ON dispatches (lead_id);
CREATE INDEX IF NOT EXISTS dispatches_contractor_idx ON dispatches (contractor_id);
CREATE INDEX IF NOT EXISTS dispatches_status_idx     ON dispatches (status, created_at DESC);

CREATE TABLE IF NOT EXISTS metro_adjacency (
  metro       text NOT NULL,
  adjacent_to text NOT NULL,
  distance_km numeric(6,1),
  PRIMARY KEY (metro, adjacent_to)
);

INSERT INTO metro_adjacency (metro, adjacent_to) VALUES
  ('Dallas / Fort Worth', 'Plano'),
  ('Plano', 'Dallas / Fort Worth'),
  ('Houston', 'Galveston'),
  ('Galveston', 'Houston'),
  ('Dallas / Fort Worth', 'Fort Worth'),
  ('Fort Worth', 'Dallas / Fort Worth')
ON CONFLICT DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────
-- 6. SETTLEMENTS & PAYOUTS
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS claim_outcomes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  lead_id         uuid REFERENCES radar_targets(id),
  dispatch_id     uuid REFERENCES dispatches(id),
  contractor_id   uuid REFERENCES contractors(id),
  target_addr     text,
  outcome         text NOT NULL
    CHECK (outcome IN ('pending','settled','denied','withdrawn','no_damage')),
  actual_payout   numeric(12,2),
  actual_fee      numeric(12,2),
  notes           text,
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS claim_outcomes_outcome_idx
  ON claim_outcomes (outcome, created_at DESC);

CREATE TABLE IF NOT EXISTS payout_rules (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  name            text NOT NULL,
  active          boolean DEFAULT true,
  contractor_pct  numeric(5,4) NOT NULL,
  ops_pct         numeric(5,4) NOT NULL,
  vault_pct       numeric(5,4) NOT NULL,
  min_settlement  numeric(12,2) DEFAULT 0,
  max_settlement  numeric(12,2),
  CHECK (ABS(contractor_pct + ops_pct + vault_pct - 1.0) < 0.001)
);

-- TODO(fee-decision-pending): revisit 70/20/10 split with Phil. Current split is unchanged; only gross bumped 1% → 3% on 2026-06-13. (See commit message.)
INSERT INTO payout_rules (name, contractor_pct, ops_pct, vault_pct)
VALUES ('Default 70/20/10', 0.70, 0.20, 0.10)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS payout_log (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at          timestamptz NOT NULL DEFAULT now(),
  settlement_id       text,
  claim_outcome_id    uuid REFERENCES claim_outcomes(id),
  dispatch_id         uuid REFERENCES dispatches(id),
  contractor_id       uuid REFERENCES contractors(id),
  recipient_type      text CHECK (recipient_type IN ('contractor','ops','vault')),
  recipient_wallet    text NOT NULL,
  amount_usdc         numeric(12,4) NOT NULL,
  rule_applied        uuid REFERENCES payout_rules(id),
  status              text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','executing','sent','failed','cancelled')),
  tx_sig              text,
  approved_by         text,
  approved_at         timestamptz,
  executed_at         timestamptz,
  failure_reason      text,
  meta                jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS payout_log_status_idx ON payout_log (status, created_at DESC);
CREATE INDEX IF NOT EXISTS payout_log_settlement_idx ON payout_log (settlement_id);


-- ─────────────────────────────────────────────────────────────────────
-- 7. MULTI-OPERATOR AUTH
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operators (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   timestamptz NOT NULL DEFAULT now(),
  email        text NOT NULL UNIQUE,
  name         text NOT NULL,
  role         text NOT NULL DEFAULT 'operator'
    CHECK (role IN ('owner','operator','viewer')),
  active       boolean NOT NULL DEFAULT true,
  last_login   timestamptz,
  invited_by   uuid REFERENCES operators(id),
  meta         jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS operator_sessions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   timestamptz NOT NULL DEFAULT now(),
  operator_id  uuid NOT NULL REFERENCES operators(id),
  token_hash   text NOT NULL,
  expires_at   timestamptz NOT NULL,
  revoked_at   timestamptz,
  user_agent   text,
  ip           text
);
CREATE INDEX IF NOT EXISTS operator_sessions_hash_idx
  ON operator_sessions (token_hash);

CREATE TABLE IF NOT EXISTS audit_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  operator_id   uuid,
  operator_name text,
  action        text NOT NULL,
  target_type   text,
  target_id     text,
  details       jsonb DEFAULT '{}'::jsonb,
  ip            text
);
CREATE INDEX IF NOT EXISTS audit_log_created_idx
  ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_operator_idx
  ON audit_log (operator_id, created_at DESC);


-- ─────────────────────────────────────────────────────────────────────
-- 8. INBOUND CALLS
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inbound_calls (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  call_uuid       text UNIQUE NOT NULL,
  from_number     text NOT NULL,
  to_number       text,
  duration        int DEFAULT 0,
  disposition     text
    CHECK (disposition IN ('forwarded','voicemail','opt_out','hung_up')),
  recording_url   text,
  recording_path  text,
  transcript      text,
  urgency_score   int,
  intent          text,
  matched_lead_id uuid REFERENCES radar_targets(id),
  status          text DEFAULT 'new'
    CHECK (status IN ('new','reviewed','called_back','closed')),
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS inbound_calls_status_idx
  ON inbound_calls (status, urgency_score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS inbound_calls_from_idx
  ON inbound_calls (from_number);


-- ─────────────────────────────────────────────────────────────────────
-- 9. BRAIN LEARNING
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brain_memory (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  lead_id         uuid REFERENCES radar_targets(id),
  decision        text NOT NULL CHECK (decision IN ('GO','NO_GO')),
  urgency         int,
  reasoning       text,
  context_text    text NOT NULL,
  embedding       vector(1536),
  asset_value     numeric(14,2),
  severity        text,
  city            text,
  outcome_id      uuid REFERENCES claim_outcomes(id),
  outcome         text,
  actual_fee      numeric(12,2),
  meta            jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS brain_memory_city_severity_idx
  ON brain_memory (city, severity);
CREATE INDEX IF NOT EXISTS brain_memory_outcome_idx
  ON brain_memory (outcome) WHERE outcome IS NOT NULL;

-- ANN index for similarity search · only build once you have data
-- (uncomment after first 100 rows)
-- CREATE INDEX IF NOT EXISTS brain_memory_embedding_idx
--   ON brain_memory USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists = 100);

CREATE TABLE IF NOT EXISTS brain_config (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  city            text NOT NULL,
  severity        text NOT NULL,
  asset_band      text NOT NULL,
  urgency_floor   int NOT NULL,
  sample_size     int NOT NULL,
  win_rate        numeric(5,4),
  avg_fee         numeric(12,2),
  expected_value  numeric(12,2),
  updated_by      text DEFAULT 'auto_tuner',
  UNIQUE (city, severity, asset_band)
);


-- ─────────────────────────────────────────────────────────────────────
-- 10. RPC FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────

-- Brain memory similarity search via pgvector cosine distance
CREATE OR REPLACE FUNCTION match_brain_memory(
  query_embedding vector(1536),
  match_count int
)
RETURNS TABLE (
  id uuid,
  context_text text,
  decision text,
  urgency int,
  reasoning text,
  city text,
  severity text,
  asset_value numeric,
  outcome text,
  actual_fee numeric,
  similarity float
)
LANGUAGE sql STABLE AS $$
  SELECT
    bm.id,
    bm.context_text,
    bm.decision,
    bm.urgency,
    bm.reasoning,
    bm.city,
    bm.severity,
    bm.asset_value,
    bm.outcome,
    bm.actual_fee,
    1 - (bm.embedding <=> query_embedding) as similarity
  FROM brain_memory bm
  WHERE bm.embedding IS NOT NULL
  ORDER BY bm.embedding <=> query_embedding
  LIMIT match_count;
$$;


-- ─────────────────────────────────────────────────────────────────────
-- 11. BOOTSTRAP SEEDS · EDIT BEFORE RUNNING
-- ─────────────────────────────────────────────────────────────────────

-- ⚠ REPLACE THE EMAIL BELOW WITH YOUR REAL OWNER EMAIL BEFORE RUNNING
INSERT INTO operators (email, name, role) VALUES
  ('PhillipLivesley@empire-ai.co.uk', 'Empire Owner', 'owner')
ON CONFLICT (email) DO NOTHING;


-- ═══════════════════════════════════════════════════════════════════════════
-- SCHEMA INSTALL COMPLETE
-- ═══════════════════════════════════════════════════════════════════════════
-- Verify with:
--   SELECT count(*) FROM information_schema.tables
--   WHERE table_schema = 'public';
-- Expected: 25+ tables
-- ═══════════════════════════════════════════════════════════════════════════
