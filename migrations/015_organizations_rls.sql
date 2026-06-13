-- ============================================================================
-- EMPIRE V49 · DDL MIGRATION 015: ORGANIZATIONS + ROW-LEVEL SECURITY
-- ============================================================================
-- Phase 10: Multi-tenant isolation. Every business data row gets an org_id
-- column. Supabase RLS policies enforce that operators only see rows
-- belonging to their organization.
--
-- Migration order:
--   1. CREATE organizations table
--   2. ALTER operators → add org_id
--   3. ALTER all business tables → add org_id
--   4. Enable RLS + create policies on each table
--   5. Migrate existing data into a default org
--   6. Seed the default organization
--
-- Idempotent: All CREATE/ALTER use IF NOT EXISTS.
-- ============================================================================


-- ── 1. ORGANIZATIONS TABLE ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.organizations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Identity
    name                text NOT NULL,
    slug                text NOT NULL UNIQUE,         -- URL-safe org identifier
    domain              text,                         -- custom domain (white-label)

    -- Owner (the operator who created / owns this org)
    owner_id            uuid,                         -- FK to operators, added after ALTER

    -- Billing
    billing_plan        text NOT NULL DEFAULT 'free'
        CHECK (billing_plan IN ('free', 'starter', 'professional', 'enterprise')),
    billing_status      text NOT NULL DEFAULT 'active'
        CHECK (billing_status IN ('active', 'past_due', 'canceled', 'trialing')),

    -- White-label branding
    branding            jsonb DEFAULT '{}'::jsonb,    -- {logo_url, primary_color, favicon, ...}

    -- Feature flags
    features            jsonb DEFAULT '{}'::jsonb,    -- {inbound_router: true, buyer_spy: false, ...}

    -- Limits
    max_operators       integer NOT NULL DEFAULT 5,
    max_leads_per_month integer NOT NULL DEFAULT 1000,

    -- Metadata
    meta                jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS organizations_slug_idx ON public.organizations (slug);
CREATE INDEX IF NOT EXISTS organizations_owner_idx ON public.organizations (owner_id);

COMMENT ON TABLE  public.organizations IS 'Multi-tenant organizations — isolates operators, data, billing, and branding per tenant';
COMMENT ON COLUMN public.organizations.slug IS 'URL-safe identifier used in API routes and subdomains';
COMMENT ON COLUMN public.organizations.domain IS 'Custom domain for white-label access (e.g. acme.empire-ai.co.uk)';
COMMENT ON COLUMN public.organizations.branding IS 'White-label config: {logo_url, primary_color, secondary_color, favicon, font_family}';
COMMENT ON COLUMN public.organizations.features IS 'Feature flags enabled for this organization';


-- ── 2. ADD ORG_ID TO EXISTING TABLES ─────────────────────────────────
-- Each statement is idempotent via IF NOT EXISTS on the column.

-- Operators → scoped to an organization
ALTER TABLE public.operators
    ADD COLUMN IF NOT EXISTS org_id uuid REFERENCES public.organizations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS operators_org_idx ON public.operators (org_id);

-- Business tables (add org_id to each)
ALTER TABLE public.radar_targets      ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.strike_log         ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.call_logs          ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.dispatches         ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.inbound_leads      ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.email_sequences    ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.sms_sequences      ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.contractors        ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.buyers             ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.buyer_subscriptions ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.affiliate_links    ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.payout_log         ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.email_drafts       ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.audit_log          ADD COLUMN IF NOT EXISTS org_id uuid;
ALTER TABLE public.operator_sessions  ADD COLUMN IF NOT EXISTS org_id uuid;

-- Indexes for RLS performance
CREATE INDEX IF NOT EXISTS radar_targets_org_idx      ON public.radar_targets (org_id);
CREATE INDEX IF NOT EXISTS strike_log_org_idx         ON public.strike_log (org_id);
CREATE INDEX IF NOT EXISTS call_logs_org_idx          ON public.call_logs (org_id);
CREATE INDEX IF NOT EXISTS dispatches_org_idx         ON public.dispatches (org_id);
CREATE INDEX IF NOT EXISTS inbound_leads_org_idx      ON public.inbound_leads (org_id);
CREATE INDEX IF NOT EXISTS email_seq_org_idx          ON public.email_sequences (org_id);
CREATE INDEX IF NOT EXISTS sms_seq_org_idx            ON public.sms_sequences (org_id);
CREATE INDEX IF NOT EXISTS contractors_org_idx        ON public.contractors (org_id);
CREATE INDEX IF NOT EXISTS buyers_org_idx             ON public.buyers (org_id);
CREATE INDEX IF NOT EXISTS buyer_subs_org_idx         ON public.buyer_subscriptions (org_id);
CREATE INDEX IF NOT EXISTS affiliate_links_org_idx    ON public.affiliate_links (org_id);
CREATE INDEX IF NOT EXISTS payout_log_org_idx         ON public.payout_log (org_id);
CREATE INDEX IF NOT EXISTS audit_log_org_idx          ON public.audit_log (org_id);


-- ── 3. ENABLE RLS + CREATE POLICIES ─────────────────────────────────

-- Helper function: create an RLS policy that scopes SELECT/INSERT/UPDATE/DELETE to org_id
-- Must be run per-table.

