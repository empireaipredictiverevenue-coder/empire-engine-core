-- 046_white_label_partners.sql
-- White-Label Partner Management — Reseller tiers, partners, containers
--
-- Tables:
--   white_label_partners       — registered reseller partners with tier, branding, revenue
--   white_label_containers     — provisioned Docker containers per partner
--   white_label_provisioning_log — audit trail of provisioning actions
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.

-- ── 1. WHITE LABEL PARTNERS ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.white_label_partners (
    partner_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    email               TEXT NOT NULL,
    company             TEXT DEFAULT '',
    phone               TEXT DEFAULT '',
    tier                TEXT NOT NULL DEFAULT 'starter',
    tier_display        TEXT NOT NULL DEFAULT 'Starter Partner',
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'suspended')),
    branding            JSONB DEFAULT '{}'::jsonb,
    containers_active   INTEGER DEFAULT 0,
    containers_max      INTEGER DEFAULT 1,
    sub_accounts        INTEGER DEFAULT 0,
    sub_accounts_max    INTEGER DEFAULT 10,
    revenue_split_pct   INTEGER DEFAULT 80,
    monthly_fee         NUMERIC(10,2) DEFAULT 299.00,
    features            JSONB DEFAULT '[]'::jsonb,
    support_level       TEXT DEFAULT 'email',
    mrr                 NUMERIC(12,2) DEFAULT 0.00,
    lifetime_revenue    NUMERIC(12,2) DEFAULT 0.00,
    notes               TEXT DEFAULT '',
    suspended_at        TIMESTAMPTZ,
    suspension_reason   TEXT DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.white_label_partners IS 'White-label reseller partners with tier, branding, and revenue tracking';
COMMENT ON COLUMN public.white_label_partners.partner_id IS 'Format: WL-XXXXXXXX (uppercase hex)';
COMMENT ON COLUMN public.white_label_partners.tier IS 'starter | growth | enterprise | agency';
COMMENT ON COLUMN public.white_label_partners.revenue_split_pct IS 'Percentage of revenue kept by partner (e.g., 80 = 80%)';

CREATE INDEX IF NOT EXISTS idx_white_label_partners_tier
    ON public.white_label_partners(tier);
CREATE INDEX IF NOT EXISTS idx_white_label_partners_status
    ON public.white_label_partners(status);
CREATE INDEX IF NOT EXISTS idx_white_label_partners_email
    ON public.white_label_partners(email);


