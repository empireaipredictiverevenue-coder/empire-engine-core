-- 047_hexstrike.sql
-- hexstrike-ai — Internal Security Agent Findings & Scan Logs
--
-- Tables:
--   hexstrike_findings       — Security findings (vulns, misconfigs, secrets leaks)
--   hexstrike_scans          — Scan run history with coverage stats
--   hexstrike_alerts         — Security alerts (auto-generated from critical findings)
--   hexstrike_targets        — Infrastructure targets registered for scanning
--
-- Idempotent: All CREATEs use IF NOT EXISTS. Safe to re-run.

-- ── 1. HEXSTRIKE FINDINGS ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hexstrike_findings (
    finding_id          TEXT PRIMARY KEY,
    scan_id             TEXT NOT NULL DEFAULT '',
    target_id           TEXT DEFAULT '',
    category            TEXT NOT NULL
                        CHECK (category IN (
                            'container_security',
                            'api_security',
                            'secrets_leak',
                            'pipeline_integrity',
                            'network_exposure',
                            'dependency_vuln',
                            'config_misconfig',
                            'auth_weakness'
                        )),
    severity            TEXT NOT NULL DEFAULT 'medium'
                        CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    detail              JSONB DEFAULT '{}'::jsonb,
    affected_resource   TEXT DEFAULT '',
    remediation         TEXT DEFAULT '',
    cve_id              TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'acknowledged', 'in_progress', 'resolved', 'false_positive')),
    source              TEXT DEFAULT 'hexstrike_scan',
    niche               TEXT DEFAULT '',
    metadata            JSONB DEFAULT '{}'::jsonb,
    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  public.hexstrike_findings IS 'Security findings discovered by hexstrike-ai scans';
COMMENT ON COLUMN public.hexstrike_findings.category IS 'container_security | api_security | secrets_leak | pipeline_integrity | network_exposure | dependency_vuln | config_misconfig | auth_weakness';
COMMENT ON COLUMN public.hexstrike_findings.severity IS 'critical | high | medium | low | info';

CREATE INDEX IF NOT EXISTS idx_hexstrike_findings_category
    ON public.hexstrike_findings(category);
CREATE INDEX IF NOT EXISTS idx_hexstrike_findings_severity
    ON public.hexstrike_findings(severity);
CREATE INDEX IF NOT EXISTS idx_hexstrike_findings_status
    ON public.hexstrike_findings(status);
CREATE INDEX IF NOT EXISTS idx_hexstrike_findings_scanned
    ON public.hexstrike_findings(discovered_at DESC);


-- ── 2. HEXSTRIKE SCANS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hexstrike_scans (
    scan_id             TEXT PRIMARY KEY,
    scan_type           TEXT NOT NULL
                        CHECK (scan_type IN (
                            'container_audit',
                            'api_probe',
                            'secrets_scan',
                            'pipeline_check',
                            'dependency_scan',
                            'full_scan'
                        )),
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'completed', 'failed', 'partial')),
    targets_scanned     INTEGER DEFAULT 0,
    findings_count      INTEGER DEFAULT 0,
    critical_count      INTEGER DEFAULT 0,
    high_count          INTEGER DEFAULT 0,
    medium_count        INTEGER DEFAULT 0,
    low_count           INTEGER DEFAULT 0,
    duration_seconds    FLOAT8 DEFAULT 0.0,
    summary             TEXT DEFAULT '',
    error               TEXT DEFAULT '',
    triggered_by        TEXT DEFAULT 'scheduler',
    metadata            JSONB DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

COMMENT ON TABLE public.hexstrike_scans IS 'Scan run history with coverage and finding counts';
COMMENT ON COLUMN public.hexstrike_scans.triggered_by IS 'scheduler | operator | webhook | container_event';

CREATE INDEX IF NOT EXISTS idx_hexstrike_scans_type
    ON public.hexstrike_scans(scan_type);
CREATE INDEX IF NOT EXISTS idx_hexstrike_scans_status
    ON public.hexstrike_scans(status);
CREATE INDEX IF NOT EXISTS idx_hexstrike_scans_started
    ON public.hexstrike_scans(started_at DESC);


-- ── 3. HEXSTRIKE ALERTS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hexstrike_alerts (
    alert_id            TEXT PRIMARY KEY,
    finding_id          TEXT REFERENCES public.hexstrike_findings(finding_id) ON DELETE CASCADE,
    severity            TEXT NOT NULL DEFAULT 'high',
    title               TEXT NOT NULL,
    description         TEXT DEFAULT '',
    affected_resource   TEXT DEFAULT '',
    remediation         TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'acknowledged', 'resolved', 'dismissed')),
    acknowledged_by     TEXT DEFAULT '',
    acknowledged_at     TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hexstrike_alerts_severity
    ON public.hexstrike_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_hexstrike_alerts_status
    ON public.hexstrike_alerts(status);
CREATE INDEX IF NOT EXISTS idx_hexstrike_alerts_finding
    ON public.hexstrike_alerts(finding_id);


-- ── 4. HEXSTRIKE TARGETS ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.hexstrike_targets (
    target_id           TEXT PRIMARY KEY,
    target_type         TEXT NOT NULL
                        CHECK (target_type IN (
                            'container',
                            'api_endpoint',
                            'environment',
                            'pipeline',
                            'dependency',
                            'network'
                        )),
    display_name        TEXT NOT NULL,
    identifier          TEXT NOT NULL,  -- container name, URL, env name, etc.
    labels              JSONB DEFAULT '[]'::jsonb,
    last_scanned_at     TIMESTAMPTZ,
    scan_interval_min   INTEGER DEFAULT 360,
    enabled             BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.hexstrike_targets IS 'Infrastructure targets registered for periodic security scanning';
COMMENT ON COLUMN public.hexstrike_targets.scan_interval_min IS 'Default 6 hours = 360 minutes';

CREATE INDEX IF NOT EXISTS idx_hexstrike_targets_type
    ON public.hexstrike_targets(target_type);
CREATE INDEX IF NOT EXISTS idx_hexstrike_targets_enabled
    ON public.hexstrike_targets(enabled);


-- ── 5. SEED DEFAULT TARGETS ────────────────────────────────────────
INSERT INTO public.hexstrike_targets (target_id, target_type, display_name, identifier, labels) VALUES
    ('TGT-ENV-001', 'environment', 'Empire Hub Environment', '/root/.env', '["production", "hub"]'::jsonb),
    ('TGT-CONT-001', 'container', 'Empire Hub Container', 'empire-hub', '["production", "hub", "docker"]'::jsonb),
    ('TGT-CONT-002', 'container', 'Empire Suite Gateway', 'empire-suite-gateway', '["production", "suite", "docker"]'::jsonb),
    ('TGT-CONT-003', 'container', 'Empire Synthetic Brain', 'empire-synthetic-brain', '["production", "brain", "docker"]'::jsonb),
    ('TGT-API-001', 'api_endpoint', 'Hub API Root', '/api/v1/', '["production", "hub", "api"]'::jsonb);