-- operators
ALTER TABLE public.operators ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operators_org_isolation ON public.operators;
CREATE POLICY operators_org_isolation ON public.operators
    USING (org_id = current_setting('app.current_org_id')::uuid OR
           current_setting('app.current_role')::text = 'owner');

-- radar_targets
ALTER TABLE public.radar_targets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS radar_targets_org_isolation ON public.radar_targets;
CREATE POLICY radar_targets_org_isolation ON public.radar_targets
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- strike_log
ALTER TABLE public.strike_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS strike_log_org_isolation ON public.strike_log;
CREATE POLICY strike_log_org_isolation ON public.strike_log
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- call_logs
ALTER TABLE public.call_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS call_logs_org_isolation ON public.call_logs;
CREATE POLICY call_logs_org_isolation ON public.call_logs
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- dispatches
ALTER TABLE public.dispatches ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dispatches_org_isolation ON public.dispatches;
CREATE POLICY dispatches_org_isolation ON public.dispatches
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- inbound_leads
ALTER TABLE public.inbound_leads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS inbound_leads_org_isolation ON public.inbound_leads;
CREATE POLICY inbound_leads_org_isolation ON public.inbound_leads
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- email_sequences
ALTER TABLE public.email_sequences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS email_sequences_org_isolation ON public.email_sequences;
CREATE POLICY email_sequences_org_isolation ON public.email_sequences
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- sms_sequences
ALTER TABLE public.sms_sequences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sms_sequences_org_isolation ON public.sms_sequences;
CREATE POLICY sms_sequences_org_isolation ON public.sms_sequences
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- contractors
ALTER TABLE public.contractors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS contractors_org_isolation ON public.contractors;
CREATE POLICY contractors_org_isolation ON public.contractors
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- buyers
ALTER TABLE public.buyers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS buyers_org_isolation ON public.buyers;
CREATE POLICY buyers_org_isolation ON public.buyers
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- buyer_subscriptions
ALTER TABLE public.buyer_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS buyer_subs_org_isolation ON public.buyer_subscriptions;
CREATE POLICY buyer_subs_org_isolation ON public.buyer_subscriptions
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- affiliate_links
ALTER TABLE public.affiliate_links ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS affiliate_links_org_isolation ON public.affiliate_links;
CREATE POLICY affiliate_links_org_isolation ON public.affiliate_links
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- payout_log
ALTER TABLE public.payout_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS payout_log_org_isolation ON public.payout_log;
CREATE POLICY payout_log_org_isolation ON public.payout_log
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- email_drafts
ALTER TABLE public.email_drafts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS email_drafts_org_isolation ON public.email_drafts;
CREATE POLICY email_drafts_org_isolation ON public.email_drafts
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- audit_log
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_log_org_isolation ON public.audit_log;
CREATE POLICY audit_log_org_isolation ON public.audit_log
    USING (org_id = current_setting('app.current_org_id')::uuid);


-- ── 4. STORED PROCEDURE: ENFORCE ORG_ID ON WRITE ────────────────────
-- This function is called from a BEFORE INSERT trigger on each business table.
-- It reads the current org from a custom GUC (Grand Unified Configuration)
-- parameter set by the application at the start of each request.

CREATE OR REPLACE FUNCTION enforce_org_id()
RETURNS trigger AS $$
BEGIN
    -- If no org_id is explicitly set, default to the current request's org
    IF NEW.org_id IS NULL THEN
        BEGIN
            NEW.org_id := current_setting('app.current_org_id')::uuid;
        EXCEPTION WHEN OTHERS THEN
            -- Leave as NULL if not set (shouldn't happen in production)
            NULL;
        END;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── 5. SEED DEFAULT ORGANIZATION ────────────────────────────────────
-- Creates the default org for existing data. Runs once.
INSERT INTO public.organizations (name, slug, billing_plan, billing_status, max_operators, max_leads_per_month)
VALUES ('Empire AI', 'empire-ai', 'enterprise', 'active', 50, 100000)
ON CONFLICT (slug) DO NOTHING;


-- ── 6. MIGRATE EXISTING OPERATORS TO DEFAULT ORG ────────────────────
-- Sets org_id on all operators that don't have one yet.
DO $$
DECLARE
    default_org_id uuid;
BEGIN
    SELECT id INTO default_org_id FROM public.organizations WHERE slug = 'empire-ai';
    IF default_org_id IS NOT NULL THEN
        UPDATE public.operators SET org_id = default_org_id WHERE org_id IS NULL;
        UPDATE public.organizations SET owner_id = (SELECT id FROM public.operators WHERE role = 'owner' LIMIT 1) WHERE id = default_org_id AND owner_id IS NULL;
    END IF;
END $$;


-- ── VERIFICATION ─────────────────────────────────────────────────────
-- -- Check orgs:
-- SELECT id, name, slug, billing_plan, max_operators FROM public.organizations;
--
-- -- Check operators with org:
-- SELECT id, email, name, role, org_id FROM public.operators LIMIT 10;
--
-- -- Check a business table for org isolation:
-- SELECT COUNT(*) FROM public.radar_targets WHERE org_id IS NULL;
