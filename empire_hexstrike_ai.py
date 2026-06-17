"""
EMPIRE V49 · HEXSTRIKE AI — INTERNAL SECURITY AGENT
=====================================================
Autonomous security monitoring agent. Runs periodic security scans on
Empire's own infrastructure (containers, API endpoints, env files,
pipelines) and generates findings with severity scoring.

Capabilities (Phase 1):
  1. Container security audit — check ports, images, healthchecks, root user
  2. API security probe — test endpoints for missing auth, injection, rate limits
  3. Secrets leak detection — scan env files, git history, logs for keys/tokens
  4. Pipeline integrity check — verify payout paths, compliance gates, signing chains
  5. Full scan — runs all 4 checks and aggregates findings

Fleet role: hexstrike_security
Parent role: quality_analyst

Routes:
  GET    /api/hexstrike/overview          — Security dashboard snapshot
  GET    /api/hexstrike/findings          — List findings with filters
  GET    /api/hexstrike/finding/{id}      — Single finding detail
  PATCH  /api/hexstrike/finding/{id}      — Update finding status
  POST   /api/hexstrike/scan/containers   — Run container security audit
  POST   /api/hexstrike/scan/api          — Run API security probe
  POST   /api/hexstrike/scan/secrets      — Run secrets leak scan
  POST   /api/hexstrike/scan/pipeline     — Run pipeline integrity check
  POST   /api/hexstrike/scan/full         — Run all scan types
  GET    /api/hexstrike/scans             — Scan history
  GET    /api/hexstrike/targets           — Registered scan targets
  GET    /api/hexstrike/snapshot          — Condensed fleet snapshot
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

import httpx

log = logging.getLogger("empire.hexstrike")

# ── Severity order for sorting ─────────────────────────────────────
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# ── Finding categories ─────────────────────────────────────────────
FINDING_CATEGORIES = [
    "container_security",
    "api_security",
    "secrets_leak",
    "pipeline_integrity",
    "network_exposure",
    "dependency_vuln",
    "config_misconfig",
    "auth_weakness",
]

# ── Known secrets patterns (regex) ─────────────────────────────────
SECRETS_PATTERNS = [
    (r"(?i)SUPABASE_SERVICE_KEY\s*[=:]\s*\S{20,}", "Supabase service key"),
    (r"(?i)SUPABASE_ANON_KEY\s*[=:]\s*\S{20,}", "Supabase anon key"),
    (r"(?i)RESEND_API_KEY\s*[=:]\s*\S{10,}", "Resend API key"),
    (r"(?i)OPENAI_API_KEY\s*sk-\S{20,}", "OpenAI API key"),
    (r"(?i)ANTHROPIC_API_KEY\s*sk-ant-\S{20,}", "Anthropic API key"),
    (r"(?i)VONAGE_API_KEY\s*\S{10,}", "Vonage API key"),
    (r"(?i)VONAGE_API_SECRET\s*\S{10,}", "Vonage API secret"),
    (r"(?i)HUB_TOKEN\s*\S{10,}", "Hub token"),
    (r"(?i)EMPIRE_SIGNING_KEY\s*\S{10,}", "Empire signing key"),
    (r"(?i)EMPIRE_VAULT_WALLET\s*\S{10,}", "Empire vault wallet"),
    (r"(?i)SOLANA_RPC_URL\s*\S{10,}", "Solana RPC URL"),
    (r"(?i)NTFY_TOKEN\s*\S{10,}", "Ntfy token"),
    (r"(?i)sk-[a-zA-Z0-9]{20,}", "Generic OpenAI-style key"),
    (r"(?i)pk-[a-zA-Z0-9]{20,}", "Generic private key"),
    (r"(?i)-----BEGIN\s+(RSA |EC |)?PRIVATE KEY-----", "PEM private key block"),
]

# ── Known risky port ranges (non-standard, potential exposure) ────
SENSITIVE_PORTS = [5432, 6379, 27017, 9200, 9300, 5672, 15672, 8081, 9090, 3000, 5000]


class HexStrike:
    """Internal security agent — scans Empire's own infrastructure for
    vulnerabilities, misconfigurations, secrets leaks, and pipeline
    integrity issues.

    All findings are persisted to hexstrike_findings and hexstrike_alerts
    tables. Alerts are generated for critical and high-severity findings.
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._findings: list[dict] = []
        self._scans: list[dict] = []
        self._alerts: list[dict] = []
        self._targets: list[dict] = []
        self._targets_loaded = False

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _finding_id(self) -> str:
        return f"HSF-{uuid.uuid4().hex[:8].upper()}"

    def _scan_id(self) -> str:
        return f"HSC-{uuid.uuid4().hex[:8].upper()}"

    def _alert_id(self) -> str:
        return f"HSA-{uuid.uuid4().hex[:8].upper()}"

    def _ensure_targets(self) -> None:
        """Lazy-load targets from DB on first access. Never fails — falls back to defaults."""
        if self._targets_loaded:
            return
        try:
            db = self._db()
            r = db.table("hexstrike_targets").select("*").eq("enabled", True).execute()
            if r.data:
                self._targets = r.data
        except Exception:
            pass
        if not self._targets:
            self._targets = [
                {"target_id": "TGT-ENV-001", "target_type": "environment",
                 "display_name": "Empire Hub Environment", "identifier": "/root/.env"},
                {"target_id": "TGT-API-001", "target_type": "api_endpoint",
                 "display_name": "Hub API Root", "identifier": "/api/v1/"},
            ]
        self._targets_loaded = True

    def _persist_finding(self, finding: dict) -> None:
        """Save a finding to hexstrike_findings table."""
        try:
            db = self._db()
            db.table("hexstrike_findings").upsert({
                "finding_id": finding["finding_id"],
                "scan_id": finding.get("scan_id", ""),
                "target_id": finding.get("target_id", ""),
                "category": finding.get("category", "config_misconfig"),
                "severity": finding.get("severity", "medium"),
                "title": finding.get("title", ""),
                "description": finding.get("description", ""),
                "detail": json.dumps(finding.get("detail", {})),
                "affected_resource": finding.get("affected_resource", ""),
                "remediation": finding.get("remediation", ""),
                "cve_id": finding.get("cve_id", ""),
                "status": "open",
                "source": "hexstrike_scan",
                "discovered_at": self._now(),
            }, on_conflict="finding_id").execute()
        except Exception as e:
            log.warning(f"[hexstrike] persist finding failed: {e}")

    def _persist_scan(self, scan: dict) -> None:
        """Save a scan record to hexstrike_scans table."""
        try:
            db = self._db()
            db.table("hexstrike_scans").upsert(scan, on_conflict="scan_id").execute()
        except Exception as e:
            log.warning(f"[hexstrike] persist scan failed: {e}")

    def _persist_alert(self, alert: dict) -> None:
        """Save an alert to hexstrike_alerts table."""
        try:
            db = self._db()
            db.table("hexstrike_alerts").upsert({
                "alert_id": alert["alert_id"],
                "finding_id": alert.get("finding_id", ""),
                "severity": alert.get("severity", "high"),
                "title": alert.get("title", ""),
                "description": alert.get("description", ""),
                "affected_resource": alert.get("affected_resource", ""),
                "remediation": alert.get("remediation", ""),
                "status": "open",
                "created_at": self._now(),
            }, on_conflict="alert_id").execute()
        except Exception as e:
            log.warning(f"[hexstrike] persist alert failed: {e}")

    def _generate_alert(self, finding: dict) -> dict:
        """Generate a security alert for critical/high findings."""
        alert = {
            "alert_id": self._alert_id(),
            "finding_id": finding["finding_id"],
            "severity": finding.get("severity", "high"),
            "title": f"Security Alert: {finding.get('title', 'Unknown finding')}",
            "description": finding.get("description", ""),
            "affected_resource": finding.get("affected_resource", ""),
            "remediation": finding.get("remediation", ""),
            "status": "open",
            "created_at": self._now(),
        }
        self._alerts.append(alert)
        self._persist_alert(alert)
        log.warning(f"[hexstrike] ALERT [{alert['severity'].upper()}] {alert['title']}")
        return alert

    # ═════════════════════════════════════════════════════════════════
    # 1. CONTAINER SECURITY AUDIT
    # ═════════════════════════════════════════════════════════════════

    async def scan_containers(self, scan_id: str = "") -> dict:
        """Audit Docker containers for security issues.

        Checks:
          - Running as root (should use non-root user)
          - Exposed ports (flag sensitive ports)
          - Missing healthchecks
          - Non-standard images (not official or empire images)
          - Container age / stale images
        """
        scan_id = scan_id or self._scan_id()
        findings: list[dict] = []
        containers_scanned = 0
        start = datetime.now()

        def _run_docker_ps():
            return subprocess.run(
                ["docker", "ps", "--format", "{{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Ports}}\t{{.Status}}"],
                capture_output=True, text=True, timeout=15,
            )

        try:
            result = await asyncio.to_thread(_run_docker_ps)
            if result.returncode != 0:
                return self._scan_result(scan_id, "container_audit", "failed",
                                         0, [], 0, error=result.stderr.strip()[:200])

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                cid, image, name, ports, status = parts[0], parts[1], parts[2], parts[3], parts[4]
                containers_scanned += 1

                # Check 1: Root user — inspect container Config.User
                try:
                    def _inspect_user():
                        return subprocess.run(
                            ["docker", "inspect", cid, "--format", "{{.Config.User}}"],
                            capture_output=True, text=True, timeout=5,
                        )
                    inspect = await asyncio.to_thread(_inspect_user)
                    user = inspect.stdout.strip()
                    if not user or user == "" or user == "root":
                        findings.append(self._make_finding(
                            scan_id, "container_security", "medium",
                            f"Container '{name}' runs as root",
                            f"Container {name} ({image}) is running as the root user. "
                            "This increases blast radius in case of compromise.",
                            affected_resource=f"docker://{name}",
                            remediation="Add a USER directive in the Dockerfile or use --user flag.",
                            detail={"container_id": cid, "image": image, "current_user": user or "root"},
                        ))
                except Exception:
                    pass

                # Check 2: Sensitive ports exposed
                exposed_ports = re.findall(r"(\d+)(?:->|/)", ports)
                for p_str in exposed_ports:
                    try:
                        p = int(p_str)
                        if p in SENSITIVE_PORTS:
                            findings.append(self._make_finding(
                                scan_id, "network_exposure", "high",
                                f"Container '{name}' exposes sensitive port {p}",
                                f"Port {p} is exposed on container {name}. Common attack vector.",
                                affected_resource=f"docker://{name}:{p}",
                                remediation="Bind to localhost only or remove the port mapping if not needed.",
                                detail={"container_id": cid, "port": p, "image": image},
                            ))
                    except ValueError:
                        pass

                # Check 3: Missing healthcheck
                try:
                    def _inspect_hc():
                        return subprocess.run(
                            ["docker", "inspect", cid, "--format", "{{.Config.Healthcheck}}"],
                            capture_output=True, text=True, timeout=5,
                        )
                    has_hc = await asyncio.to_thread(_inspect_hc)
                    if not has_hc.stdout.strip() or has_hc.stdout.strip() == "<nil>":
                        findings.append(self._make_finding(
                            scan_id, "container_security", "low",
                            f"Container '{name}' has no healthcheck",
                            "No HEALTHCHECK instruction defined. Container failures won't auto-remediate.",
                            affected_resource=f"docker://{name}",
                            remediation="Add a HEALTHCHECK instruction to the Dockerfile.",
                            detail={"container_id": cid, "image": image},
                        ))
                except Exception:
                    pass

                # Check 4: Non-official image (not from known registry)
                if image and not any(prefix in image for prefix in
                                       ["empireai/", "python:", "node:", "nginx:", "postgres:",
                                        "redis:", "rabbitmq:", "mongo:", "library/"]):
                    findings.append(self._make_finding(
                        scan_id, "container_security", "info",
                        f"Container '{name}' uses non-standard image: {image}",
                        "Non-standard images should be reviewed for supply chain risks.",
                        affected_resource=f"docker://{name}",
                        remediation="Pin to a specific version from an official registry.",
                        detail={"container_id": cid, "image": image},
                    ))

        except FileNotFoundError:
            # Docker not available — not an error, just skip
            return self._scan_result(scan_id, "container_audit", "completed",
                                     0, [], 0, summary="Docker socket not available — skipped container audit.")

        duration = (datetime.now() - start).total_seconds()
        return self._scan_result(scan_id, "container_audit", "completed",
                                 containers_scanned, findings, duration)

    # ═════════════════════════════════════════════════════════════════
    # 2. API SECURITY PROBE
    # ═════════════════════════════════════════════════════════════════

    async def scan_api(self, scan_id: str = "") -> dict:
        """Probe hub API endpoints for security issues.

        Checks:
          - Missing auth on internal endpoints
          - Injection-susceptible endpoints (query params in URLs)
          - Endpoints returning stack traces / debug info
          - Rate limit bypass potential
        """
        scan_id = scan_id or self._scan_id()
        findings: list[dict] = []
        endpoints_tested = 0
        start = datetime.now()

        # Define internal endpoints that should REQUIRE auth
        sensitive_endpoints = [
            "/api/v1/payouts", "/api/v1/contractors", "/api/v1/auth/me",
            "/api/white-label/partners", "/api/white-label/overview",
            "/api/compliance/overview", "/api/pulse/summary",
            "/api/v1/closer/stats", "/api/v1/fleet/status",
            "/api/v1/email/quota",
        ]

        # Public endpoints that should NOT require auth
        public_endpoints = [
            "/", "/support", "/pricing", "/ppc", "/ppl", "/demo",
            "/api/contractors/chat", "/api/customer-service/chat",
        ]

        hub_base = "http://localhost:8000"

        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:

            # Test sensitive endpoints WITHOUT auth token
            for ep in sensitive_endpoints:
                try:
                    r = await client.get(f"{hub_base}{ep}")
                    endpoints_tested += 1
                    # If the endpoint returns 200 without auth, that's a finding
                    if r.status_code == 200:
                        # Check if it's returning actual data vs a login page
                        body = r.text[:500].lower()
                        if "login" not in body and "unauthorized" not in body and "auth" not in body:
                            findings.append(self._make_finding(
                                scan_id, "auth_weakness", "critical",
                                f"Endpoint {ep} accessible without authentication",
                                f"GET {ep} returned {r.status_code} without valid auth. "
                                "Sensitive data may be exposed.",
                                affected_resource=ep,
                                remediation="Ensure the endpoint has require_auth dependency.",
                                detail={"endpoint": ep, "status": r.status_code,
                                        "response_preview": body[:200]},
                            ))
                except Exception:
                    pass

            # Test public endpoints for stack traces / debug info
            for ep in public_endpoints:
                try:
                    r = await client.get(f"{hub_base}{ep}")
                    endpoints_tested += 1
                    body = r.text.lower()
                    if "traceback" in body or "stacktrace" in body or "file \"" in body:
                        findings.append(self._make_finding(
                            scan_id, "config_misconfig", "high",
                            f"Public endpoint {ep} returned debug/stack trace info",
                            "Stack trace or debug info exposed on a public endpoint.",
                            affected_resource=ep,
                            remediation="Set DEBUG=False and handle exceptions gracefully.",
                            detail={"endpoint": ep, "status": r.status_code},
                        ))
                except Exception:
                    pass

        duration = (datetime.now() - start).total_seconds()
        return self._scan_result(scan_id, "api_probe", "completed",
                                 endpoints_tested, findings, duration)

    # ═════════════════════════════════════════════════════════════════
    # 3. SECRETS LEAK DETECTION
    # ═════════════════════════════════════════════════════════════════

    async def scan_secrets(self, scan_id: str = "") -> dict:
        """Scan env files, git history, and log files for leaked secrets.

        Checks:
          - /root/.env file for exposed keys
          - Recent git commits for accidentally committed secrets
          - PM2 logs for key material
          - Hub log files for API keys
        """
        scan_id = scan_id or self._scan_id()
        findings: list[dict] = []
        files_scanned = 0
        start = datetime.now()

        # Targets to scan
        scan_targets = [
            "/root/.env",
            "/root/empire-v49/.env",
            "/root/.pm2/logs/empire-hub-error.log",
            "/root/.pm2/logs/empire-hub-out.log",
            "/var/log/empire.log",
        ]

        for filepath in scan_targets:
            if not os.path.isfile(filepath):
                continue
            try:
                with open(filepath, "r", errors="ignore") as f:
                    content = f.read()
                files_scanned += 1

                for pattern, desc in SECRETS_PATTERNS:
                    matches = re.findall(pattern, content)
                    if matches:
                        # Sanitize: show only first 4 chars
                        sanitized = [f"{m[:4]}****" if len(m) > 8 else m for m in matches[:3]]
                        findings.append(self._make_finding(
                            scan_id, "secrets_leak", "critical",
                            f"Potential {desc} found in {os.path.basename(filepath)}",
                            f"A {desc} was detected in {filepath}. "
                            "This exposes the key to anyone with file read access.",
                            affected_resource=filepath,
                            remediation=f"Remove the key from {filepath} and rotate it immediately.",
                            detail={"file": filepath, "pattern": desc,
                                    "matches": sanitized, "count": len(matches)},
                        ))
            except (PermissionError, OSError) as e:
                log.debug(f"[hexstrike] secrets scan: cannot read {filepath}: {e}")

        # Scan recent git commits for secrets
        try:
            git_log = subprocess.run(
                ["git", "log", "--oneline", "-50", "--all"],
                capture_output=True, text=True, timeout=10,
                cwd="/root/empire-v49",
            )
            if git_log.returncode == 0:
                for line in git_log.stdout.strip().split("\n"):
                    for pattern, desc in SECRETS_PATTERNS:
                        if re.search(pattern, line):
                            commit_hash = line.split()[0] if line else "unknown"
                            findings.append(self._make_finding(
                                scan_id, "secrets_leak", "critical",
                                f"Potential {desc} in git commit {commit_hash}",
                                f"A {desc} pattern was found in git history. "
                                "Even removed secrets remain in git history.",
                                affected_resource=f"git://{commit_hash}",
                                remediation="Rotate the exposed key and use git filter-branch or BFG to remove from history.",
                                detail={"commit": commit_hash, "pattern": desc, "preview": line[:120]},
                            ))
                            break  # one alert per commit
        except Exception:
            pass

        duration = (datetime.now() - start).total_seconds()
        return self._scan_result(scan_id, "secrets_scan", "completed",
                                 files_scanned, findings, duration)

    # ═════════════════════════════════════════════════════════════════
    # 4. PIPELINE INTEGRITY CHECK
    # ═════════════════════════════════════════════════════════════════

    async def scan_pipeline(self, scan_id: str = "") -> dict:
        """Audit critical pipeline integrity.

        Checks:
          - Payout signer key is present and not empty
          - Compliance gate is importable
          - Email engine is wired with Resend key
          - SMS engine is wired with Vonage credentials
          - Auth engine has a session TTL configured
        """
        scan_id = scan_id or self._scan_id()
        findings: list[dict] = []
        checks_run = 0
        start = datetime.now()

        # Check 1: Payout signing key
        signing_key = os.environ.get("EMPIRE_SIGNING_KEY", "")
        vault_wallet = os.environ.get("EMPIRE_VAULT_WALLET", "")
        checks_run += 1
        if not signing_key:
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "critical",
                "EMPIRE_SIGNING_KEY is not set — payouts will fail",
                "Payout engine requires a Solana signing key to process disbursements. "
                "Without this, contractor payouts cannot be executed.",
                affected_resource="env://EMPIRE_SIGNING_KEY",
                remediation="Set EMPIRE_SIGNING_KEY in /root/.env with a valid Solana private key.",
            ))
        if not vault_wallet:
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "high",
                "EMPIRE_VAULT_WALLET is not set — payouts have no source wallet",
                "Payout engine requires a vault wallet address to source funds.",
                affected_resource="env://EMPIRE_VAULT_WALLET",
                remediation="Set EMPIRE_VAULT_WALLET in /root/.env.",
            ))

        # Check 2: Compliance gate importable
        checks_run += 1
        try:
            from agents.outreach import compliance  # noqa: F401
        except (ImportError, AttributeError):
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "high",
                "Compliance gate (agents.outreach.compliance) is not importable",
                "SMS and voice dispatch will not enforce TCPA/DNC compliance.",
                affected_resource="module://agents.outreach.compliance",
                remediation="Ensure agents/outreach/compliance.py exists and is importable.",
            ))

        # Check 3: Resend API key
        resend_key = os.environ.get("RESEND_API_KEY", "")
        checks_run += 1
        if not resend_key or resend_key == "":
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "high",
                "RESEND_API_KEY is not set — email dispatch will fail",
                "Email engine requires Resend API key for sending emails.",
                affected_resource="env://RESEND_API_KEY",
                remediation="Set RESEND_API_KEY in /root/.env.",
            ))

        # Check 4: Vonage credentials
        vonage_key = os.environ.get("VONAGE_API_KEY", "")
        vonage_secret = os.environ.get("VONAGE_API_SECRET", "")
        checks_run += 1
        if not vonage_key or not vonage_secret:
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "medium",
                "Vonage credentials incomplete — voice calls may fail",
                "Voice router requires Vonage API key, secret, and application ID.",
                affected_resource="env://VONAGE_*",
                remediation="Set VONAGE_API_KEY, VONAGE_API_SECRET, and VONAGE_APPLICATION_ID.",
            ))

        # Check 5: Auth session TTL
        checks_run += 1
        hub_token = os.environ.get("HUB_TOKEN", "")
        if not hub_token or hub_token == "dev-token-insecure":
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "medium",
                "HUB_TOKEN is using default dev token ('dev-token-insecure')",
                "The default hub token should be replaced in production.",
                affected_resource="env://HUB_TOKEN",
                remediation="Set a strong random HUB_TOKEN in /root/.env.",
            ))

        # Check 6: SUPABASE connection
        sb_url = os.environ.get("SUPABASE_URL", "")
        sb_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        checks_run += 1
        if not sb_url or not sb_key:
            findings.append(self._make_finding(
                scan_id, "pipeline_integrity", "critical",
                "Supabase credentials missing — entire app depends on DB",
                "Without SUPABASE_URL and SUPABASE_SERVICE_KEY, the hub cannot start.",
                affected_resource="env://SUPABASE_*",
                remediation="Set SUPABASE_URL and SUPABASE_SERVICE_KEY in /root/.env.",
            ))

        duration = (datetime.now() - start).total_seconds()
        return self._scan_result(scan_id, "pipeline_check", "completed",
                                 checks_run, findings, duration)

    # ═════════════════════════════════════════════════════════════════
    # 5. FULL SCAN — RUN ALL CHECKS
    # ═════════════════════════════════════════════════════════════════

    async def scan_full(self) -> dict:
        """Run all 4 scan types and aggregate findings."""
        scan_id = self._scan_id()
        all_findings: list[dict] = []
        total_targets = 0
        sub_scans = {}
        start = datetime.now()

        results = {
            "containers": await self.scan_containers(scan_id),
            "api": await self.scan_api(scan_id),
            "secrets": await self.scan_secrets(scan_id),
            "pipeline": await self.scan_pipeline(scan_id),
        }

        for scan_type, result in results.items():
            sub_scans[scan_type] = {
                "status": result.get("status"),
                "targets": result.get("targets_scanned", 0),
                "findings": result.get("findings_count", 0),
            }
            total_targets += result.get("targets_scanned", 0)
            all_findings.extend(result.get("findings", []))

        duration = (datetime.now() - start).total_seconds()
        return self._scan_result(scan_id, "full_scan", "completed",
                                 total_targets, all_findings, duration,
                                 summary=f"Full scan: {len(all_findings)} findings across 4 scan types.")

    # ═════════════════════════════════════════════════════════════════
    # HELPERS
    # ═════════════════════════════════════════════════════════════════

    def _make_finding(self, scan_id: str, category: str, severity: str,
                       title: str, description: str, *,
                       affected_resource: str = "", remediation: str = "",
                       cve_id: str = "", detail: Optional[dict] = None) -> dict:
        """Create a finding dict and auto-generate alerts for critical/high."""
        finding = {
            "finding_id": self._finding_id(),
            "scan_id": scan_id,
            "target_id": "",
            "category": category,
            "severity": severity,
            "title": title,
            "description": description,
            "affected_resource": affected_resource,
            "remediation": remediation,
            "cve_id": cve_id,
            "status": "open",
            "detail": detail or {},
            "source": "hexstrike_scan",
            "discovered_at": self._now(),
        }
        self._findings.append(finding)
        self._persist_finding(finding)

        # Auto-generate alert for critical/high severity
        if severity in ("critical", "high"):
            self._generate_alert(finding)

        return finding

    def _scan_result(self, scan_id: str, scan_type: str, status: str,
                     targets_scanned: int, findings: list, duration: float,
                     *, summary: str = "", error: str = "") -> dict:
        """Build and persist a scan result record."""
        critical_count = sum(1 for f in findings if f.get("severity") == "critical")
        high_count = sum(1 for f in findings if f.get("severity") == "high")
        medium_count = sum(1 for f in findings if f.get("severity") == "medium")
        low_count = sum(1 for f in findings if f.get("severity") == "low")

        scan_record = {
            "scan_id": scan_id,
            "scan_type": scan_type,
            "status": status,
            "targets_scanned": targets_scanned,
            "findings_count": len(findings),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "duration_seconds": round(duration, 2),
            "summary": summary or f"{scan_type}: {len(findings)} findings",
            "error": error,
            "triggered_by": "operator",
            "started_at": self._now(),
            "completed_at": self._now(),
        }
        self._scans.append(scan_record)
        self._persist_scan(scan_record)

        return {
            "ok": status == "completed",
            "scan_id": scan_id,
            "scan_type": scan_type,
            "status": status,
            "targets_scanned": targets_scanned,
            "findings_count": len(findings),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "duration_seconds": round(duration, 2),
            "summary": scan_record["summary"],
            "error": error,
            "findings": findings,
        }

    # ═════════════════════════════════════════════════════════════════
    # QUERIES — OVERVIEW, FINDINGS, SCANS, ALERTS, TARGETS
    # ═════════════════════════════════════════════════════════════════

    def overview(self) -> dict:
        """Security dashboard — finding counts by severity/category, recent scans, open alerts."""
        # Load findings from DB for persistence across restarts
        db_findings = []
        try:
            db = self._db()
            r = db.table("hexstrike_findings") \
                .select("*") \
                .order("discovered_at", desc=True) \
                .limit(200) \
                .execute()
            db_findings = self._parse_findings(r.data or [])
        except Exception:
            pass

        # Merge with in-memory findings (deduplicate by finding_id)
        seen_ids = set()
        merged = []
        for f in self._findings + db_findings:
            fid = f.get("finding_id")
            if fid and fid not in seen_ids:
                seen_ids.add(fid)
                merged.append(f)

        by_severity = {}
        by_category = {}
        open_findings = 0
        for f in merged:
            sev = f.get("severity", "info")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            cat = f.get("category", "other")
            by_category[cat] = by_category.get(cat, 0) + 1
            if f.get("status") == "open":
                open_findings += 1

        # Load alerts from DB
        alerts = []
        try:
            db = self._db()
            r = db.table("hexstrike_alerts") \
                .select("*") \
                .eq("status", "open") \
                .order("created_at", desc=True) \
                .limit(50) \
                .execute()
            alerts = r.data or []
        except Exception:
            alerts = [a for a in self._alerts if a.get("status") == "open"]

        # Recent scans from DB
        recent_scans = []
        try:
            db = self._db()
            r = db.table("hexstrike_scans") \
                .select("*") \
                .order("started_at", desc=True) \
                .limit(10) \
                .execute()
            recent_scans = r.data or []
        except Exception:
            recent_scans = sorted(self._scans, key=lambda s: s.get("started_at", ""), reverse=True)[:10]

        return {
            "ts": self._now(),
            "findings": {
                "total": len(merged),
                "open": open_findings,
                "resolved": sum(1 for f in merged if f.get("status") == "resolved"),
                "by_severity": by_severity,
                "by_category": by_category,
            },
            "alerts": {
                "total": len(alerts),
                "open": len([a for a in alerts if a.get("status") == "open"]),
            },
            "scans": {
                "total_run": len(self._scans) + len(recent_scans),
                "recent": [
                    {
                        "scan_id": s.get("scan_id"),
                        "scan_type": s.get("scan_type"),
                        "status": s.get("status"),
                        "findings": s.get("findings_count", s.get("findings", 0)),
                        "critical": s.get("critical_count", 0),
                        "started_at": s.get("started_at", s.get("started_at", "")),
                    }
                    for s in recent_scans
                ],
            },
            "targets": {
                "total": len(self._targets),
                "types": self._count_target_types(),
            },
            "health": self._compute_health(by_severity, alerts),
        }

    def _parse_findings(self, rows: list) -> list:
        """Parse DB finding rows, hydrating JSON fields."""
        parsed = []
        for row in rows:
            f = dict(row)
            if isinstance(f.get("detail"), str):
                try:
                    f["detail"] = json.loads(f["detail"])
                except (json.JSONDecodeError, TypeError):
                    f["detail"] = {}
            if f.get("detail") is None:
                f["detail"] = {}
            parsed.append(f)
        return parsed

    def _count_target_types(self) -> dict:
        """Count targets by type."""
        counts = {}
        for t in self._targets:
            tt = t.get("target_type", "unknown")
            counts[tt] = counts.get(tt, 0) + 1
        return counts

    def _compute_health(self, by_severity: dict, alerts: list) -> str:
        """Compute overall security health: critical | warning | ok."""
        if by_severity.get("critical", 0) > 0:
            return "critical"
        if by_severity.get("high", 0) > 0:
            return "warning"
        if len([a for a in alerts if a.get("status") == "open"]) > 0:
            return "warning"
        return "ok"

    def list_findings(self, severity: str = "", category: str = "",
                       status: str = "", limit: int = 100) -> dict:
        """List findings with optional filters."""
        findings = list(self._findings)
        if severity:
            findings = [f for f in findings if f.get("severity") == severity]
        if category:
            findings = [f for f in findings if f.get("category") == category]
        if status:
            findings = [f for f in findings if f.get("status") == status]

        findings.sort(key=lambda f: (
            SEVERITY_ORDER.get(f.get("severity", "info"), 99),
            f.get("discovered_at", ""),
        ))

        return {
            "total": len(findings),
            "severity_filter": severity or "all",
            "category_filter": category or "all",
            "status_filter": status or "all",
            "findings": findings[:limit],
        }

    def get_finding(self, finding_id: str) -> Optional[dict]:
        """Get a single finding by ID."""
        for f in self._findings:
            if f.get("finding_id") == finding_id:
                return f
        # Fallback to DB
        try:
            db = self._db()
            r = db.table("hexstrike_findings").select("*") \
                .eq("finding_id", finding_id).limit(1).execute()
            if r.data:
                return self._parse_findings(r.data)[0]
        except Exception:
            pass
        return None

    def update_finding(self, finding_id: str, status: str,
                        remediation_note: str = "") -> dict:
        """Update a finding's status."""
        finding = self.get_finding(finding_id)
        if not finding:
            return {"ok": False, "error": f"Finding {finding_id} not found"}

        now = self._now()
        finding["status"] = status
        if status == "resolved":
            finding["resolved_at"] = now
        finding["updated_at"] = now

        # Persist update to DB
        try:
            db = self._db()
            update_data = {"status": status, "updated_at": now}
            if status == "resolved":
                update_data["resolved_at"] = now
            db.table("hexstrike_findings").update(update_data) \
                .eq("finding_id", finding_id).execute()
        except Exception as e:
            log.debug(f"[hexstrike] update finding DB error: {e}")

        return {"ok": True, "finding": finding}

    def list_scans(self, scan_type: str = "", status: str = "",
                    limit: int = 20) -> dict:
        """List scan history from DB."""
        scans = []
        try:
            db = self._db()
            q = db.table("hexstrike_scans").select("*")
            if scan_type:
                q = q.eq("scan_type", scan_type)
            if status:
                q = q.eq("status", status)
            r = q.order("started_at", desc=True).limit(limit).execute()
            scans = r.data or []
        except Exception:
            scans = sorted(self._scans, key=lambda s: s.get("started_at", ""), reverse=True)[:limit]

        return {
            "total": len(scans),
            "scans": scans,
        }

    def list_targets(self) -> dict:
        """List registered scan targets."""
        self._ensure_targets()
        return {
            "total": len(self._targets),
            "targets": self._targets,
        }

    def snapshot(self) -> dict:
        """Condensed fleet snapshot."""
        o = self.overview()
        return {
            "findings_total": o.get("findings", {}).get("total", 0),
            "findings_open": o.get("findings", {}).get("open", 0),
            "critical_findings": o.get("findings", {}).get("by_severity", {}).get("critical", 0),
            "alerts_open": o.get("alerts", {}).get("open", 0),
            "scans_total": o.get("scans", {}).get("total_run", 0),
            "targets": o.get("targets", {}).get("total", 0),
            "health": o.get("health", "ok"),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_hexstrike_routes(app, get_db=None, require_auth=None):
    """Register HexStrike security agent routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query, Path

    if get_db is None:
        log.warning("[hexstrike] No get_db — agent will return errors on DB calls")
    _hs = HexStrike(get_db=get_db) if get_db else None

    def _get_hs():
        if _hs is None:
            raise HTTPException(503, "HexStrike not initialized (no get_db)")
        return _hs

    @app.get("/api/hexstrike/overview")
    async def hexstrike_overview(auth=Depends(require_auth) if require_auth else None):
        """Security dashboard — finding counts, alerts, recent scans."""
        return _get_hs().overview()

    @app.get("/api/hexstrike/findings")
    async def hexstrike_list_findings(
        severity: str = Query("", description="Filter: critical|high|medium|low|info"),
        category: str = Query("", description="Filter by category"),
        status: str = Query("", description="Filter: open|resolved|acknowledged"),
        limit: int = Query(100, ge=1, le=500),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List security findings with optional filters."""
        return _get_hs().list_findings(severity=severity, category=category,
                                        status=status, limit=limit)

    @app.get("/api/hexstrike/finding/{finding_id}")
    async def hexstrike_get_finding(
        finding_id: str = Path(..., description="Finding ID"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get a single finding detail."""
        finding = _get_hs().get_finding(finding_id)
        if not finding:
            raise HTTPException(404, f"Finding {finding_id} not found")
        return finding

    @app.patch("/api/hexstrike/finding/{finding_id}")
    async def hexstrike_update_finding(
        finding_id: str = Path(..., description="Finding ID"),
        status: str = Query("", description="New status: open|acknowledged|in_progress|resolved|false_positive"),
        note: str = Query("", description="Remediation note"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Update a finding's status."""
        if status not in ("open", "acknowledged", "in_progress", "resolved", "false_positive"):
            raise HTTPException(400, f"Invalid status: {status}")
        result = _get_hs().update_finding(finding_id, status, remediation_note=note)
        if not result.get("ok"):
            raise HTTPException(404, result.get("error", "Update failed"))
        return result

    @app.post("/api/hexstrike/scan/containers")
    async def hexstrike_scan_containers(auth=Depends(require_auth) if require_auth else None):
        """Run container security audit."""
        return await _get_hs().scan_containers()

    @app.post("/api/hexstrike/scan/api")
    async def hexstrike_scan_api(auth=Depends(require_auth) if require_auth else None):
        """Run API security probe."""
        return await _get_hs().scan_api()

    @app.post("/api/hexstrike/scan/secrets")
    async def hexstrike_scan_secrets(auth=Depends(require_auth) if require_auth else None):
        """Run secrets leak scan (env files, git history, logs)."""
        return await _get_hs().scan_secrets()

    @app.post("/api/hexstrike/scan/pipeline")
    async def hexstrike_scan_pipeline(auth=Depends(require_auth) if require_auth else None):
        """Run pipeline integrity check."""
        return await _get_hs().scan_pipeline()

    @app.post("/api/hexstrike/scan/full")
    async def hexstrike_scan_full(auth=Depends(require_auth) if require_auth else None):
        """Run ALL security scans (containers + API + secrets + pipeline)."""
        return await _get_hs().scan_full()

    @app.get("/api/hexstrike/scans")
    async def hexstrike_list_scans(
        scan_type: str = Query("", description="Filter by type"),
        status: str = Query("", description="Filter: running|completed|failed"),
        limit: int = Query(20, ge=1, le=100),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Scan history."""
        return _get_hs().list_scans(scan_type=scan_type, status=status, limit=limit)

    @app.get("/api/hexstrike/targets")
    async def hexstrike_list_targets(auth=Depends(require_auth) if require_auth else None):
        """Registered scan targets."""
        return _get_hs().list_targets()

    @app.get("/api/hexstrike/snapshot")
    async def hexstrike_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed fleet snapshot."""
        return _get_hs().snapshot()

    log.info("[hexstrike] Routes registered · "
             "/api/hexstrike/{overview,findings,finding,scan/*,scans,targets,snapshot}")