-- ── 2. WHITE LABEL CONTAINERS ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.white_label_containers (
    container_id            TEXT PRIMARY KEY,
    partner_id              TEXT NOT NULL
                            REFERENCES public.white_label_partners(partner_id)
                            ON DELETE CASCADE,
    partner_name            TEXT DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'provisioning'
                            CHECK (status IN ('provisioning', 'running', 'config_generated', 'suspending', 'stopped', 'failed')),
    image                   TEXT DEFAULT 'empireai/hub:latest',
    port                    INTEGER,
    docker_container_name   TEXT DEFAULT '',
    docker_container_id     TEXT DEFAULT '',
    env                     JSONB DEFAULT '{}'::jsonb,
    docker_config           JSONB DEFAULT '{}'::jsonb,
    note                    TEXT DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.white_label_containers IS 'Provisioned Docker containers, one or more per partner';
COMMENT ON COLUMN public.white_label_containers.status IS 'provisioning | running | config_generated | suspending | stopped | failed';
COMMENT ON COLUMN public.white_label_containers.port IS 'Allocated port on the host (e.g., 8100)';

CREATE INDEX IF NOT EXISTS idx_white_label_containers_partner
    ON public.white_label_containers(partner_id);
CREATE INDEX IF NOT EXISTS idx_white_label_containers_status
    ON public.white_label_containers(status);


-- ── 3. WHITE LABEL PROVISIONING LOG ──────────────────────────────────
CREATE TABLE IF NOT EXISTS public.white_label_provisioning_log (
    id              BIGSERIAL PRIMARY KEY,
    partner_id      TEXT NOT NULL
                    REFERENCES public.white_label_partners(partner_id)
                    ON DELETE CASCADE,
    container_id    TEXT,
    action          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'completed',
    detail          JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.white_label_provisioning_log IS 'Audit trail of provisioning actions per partner';
COMMENT ON COLUMN public.white_label_provisioning_log.action IS 'provision | suspend | unsuspend | upgrade | downgrade | branding_update';

CREATE INDEX IF NOT EXISTS idx_white_label_log_partner
    ON public.white_label_provisioning_log(partner_id);
CREATE INDEX IF NOT EXISTS idx_white_label_log_action
    ON public.white_label_provisioning_log(action);


-- ── 4. SEED DEMO DATA ───────────────────────────────────────────────-
INSERT INTO public.white_label_partners (
    partner_id, name, email, company, tier, tier_display, status,
    containers_active, containers_max, sub_accounts, sub_accounts_max,
    revenue_split_pct, monthly_fee, features, support_level, mrr, lifetime_revenue,
    branding
) VALUES
(
    'WL-DEMO001', 'John Smith', 'john@acme-restoration.com', 'Acme Restoration Pros',
    'growth', 'Growth Partner', 'active',
    1, 3, 12, 50, 70, 799.00,
    '["custom_domain", "multi_container", "priority_support", "analytics"]'::jsonb,
    'priority', 799.00, 2397.00,
    '{"primary_color": "#00AAFF", "secondary_color": "#0A0A0F", "company_name": "Acme Restoration Pros", "custom_domain": "leads.acme-restoration.com", "logo_url": "", "theme": "dark"}'::jsonb
),
(
    'WL-DEMO002', 'Sarah Johnson', 'sarah@elite-roofing.com', 'Elite Roofing Network',
    'enterprise', 'Enterprise Partner', 'active',
    3, 10, 45, 200, 60, 1999.00,
    '["full_branding", "multi_container", "api_access", "dedicated_support", "analytics_dashboard", "custom_integrations"]'::jsonb,
    'dedicated', 1999.00, 5997.00,
    '{"primary_color": "#FF6600", "secondary_color": "#1A1A1A", "company_name": "Elite Roofing Network", "custom_domain": "leads.elite-roofing.com", "logo_url": "https://elite-roofing.com/logo.png", "theme": "dark"}'::jsonb
),
(
    'WL-DEMO003', 'Mike Chen', 'mike@starlight-construction.com', 'Starlight Construction',
    'starter', 'Starter Partner', 'active',
    0, 1, 3, 10, 80, 299.00,
    '["basic_branding", "single_container", "email_support"]'::jsonb,
    'email', 299.00, 299.00,
    '{"primary_color": "#44E5B8", "secondary_color": "#0A0A0F", "company_name": "Starlight Construction", "theme": "dark"}'::jsonb
);

-- Seed some containers for demo partners
INSERT INTO public.white_label_containers (
    container_id, partner_id, partner_name, status, image, port,
    docker_container_name, docker_container_id, env
) VALUES
(
    'CTN-ACME001', 'WL-DEMO001', 'Acme Restoration Pros',
    'running', 'empireai/hub:latest', 8101,
    'empire-partner-wl-demo001-a1b2', 'abc123def456',
    '{"PARTNER_ID": "WL-DEMO001", "PARTNER_NAME": "Acme Restoration Pros", "BRAND_PRIMARY_COLOR": "#00AAFF", "TIER": "growth", "REVENUE_SPLIT_PCT": "70", "HUB_PORT": "8101"}'::jsonb
),
(
    'CTN-ELITE001', 'WL-DEMO002', 'Elite Roofing Network',
    'running', 'empireai/hub:latest', 8102,
    'empire-partner-wl-demo002-c3d4', 'def789abc012',
    '{"PARTNER_ID": "WL-DEMO002", "PARTNER_NAME": "Elite Roofing Network", "BRAND_PRIMARY_COLOR": "#FF6600", "TIER": "enterprise", "REVENUE_SPLIT_PCT": "60", "HUB_PORT": "8102"}'::jsonb
);

-- Seed provisioning log entries
INSERT INTO public.white_label_provisioning_log (partner_id, container_id, action, status, detail) VALUES
('WL-DEMO001', 'CTN-ACME001', 'provision', 'completed', '{"port": 8101, "method": "docker_run"}'::jsonb),
('WL-DEMO002', 'CTN-ELITE001', 'provision', 'completed', '{"port": 8102, "method": "docker_run"}'::jsonb),
('WL-DEMO003', NULL, 'provision', 'completed', '{"status": "config_generated", "reason": "Docker unavailable"}'::jsonb);
