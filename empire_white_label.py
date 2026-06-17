"""
EMPIRE V49 · WHITE LABEL MANAGER
===================================
Autonomous white-label partner management system. Manages reseller/partner
tiers, provisions Dockerized containers per partner, handles branding
configuration, revenue splits, and partner lifecycle.

Each partner gets:
  - Their own Docker container running the full Empire AI suite
  - Custom branding (logo, colors, domain)
  - Tier-based feature access and rate limits
  - Automated revenue split on their sub-accounts

Fleet parent: sales_director
Reseller Tiers:
  starter    → 1 container, basic branding, 80/20 split
  growth     → 3 containers, custom domain, 70/30 split
  enterprise → 10 containers, full branding, 60/40 split
  agency     → Unlimited containers, white-label, 50/50 split

Routes:
  GET   /api/white-label/overview       — Partner dashboard
  POST  /api/white-label/partner        — Register a new partner
  GET   /api/white-label/partners       — List all partners
  GET   /api/white-label/partner/{id}   — Partner detail
  PATCH /api/white-label/partner/{id}   — Update partner (tier, branding)
  POST  /api/white-label/partner/{id}/provision — Provision container
  POST  /api/white-label/partner/{id}/deploy    — Full deploy flow
  POST  /api/white-label/partner/{id}/suspend   — Suspend a partner
  GET   /api/white-label/tiers          — Available reseller tiers
  GET   /api/white-label/snapshot       — Fleet snapshot
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.white_label")

# ── Reseller/Partner Tiers ─────────────────────────────────────────
RESELLER_TIERS = {
    "starter": {
        "display_name": "Starter Partner",
        "description": "For small agencies testing white-label. 1 container, basic branding.",
        "max_containers": 1,
        "max_sub_accounts": 10,
        "branding_level": "basic",         # logo + colors only
        "custom_domain": False,
        "revenue_split_pct": 80,           # partner gets 80%
        "monthly_price_usd": 299,
        "features": ["basic_branding", "single_container", "email_support"],
        "support_level": "email",
    },
    "growth": {
        "display_name": "Growth Partner",
        "description": "For growing agencies. 3 containers, custom domain, priority support.",
        "max_containers": 3,
        "max_sub_accounts": 50,
        "branding_level": "custom_domain", # custom domain + logo + colors
        "custom_domain": True,
        "revenue_split_pct": 70,           # partner gets 70%
        "monthly_price_usd": 799,
        "features": ["custom_domain", "multi_container", "priority_support", "analytics"],
        "support_level": "priority",
    },
    "enterprise": {
        "display_name": "Enterprise Partner",
        "description": "For large agencies. 10 containers, full branding, API access.",
        "max_containers": 10,
        "max_sub_accounts": 200,
        "branding_level": "full",          # everything is rebrandable
        "custom_domain": True,
        "revenue_split_pct": 60,           # partner gets 60%
        "monthly_price_usd": 1999,
        "features": [
            "full_branding", "multi_container", "api_access",
            "dedicated_support", "analytics_dashboard", "custom_integrations",
        ],
        "support_level": "dedicated",
    },
    "agency": {
        "display_name": "Agency Partner",
        "description": "For top-tier agencies. Unlimited containers, full white-label, SLAs.",
        "max_containers": 999,
        "max_sub_accounts": 9999,
        "branding_level": "white_label",   # complete rebrand
        "custom_domain": True,
        "revenue_split_pct": 50,           # partner gets 50%
        "monthly_price_usd": 4999,
        "features": [
            "white_label", "unlimited_containers", "full_api",
            "sla_guarantee", "dedicated_manager", "custom_development",
            "early_access", "co_marketing",
        ],
        "support_level": "concierge",
    },
}

# ── Default branding template ──────────────────────────────────────
DEFAULT_BRANDING = {
    "primary_color": "#44E5B8",
    "secondary_color": "#0A0A0F",
    "logo_url": "",
    "favicon_url": "",
    "company_name": "",
    "company_tagline": "AI-Powered Lead Generation",
    "support_email": "",
    "custom_domain": "",
    "terms_url": "",
    "privacy_url": "",
    "theme": "dark",
}


class WhiteLabelManager:
    """Manages white-label partners — registration, tiering, container provisioning, branding.

    Persists all partners, containers, and provisioning logs to Supabase tables
    (white_label_partners, white_label_containers, white_label_provisioning_log).
    Also creates product_subscriptions entries for billing.
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── TIER DEFINITIONS ───────────────────────────────────────────

    def get_tiers(self) -> dict:
        """Return all available reseller tiers with details."""
        return {
            "ts": self._now(),
            "tiers": RESELLER_TIERS,
            "total": len(RESELLER_TIERS),
        }

    def _tier_config(self, tier: str) -> dict:
        """Get a tier config, falling back to starter."""
        return RESELLER_TIERS.get(tier, RESELLER_TIERS["starter"])

    def _db_upsert(self, table: str, data: dict, conflict_col: str = "partner_id", critical: bool = False):
        """Idempotent upsert into a Supabase table.

        Args:
            critical: If True, log failures at WARNING level so operators notice.
                      Use for partner registration and container provisioning.
        """
        try:
            db = self._db()
            db.table(table).upsert(data, on_conflict=conflict_col).execute()
        except Exception as e:
            level = log.warning if critical else log.debug
            level(f"[white_label] DB upsert failed ({table}): {e}")

    # ── PARTNER MANAGEMENT ─────────────────────────────────────────

    def register_partner(self, name: str, email: str,
                          tier: str = "starter",
                          company: str = "",
                          phone: str = "",
                          notes: str = "") -> dict:
        """Register a new white-label partner."""
        partner_id = f"WL-{uuid.uuid4().hex[:8].upper()}"
        tier_cfg = self._tier_config(tier)
        now = self._now()

        branding = {**DEFAULT_BRANDING, "company_name": company or name}

        partner = {
            "partner_id": partner_id,
            "name": name,
            "email": email,
            "company": company or name,
            "phone": phone,
            "tier": tier,
            "tier_display": tier_cfg["display_name"],
            "status": "active",
            "branding": json.dumps(branding),
            "containers_active": 0,
            "containers_max": tier_cfg["max_containers"],
            "sub_accounts": 0,
            "sub_accounts_max": tier_cfg["max_sub_accounts"],
            "revenue_split_pct": tier_cfg["revenue_split_pct"],
            "monthly_fee": tier_cfg["monthly_price_usd"],
            "features": json.dumps(list(tier_cfg["features"])),
            "support_level": tier_cfg["support_level"],
            "mrr": 0.0,
            "lifetime_revenue": 0.0,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        }

        # Persist to white_label_partners table
        self._db_upsert("white_label_partners", partner, critical=True)

        # Also create a product_subscription for billing
        try:
            db = self._db()
            db.table("product_subscriptions").upsert({
                "customer_account_id": partner_id,
                "tier_level": f"WHITE_LABEL_{tier.upper()}",
                "monthly_recurring_revenue": tier_cfg["monthly_price_usd"],
                "subscription_status": "ACTIVE",
                "notes": f"White-label partner: {company or name} ({tier})",
            }, on_conflict="customer_account_id").execute()
        except Exception as e:
            log.debug(f"[white_label] product_subscriptions upsert failed: {e}")

        # Return partner with parsed JSON fields
        partner["branding"] = branding
        partner["features"] = list(tier_cfg["features"])

        return {"ok": True, "partner": partner}

    def _parse_partner_row(self, row: dict) -> dict:
        """Parse a DB row into a dict with JSON fields hydrated."""
        p = dict(row)
        if isinstance(p.get("branding"), str):
            p["branding"] = json.loads(p["branding"])
        elif p.get("branding") is None:
            p["branding"] = dict(DEFAULT_BRANDING)
        if isinstance(p.get("features"), str):
            p["features"] = json.loads(p["features"])
        elif p.get("features") is None:
            p["features"] = []
        return p

    def _parse_container_row(self, row: dict) -> dict:
        """Parse a container DB row with JSON fields hydrated."""
        c = dict(row)
        if isinstance(c.get("env"), str):
            c["env"] = json.loads(c["env"])
        elif c.get("env") is None:
            c["env"] = {}
        if isinstance(c.get("docker_config"), str):
            c["docker_config"] = json.loads(c["docker_config"])
        elif c.get("docker_config") is None:
            c["docker_config"] = {}
        return c

    def list_partners(self, tier: str = "", status: str = "",
                       limit: int = 50) -> dict:
        """List all partners, optionally filtered."""
        try:
            db = self._db()
            query = db.table("white_label_partners").select("*") \
                .order("created_at", desc=True)
            if tier:
                query = query.eq("tier", tier)
            if status:
                query = query.eq("status", status)
            r = query.limit(limit).execute()
            rows = r.data or []
        except Exception as e:
            log.debug(f"[white_label] list_partners DB error: {e}")
            rows = []

        partners = [self._parse_partner_row(row) for row in rows]

        # Compute by_tier breakdown from DB
        by_tier = {}
        total_mrr = 0.0
        active_count = 0
        suspended_count = 0
        for p in partners:
            t = p.get("tier", "starter")
            by_tier[t] = by_tier.get(t, 0) + 1
            total_mrr += p.get("mrr", 0) or 0
            if p["status"] == "active":
                active_count += 1
            elif p["status"] == "suspended":
                suspended_count += 1

        return {
            "ts": self._now(),
            "total": len(partners),
            "by_tier": by_tier,
            "total_mrr": round(total_mrr, 2),
            "active_count": active_count,
            "suspended_count": suspended_count,
            "tier_filter": tier or "all",
            "status_filter": status or "all",
            "partners": partners[:limit],
        }

    def get_partner(self, partner_id: str) -> Optional[dict]:
        """Get a single partner by ID from DB."""
        try:
            db = self._db()
            r = db.table("white_label_partners").select("*") \
                .eq("partner_id", partner_id).limit(1).execute()
            if r.data:
                return self._parse_partner_row(r.data[0])
        except Exception as e:
            log.debug(f"[white_label] get_partner DB error: {e}")
        return None

    def update_partner(self, partner_id: str,
                        tier: str = "",
                        branding: Optional[dict] = None,
                        notes: str = "") -> dict:
        """Update a partner's tier, branding, or notes in DB."""
        partner = self.get_partner(partner_id)
        if not partner:
            return {"ok": False, "error": f"Partner {partner_id} not found"}

        update_data = {"updated_at": self._now()}

        if tier and tier in RESELLER_TIERS:
            tier_cfg = RESELLER_TIERS[tier]
            update_data.update({
                "tier": tier,
                "tier_display": tier_cfg["display_name"],
                "containers_max": tier_cfg["max_containers"],
                "sub_accounts_max": tier_cfg["max_sub_accounts"],
                "revenue_split_pct": tier_cfg["revenue_split_pct"],
                "monthly_fee": tier_cfg["monthly_price_usd"],
                "features": json.dumps(list(tier_cfg["features"])),
                "support_level": tier_cfg["support_level"],
            })

        if branding and isinstance(branding, dict):
            merged = {**partner.get("branding", {}), **branding}
            update_data["branding"] = json.dumps(merged)
            partner["branding"] = merged

        if notes:
            existing = partner.get("notes", "")
            update_data["notes"] = (existing + "\n" + notes).strip()

        try:
            db = self._db()
            db.table("white_label_partners").update(update_data) \
                .eq("partner_id", partner_id).execute()
        except Exception as e:
            log.debug(f"[white_label] update_partner DB error: {e}")

        # Reload to return fresh state
        updated = self.get_partner(partner_id)
        return {"ok": True, "partner": updated or partner}

    def suspend_partner(self, partner_id: str, reason: str = "") -> dict:
        """Suspend a partner's access."""
        partner = self.get_partner(partner_id)
        if not partner:
            return {"ok": False, "error": f"Partner {partner_id} not found"}

        now = self._now()
        update_data = {
            "status": "suspended",
            "suspended_at": now,
            "suspension_reason": reason,
            "updated_at": now,
        }

        try:
            db = self._db()
            db.table("white_label_partners").update(update_data) \
                .eq("partner_id", partner_id).execute()
            # Mark containers for shutdown
            db.table("white_label_containers").update({"status": "suspending"}) \
                .eq("partner_id", partner_id).eq("status", "running").execute()
        except Exception as e:
            log.debug(f"[white_label] suspend_partner DB error: {e}")

        return {"ok": True, "partner_id": partner_id, "status": "suspended"}

    # ── CONTAINER PROVISIONING ─────────────────────────────────────

    async def provision_container(self, partner_id: str) -> dict:
        """Provision a Docker container for a partner.

        Generates the docker-compose config for a partner-specific container
        with their branding, tier limits, and revenue split.
        Persists everything to DB.
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return {"ok": False, "error": f"Partner {partner_id} not found"}

        # Check container limit
        if partner["containers_active"] >= partner["containers_max"]:
            return {
                "ok": False,
                "error": f"Container limit reached ({partner['containers_max']}). "
                         f"Upgrade tier to increase limit.",
            }

        if partner["status"] == "suspended":
            return {"ok": False, "error": "Partner is suspended"}

        container_id = f"CTN-{uuid.uuid4().hex[:8].upper()}"
        now = self._now()

        # Determine next available port from max existing port + 1
        try:
            db = self._db()
            r = db.table("white_label_containers").select("port").order("port", desc=True).limit(1).execute()
            max_port = max((c.get("port") or 8100 for c in (r.data or [])), default=8100)
            port = max_port + 1
        except Exception:
            port = 8101
        port = max(port, 8101)

        # Build container env
        env_dict = {
            "PARTNER_ID": partner_id,
            "PARTNER_NAME": partner.get("company", partner["name"]),
            "BRAND_PRIMARY_COLOR": partner["branding"].get("primary_color", "#44E5B8"),
            "BRAND_SECONDARY_COLOR": partner["branding"].get("secondary_color", "#0A0A0F"),
            "BRAND_LOGO_URL": partner["branding"].get("logo_url", ""),
            "BRAND_FAVICON_URL": partner["branding"].get("favicon_url", ""),
            "BRAND_CUSTOM_DOMAIN": partner["branding"].get("custom_domain", ""),
            "TIER": partner["tier"],
            "REVENUE_SPLIT_PCT": str(partner["revenue_split_pct"]),
            "HUB_PORT": str(port),
        }

        docker_config = self._build_compose_config(partner, container_id, port)

        # Attempt actual Docker provisioning if Docker socket is available
        container_status = "provisioning"
        docker_container_name = ""
        docker_container_id = ""
        note = ""
        try:
            import subprocess
            container_name = f"empire-partner-{partner_id.lower()}-{uuid.uuid4().hex[:4]}"
            docker_args = [
                "docker", "run", "-d",
                "--name", container_name,
                "--restart", "unless-stopped",
                "--network", "empire-net",
                "-p", f"{port}:{port}",
            ]
            for k, v in env_dict.items():
                docker_args += ["-e", f"{k}={v}"]
            docker_args.append("empireai/hub:latest")

            result = subprocess.run(docker_args, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                container_status = "running"
                docker_container_name = container_name
                docker_container_id = result.stdout.strip()[:12]
        except Exception as e:
            log.debug(f"[white_label] Docker provision failed (expected without Docker): {e}")

        if container_status != "running":
            container_status = "config_generated"
            note = "Docker not available — compose config generated for manual deployment."

        # Persist container to DB
        container_record = {
            "container_id": container_id,
            "partner_id": partner_id,
            "partner_name": partner["name"],
            "status": container_status,
            "image": "empireai/hub:latest",
            "port": port,
            "docker_container_name": docker_container_name,
            "docker_container_id": docker_container_id,
            "env": json.dumps(env_dict),
            "docker_config": json.dumps(docker_config),
            "note": note,
            "created_at": now,
            "updated_at": now,
        }
        self._db_upsert("white_label_containers", container_record, conflict_col="container_id", critical=True)

        # Increment partner's container count
        try:
            db = self._db()
            db.table("white_label_partners").update({
                "containers_active": partner["containers_active"] + 1,
                "updated_at": now,
            }).eq("partner_id", partner_id).execute()
        except Exception as e:
            log.debug(f"[white_label] partner containers_active increment error: {e}")

        # Log provisioning action
        try:
            db = self._db()
            db.table("white_label_provisioning_log").insert({
                "partner_id": partner_id,
                "container_id": container_id,
                "action": "provision",
                "status": container_status,
                "detail": json.dumps({"port": port}),
            }).execute()
        except Exception as e:
            log.debug(f"[white_label] provisioning log insert error: {e}")

        # Build response container dict
        container_resp = {
            "container_id": container_id,
            "partner_id": partner_id,
            "partner_name": partner["name"],
            "status": container_status,
            "image": "empireai/hub:latest",
            "port": port,
            "env": env_dict,
            "docker_config": docker_config,
            "docker_container_name": docker_container_name,
            "docker_container_id": docker_container_id,
            "note": note,
            "created_at": now,
        }

        return {"ok": True, "container": container_resp}

    def _build_compose_config(self, partner: dict, container_id: str,
                               port: int) -> dict:
        """Build a docker-compose service definition for a partner."""
        return {
            "service_name": f"partner_{partner['partner_id'].lower()}",
            "image": "empireai/hub:latest",
            "container_name": f"empire-partner-{partner['partner_id'].lower()}",
            "ports": [f"{port}:{port}"],
            "environment": {
                "PARTNER_ID": partner["partner_id"],
                "PARTNER_NAME": partner.get("company", partner["name"]),
                "BRAND_PRIMARY_COLOR": partner["branding"].get("primary_color", "#44E5B8"),
                "BRAND_LOGO_URL": partner["branding"].get("logo_url", ""),
                "TIER": partner["tier"],
                "REVENUE_SPLIT_PCT": str(partner["revenue_split_pct"]),
                "HUB_PORT": str(port),
            },
            "restart": "unless-stopped",
            "networks": ["empire-net"],
        }

    def list_containers(self, partner_id: str = "", status: str = "") -> dict:
        """List provisioned containers from DB."""
        try:
            db = self._db()
            query = db.table("white_label_containers").select("*") \
                .order("created_at", desc=True)
            if partner_id:
                query = query.eq("partner_id", partner_id)
            if status:
                query = query.eq("status", status)
            r = query.execute()
            rows = r.data or []
        except Exception as e:
            log.debug(f"[white_label] list_containers DB error: {e}")
            rows = []

        containers = [self._parse_container_row(row) for row in rows]
        running = sum(1 for c in containers if c["status"] == "running")

        return {
            "ts": self._now(),
            "total": len(containers),
            "running": running,
            "containers": containers,
        }

    # ── FULL DEPLOY FLOW ──────────────────────────────────────────

    async def deploy_partner(self, name: str, email: str,
                              tier: str = "starter",
                              company: str = "",
                              phone: str = "",
                              branding: Optional[dict] = None,
                              notes: str = "") -> dict:
        """Full partner deploy flow: register → provision → config.

        One-call setup for a new white-label partner.
        """
        # Step 1: Register
        reg = self.register_partner(
            name=name, email=email, tier=tier,
            company=company, phone=phone, notes=notes,
        )
        if not reg.get("ok"):
            return reg

        partner = reg["partner"]

        # Step 2: Apply custom branding if provided
        if branding:
            self.update_partner(partner["partner_id"], branding=branding)

        # Step 3: Provision container
        prov = await self.provision_container(partner["partner_id"])

        return {
            "ok": True,
            "partner": partner,
            "provisioning": prov.get("container", {}),
            "deploy_instructions": self._deploy_instructions(partner, prov),
        }

    def _deploy_instructions(self, partner: dict, prov: dict) -> str:
        """Generate deploy instructions for a partner."""
        container = prov.get("container", {})
        port = container.get("port", "8100")
        domain = partner["branding"].get("custom_domain", "")

        parts = [
            f"Partner {partner['company']} deployed on tier {partner['tier']}.",
        ]
        if container.get("status") == "running":
            parts.append(f"Container running on port {port}.")
            if domain:
                parts.append(f"Custom domain: {domain}")
        else:
            parts.append(f"Container config generated (port {port}).")
            parts.append(f"Deploy manually:")
            parts.append(f"  docker compose -f /root/empire-v49/docker-compose.yml up -d partner_{partner['partner_id'].lower()}")

        parts.append(f"Revenue split: {partner['revenue_split_pct']}% to partner")
        parts.append(f"Monthly fee: ${partner['monthly_fee']}/mo")

        return "\n".join(parts)

    # ── OVERVIEW ──────────────────────────────────────────────────

    def _get_predictive_context(self) -> dict:
        """Fetch predictive revenue context for the partner ecosystem."""
        try:
            from bots import predictive_revenue
            forecast = predictive_revenue.per_lane_forecast() or {}
            totals = forecast.get("totals", {})
            health = predictive_revenue.revenue_health_check() or {}

            # Sum partner MRR from DB
            partner_mrr = self._sum_partner_mrr()
            ecosystem_mrr = totals.get("mrr_projected", 0)

            return {
                "ecosystem_mrr_projected": round(ecosystem_mrr, 2),
                "partner_mrr_current": round(partner_mrr, 2),
                "partner_share_pct": round(
                    partner_mrr / max(ecosystem_mrr, 1) * 100, 1
                ),
                "revenue_24h": totals.get("revenue_24h", 0),
                "health_status": health.get("status", "unknown"),
            }
        except Exception as e:
            log.debug(f"[white_label] predictive cloud unavailable: {e}")
            return {
                "ecosystem_mrr_projected": 0,
                "partner_mrr_current": self._sum_partner_mrr(),
                "partner_share_pct": 0,
                "revenue_24h": 0,
                "health_status": "unknown",
            }

    def _sum_partner_mrr(self) -> float:
        """Sum monthly_fee for all active partners from DB."""
        try:
            db = self._db()
            r = db.table("white_label_partners").select("monthly_fee").eq("status", "active").execute()
            return sum(float(p.get("monthly_fee", 0) or 0) for p in (r.data or []))
        except Exception:
            return 0.0

    def overview(self) -> dict:
        """Dashboard — partners, containers, revenue, tier breakdown — all from DB."""
        # Fetch all partners from DB
        try:
            db = self._db()
            pr = db.table("white_label_partners").select("*").execute()
            partners = [self._parse_partner_row(p) for p in (pr.data or [])]
            cr = db.table("white_label_containers").select("*").execute()
            containers = [self._parse_container_row(c) for c in (cr.data or [])]
        except Exception as e:
            log.debug(f"[white_label] overview DB error: {e}")
            partners = []
            containers = []

        active_partners = len([p for p in partners if p["status"] == "active"])
        running_containers = len([c for c in containers if c["status"] == "running"])

        total_mrr = sum(float(p.get("monthly_fee", 0) or 0) for p in partners)
        total_revenue = sum(float(p.get("lifetime_revenue", 0) or 0) for p in partners)

        # Predictive cloud context
        pred = self._get_predictive_context()

        by_tier = {}
        for t in RESELLER_TIERS:
            by_tier[t] = {
                "total": len([p for p in partners if p["tier"] == t]),
                "mrr": sum(float(p.get("monthly_fee", 0) or 0) for p in partners if p["tier"] == t),
            }

        # Container utilization
        container_usage = {}
        for p in partners:
            t = p["tier"]
            if t not in container_usage:
                container_usage[t] = {"used": 0, "max": 0}
            container_usage[t]["used"] += p["containers_active"]
            container_usage[t]["max"] += p["containers_max"]

        # Recent provisioning activity from DB
        recent = []
        try:
            db = self._db()
            lr = db.table("white_label_provisioning_log") \
                .select("*").order("created_at", desc=True).limit(10).execute()
            for row in (lr.data or []):
                recent.append({
                    "action": row.get("action", ""),
                    "partner_id": row.get("partner_id", ""),
                    "container_id": row.get("container_id", ""),
                    "timestamp": row.get("created_at", ""),
                    "status": row.get("status", ""),
                })
        except Exception:
            pass

        return {
            "ts": self._now(),
            "predictive_cloud": pred,
            "partners": {
                "total": len(partners),
                "active": active_partners,
                "suspended": len([p for p in partners if p["status"] == "suspended"]),
                "by_tier": by_tier,
            },
            "containers": {
                "total": len(containers),
                "running": running_containers,
                "config_generated": len([c for c in containers if c["status"] == "config_generated"]),
                "utilization": container_usage,
            },
            "revenue": {
                "total_mrr": round(total_mrr, 2),
                "lifetime_revenue": round(total_revenue, 2),
                "avg_mrr_per_partner": round(
                    total_mrr / max(len(partners), 1), 2
                ),
            },
            "tiers_available": list(RESELLER_TIERS.keys()),
            "recent_provisioning": recent,
        }

    def snapshot(self) -> dict:
        """Condensed fleet snapshot."""
        o = self.overview()
        return {
            "total_partners": o.get("partners", {}).get("total", 0),
            "active_partners": o.get("partners", {}).get("active", 0),
            "containers_running": o.get("containers", {}).get("running", 0),
            "total_mrr": o.get("revenue", {}).get("total_mrr", 0),
            "tiers_available": len(o.get("tiers_available", [])),
            "modified": self._now(),
        }


# ── CLI ENTRY POINT ──────────────────────────────────────────────────────

if __name__ == "__main__":
    """CLI for provisioning partners.

    Usage:
      python3 empire_white_label.py provision --name "Acme" --email "ceo@acme.com" --tier growth
      python3 empire_white_label.py list
      python3 empire_white_label.py tiers
    """
    import argparse

    parser = argparse.ArgumentParser(description="Empire AI White-Label Manager")
    sub = parser.add_subparsers(dest="command")

    # provision
    prov = sub.add_parser("provision", help="Register and deploy a new partner")
    prov.add_argument("--name", required=True)
    prov.add_argument("--email", required=True)
    prov.add_argument("--company", default="")
    prov.add_argument("--tier", default="starter", choices=list(RESELLER_TIERS.keys()))
    prov.add_argument("--phone", default="")
    prov.add_argument("--logo", default="", help="URL to partner logo")
    prov.add_argument("--color", default="#44E5B8", help="Brand primary color")
    prov.add_argument("--domain", default="", help="Custom domain")

    # list
    sub.add_parser("list", help="List all partners")

    # tiers
    sub.add_parser("tiers", help="Show available tiers")

    args = parser.parse_args()

    if args.command == "provision":
        import asyncio
        wl = WhiteLabelManager(get_db=lambda: None)  # no DB in CLI mode

        async def _provision():
            branding = {}
            if args.logo:
                branding["logo_url"] = args.logo
            if args.color:
                branding["primary_color"] = args.color
            if args.domain:
                branding["custom_domain"] = args.domain

            result = await wl.deploy_partner(
                name=args.name, email=args.email, tier=args.tier,
                company=args.company, phone=args.phone,
                branding=branding if branding else None,
            )
            print(json.dumps(result, indent=2))

        asyncio.run(_provision())

    elif args.command == "list":
        wl = WhiteLabelManager(get_db=lambda: None)
        print(json.dumps(wl.list_partners(), indent=2))

    elif args.command == "tiers":
        print(json.dumps(RESELLER_TIERS, indent=2))

    else:
        parser.print_help()


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_white_label_routes(app, get_db=None, require_auth=None):
    """Register White Label Manager routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query, Path

    if get_db is None:
        log.warning("[white_label] No get_db — agent will return errors on DB calls")
    _wl = WhiteLabelManager(get_db=get_db) if get_db else None

    def _get_wl():
        if _wl is None:
            raise HTTPException(503, "White Label Manager not initialized (no get_db)")
        return _wl

    @app.get("/api/white-label/overview")
    async def wl_overview(auth=Depends(require_auth) if require_auth else None):
        """Partner dashboard — partners, containers, revenue, tier breakdown."""
        return _get_wl().overview()

    @app.get("/api/white-label/tiers")
    async def wl_tiers(auth=Depends(require_auth) if require_auth else None):
        """Available reseller/partner tiers."""
        return _get_wl().get_tiers()

    @app.post("/api/white-label/partner")
    async def wl_register_partner(
        name: str = Query(..., description="Partner contact name"),
        email: str = Query(..., description="Partner email"),
        tier: str = Query("starter", description=f"Tier: {'|'.join(RESELLER_TIERS.keys())}"),
        company: str = Query("", description="Company name"),
        phone: str = Query("", description="Phone"),
        notes: str = Query("", description="Notes"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Register a new white-label partner."""
        result = _get_wl().register_partner(
            name=name, email=email, tier=tier,
            company=company, phone=phone, notes=notes,
        )
        return result

    @app.get("/api/white-label/partners")
    async def wl_list_partners(
        tier: str = Query("", description="Filter by tier"),
        status: str = Query("", description="Filter: active|suspended"),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List all white-label partners."""
        return _get_wl().list_partners(tier=tier, status=status, limit=limit)

    @app.get("/api/white-label/partner/{partner_id}")
    async def wl_get_partner(
        partner_id: str = Path(..., description="Partner ID"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get a single partner's details."""
        partner = _get_wl().get_partner(partner_id)
        if not partner:
            raise HTTPException(404, f"Partner {partner_id} not found")
        return partner

    @app.patch("/api/white-label/partner/{partner_id}")
    async def wl_update_partner(
        partner_id: str = Path(..., description="Partner ID"),
        tier: str = Query("", description="Upgrade/downgrade tier"),
        primary_color: str = Query("", description="Brand primary color"),
        logo_url: str = Query("", description="Brand logo URL"),
        custom_domain: str = Query("", description="Custom domain"),
        notes: str = Query("", description="Notes"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Update a partner's tier and/or branding."""
        wl = _get_wl()
        branding = {}
        if primary_color:
            branding["primary_color"] = primary_color
        if logo_url:
            branding["logo_url"] = logo_url
        if custom_domain:
            branding["custom_domain"] = custom_domain

        result = wl.update_partner(
            partner_id=partner_id, tier=tier if tier else "",
            branding=branding if branding else None,
            notes=notes,
        )
        status = 200 if result.get("ok") else 404
        return result

    @app.post("/api/white-label/partner/{partner_id}/provision")
    async def wl_provision_container(
        partner_id: str = Path(..., description="Partner ID"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Provision a Docker container for a partner."""
        result = await _get_wl().provision_container(partner_id)
        status = 200 if result.get("ok") else 400
        return result

    @app.post("/api/white-label/partner/{partner_id}/deploy")
    async def wl_deploy_partner(
        partner_id: str = Path(..., description="Partner ID (omit to register + deploy)"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Deprecated — use /api/white-label/partner POST then provision separately."""
        return {"ok": False, "error": "Use POST /api/white-label/partner then POST /api/white-label/partner/{id}/provision"}

    @app.post("/api/white-label/partner/{partner_id}/suspend")
    async def wl_suspend_partner(
        partner_id: str = Path(..., description="Partner ID"),
        reason: str = Query("", description="Suspension reason"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Suspend a partner's access."""
        result = _get_wl().suspend_partner(partner_id, reason=reason)
        status = 200 if result.get("ok") else 404
        return result

    @app.get("/api/white-label/containers")
    async def wl_containers(
        partner_id: str = Query("", description="Filter by partner"),
        status: str = Query("", description="Filter: running|config_generated|suspending"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List provisioned containers."""
        return _get_wl().list_containers(partner_id=partner_id, status=status)

    @app.get("/api/white-label/snapshot")
    async def wl_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed fleet snapshot."""
        return _get_wl().snapshot()

    log.info("[white_label] Routes registered · /api/white-label/{overview,tiers,partner,partners,containers,snapshot}")
