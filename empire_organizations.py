"""
EMPIRE V49 · ORGANIZATIONS (Multi-Tenant)
=========================================
Manages organizations — the tenant boundary for multi-tenant isolation.
Every operator belongs to an organization. All business data is scoped
to the operator's org via org_id columns and Supabase RLS.

Capabilities:
  - Organization CRUD (create, read, update, delete)
  - Per-org billing plan management
  - White-label branding config (logo, colors, fonts, domain)
  - Feature flag management per org
  - Operator → org membership
  - Org-level usage quotas and limits
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.organizations")


VALID_PLANS = {"free", "starter", "professional", "enterprise"}
VALID_STATUSES = {"active", "past_due", "canceled", "trialing"}


class OrganizationEngine:
    """Manage organizations — tenants that isolate operators and data."""

    def __init__(self, *, get_db: Callable):
        self.get_db = get_db
        self.stats = {
            "organizations_created": 0,
            "orgs_total": 0,
            "lookups": 0,
        }

    # ── HELPERS ─────────────────────────────────────────────────────

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── CRUD: CREATE ───────────────────────────────────────────────

    async def create_organization(
        self,
        *,
        name: str,
        slug: str,
        owner_operator_id: str = "",
        billing_plan: str = "free",
        domain: str = "",
        branding: Optional[dict] = None,
        features: Optional[dict] = None,
        max_operators: int = 5,
        max_leads_per_month: int = 1000,
    ) -> dict:
        """Create a new organization. Returns {ok, organization?, error?}."""
        slug = slug.lower().strip()
        if not slug or not re.match(r"^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$", slug):
            return {"ok": False, "error": "Invalid slug format"}
        if billing_plan not in VALID_PLANS:
            return {"ok": False, "error": f"Invalid plan: {billing_plan}"}

        try:
            db = self.get_db()
            now = self._now()
            org_id = str(uuid.uuid4())

            data = {
                "id": org_id,
                "name": name[:200],
                "slug": slug,
                "domain": domain[:255] if domain else None,
                "owner_id": owner_operator_id or None,
                "billing_plan": billing_plan,
                "billing_status": "active",
                "branding": branding or {},
                "features": features or {},
                "max_operators": max(1, min(max_operators, 100)),
                "max_leads_per_month": max(0, max_leads_per_month),
                "meta": {},
                "created_at": now,
                "updated_at": now,
            }
            db.table("organizations").insert(data).execute()

            self.stats["organizations_created"] += 1
            self.stats["orgs_total"] += 1

            log.info(f"[org] created {slug} · plan={billing_plan} · max_ops={max_operators}")
            return {"ok": True, "organization": data}
        except Exception as e:
            err = str(e)
            if "duplicate key" in err.lower() or "unique constraint" in err.lower():
                return {"ok": False, "error": f"Organization slug '{slug}' already exists"}
            log.error(f"[org] create failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── CRUD: READ ─────────────────────────────────────────────────

    async def get_organization(self, org_id: str) -> Optional[dict]:
        """Return an organization by ID."""
        self.stats["lookups"] += 1
        try:
            db = self.get_db()
            r = db.table("organizations").select("*").eq("id", org_id).limit(1).execute()
            return r.data[0] if r.data else None
        except Exception as e:
            log.error(f"[org] get failed: {e}")
            return None

    async def get_organization_by_slug(self, slug: str) -> Optional[dict]:
        """Return an organization by slug."""
        self.stats["lookups"] += 1
        try:
            db = self.get_db()
            r = db.table("organizations").select("*").eq("slug", slug).limit(1).execute()
            return r.data[0] if r.data else None
        except Exception as e:
            log.error(f"[org] get_by_slug failed: {e}")
            return None

    async def list_organizations(self, limit: int = 100, offset: int = 0) -> list:
        """Return all organizations."""
        try:
            db = self.get_db()
            r = db.table("organizations").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
            return r.data or []
        except Exception as e:
            log.error(f"[org] list failed: {e}")
            return []

    # ── CRUD: UPDATE ───────────────────────────────────────────────

    async def update_organization(
        self,
        org_id: str,
        *,
        name: Optional[str] = None,
        domain: Optional[str] = None,
        billing_plan: Optional[str] = None,
        billing_status: Optional[str] = None,
        branding: Optional[dict] = None,
        features: Optional[dict] = None,
        max_operators: Optional[int] = None,
        max_leads_per_month: Optional[int] = None,
        meta: Optional[dict] = None,
    ) -> dict:
        """Update organization fields. Returns {ok, organization?, error?}."""
        update = {"updated_at": self._now()}
        if name is not None:
            update["name"] = name[:200]
        if domain is not None:
            update["domain"] = domain[:255] or None
        if billing_plan is not None:
            if billing_plan not in VALID_PLANS:
                return {"ok": False, "error": f"Invalid plan: {billing_plan}"}
            update["billing_plan"] = billing_plan
        if billing_status is not None:
            if billing_status not in VALID_STATUSES:
                return {"ok": False, "error": f"Invalid status: {billing_status}"}
            update["billing_status"] = billing_status
        if branding is not None:
            update["branding"] = branding
        if features is not None:
            update["features"] = features
        if max_operators is not None:
            update["max_operators"] = max(1, min(max_operators, 100))
        if max_leads_per_month is not None:
            update["max_leads_per_month"] = max(0, max_leads_per_month)
        if meta is not None:
            existing = await self.get_organization(org_id)
            current_meta = (existing or {}).get("meta") or {}
            current_meta.update(meta)
            update["meta"] = current_meta

        try:
            db = self.get_db()
            db.table("organizations").update(update).eq("id", org_id).execute()
            return await self.get_organization(org_id)
        except Exception as e:
            log.error(f"[org] update failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── CRUD: DELETE ───────────────────────────────────────────────

    async def delete_organization(self, org_id: str) -> dict:
        """Soft-delete by setting billing_status to 'canceled'. Returns {ok, error?}."""
        try:
            db = self.get_db()
            db.table("organizations").update({
                "billing_status": "canceled",
                "updated_at": self._now(),
            }).eq("id", org_id).execute()

            # Deactivate operators in this org
            db.table("operators").update({"active": False}).eq("org_id", org_id).execute()

            log.info(f"[org] soft-deleted {org_id}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── BRANDING ───────────────────────────────────────────────────

    async def set_branding(self, org_id: str, branding: dict) -> dict:
        """Set white-label branding for an organization.
        branding fields: logo_url, primary_color, secondary_color, favicon, font_family, custom_css
        """
        valid_keys = {"logo_url", "primary_color", "secondary_color", "favicon",
                       "font_family", "custom_css", "accent_color", "bg_color"}
        cleaned = {k: v for k, v in branding.items() if k in valid_keys and isinstance(v, str)}
        return await self.update_organization(org_id, branding=cleaned)

    async def get_branding(self, org_id: str) -> dict:
        """Return branding config for an organization."""
        org = await self.get_organization(org_id)
        if not org:
            return {}
        branding = org.get("branding") or {}
        # Merge with defaults
        defaults = {
            "logo_url": "",
            "primary_color": "#44E5B8",
            "secondary_color": "#5AC8FA",
            "favicon": "",
            "font_family": "Inter, system-ui, sans-serif",
            "custom_css": "",
            "accent_color": "#44E5B8",
            "bg_color": "#0A1A2F",
            "org_name": org.get("name", "Empire AI"),
            "org_slug": org.get("slug", ""),
        }
        defaults.update(branding)
        return defaults

    # ── OPERATOR → ORG ─────────────────────────────────────────────

    async def add_operator_to_org(self, operator_id: str, org_id: str) -> dict:
        """Assign an operator to an organization."""
        try:
            db = self.get_db()
            db.table("operators").update({"org_id": org_id}).eq("id", operator_id).execute()
            log.info(f"[org] operator {operator_id} → org {org_id}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def get_org_operators(self, org_id: str) -> list:
        """Return all operators in an organization."""
        try:
            db = self.get_db()
            r = db.table("operators").select("id, email, name, role, active, last_login, created_at") \
                .eq("org_id", org_id).order("created_at", desc=False).execute()
            return r.data or []
        except Exception as e:
            log.error(f"[org] get_operators failed: {e}")
            return []

    # ── QUOTA / USAGE ──────────────────────────────────────────────

    async def check_quota(self, org_id: str) -> dict:
        """Check if an organization has exceeded its usage limits.
        Returns {ok, within_limits, operator_count, leads_this_month, max_operators, max_leads}
        """
        org = await self.get_organization(org_id)
        if not org:
            return {"ok": False, "error": "org not found"}

        ops = await self.get_org_operators(org_id)
        lead_count = await self._count_leads_this_month(org_id)

        max_ops = org.get("max_operators", 5)
        max_leads = org.get("max_leads_per_month", 1000)

        return {
            "ok": True,
            "within_limits": len(ops) <= max_ops and lead_count <= max_leads,
            "operator_count": len(ops),
            "leads_this_month": lead_count,
            "max_operators": max_ops,
            "max_leads_per_month": max_leads,
        }

    async def _count_leads_this_month(self, org_id: str) -> int:
        """Count leads created this month for an organization."""
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            r = db.table("radar_targets").select("id", count="exact") \
                .eq("org_id", org_id) \
                .gte("created_at", month_start) \
                .execute()
            return getattr(r, "count", 0) or len(r.data or [])
        except Exception:
            return 0

    # ── SNAPSHOT ───────────────────────────────────────────────────

    async def snapshot(self) -> dict:
        """Organization engine stats snapshot for the SPA."""
        orgs = await self.list_organizations(limit=500)
        active = [o for o in orgs if o.get("billing_status") in ("active", "trialing")]
        plan_counts = {}
        for o in orgs:
            p = o.get("billing_plan", "free")
            plan_counts[p] = plan_counts.get(p, 0) + 1

        return {
            "total_orgs": len(orgs),
            "active_orgs": len(active),
            "by_plan": plan_counts,
            "stats": self.stats,
        }


# ── FASTAPI ROUTE REGISTRATION ────────────────────────────────────────
def register_organization_routes(app, *, org_engine, require_auth, require_owner):
    """Register organization management API routes."""

    from fastapi import Request, HTTPException, Depends
    from fastapi.responses import JSONResponse

    # ── LIST ORGS ──────────────────────────────────────────────────
    @app.get("/api/v1/organizations")
    async def org_list(limit: int = 100, offset: int = 0, op: dict = Depends(require_owner)):
        orgs = await org_engine.list_organizations(limit=limit, offset=offset)
        return {"organizations": orgs, "count": len(orgs)}

    # ── GET ORG ────────────────────────────────────────────────────
    @app.get("/api/v1/organizations/{org_id}")
    async def org_get(org_id: str, op: dict = Depends(require_auth)):
        org = await org_engine.get_organization(org_id)
        if not org:
            raise HTTPException(404, "Organization not found")
        return org

    # ── GET ORG BY SLUG ────────────────────────────────────────────
    @app.get("/api/v1/organizations/by-slug/{slug}")
    async def org_get_by_slug(slug: str, op: dict = Depends(require_auth)):
        org = await org_engine.get_organization_by_slug(slug)
        if not org:
            raise HTTPException(404, "Organization not found")
        return org

    # ── CREATE ORG ─────────────────────────────────────────────────
    @app.post("/api/v1/organizations")
    async def org_create(request: Request, op: dict = Depends(require_owner)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        result = await org_engine.create_organization(
            name=body.get("name", ""),
            slug=body.get("slug", ""),
            owner_operator_id=op.get("id", ""),
            billing_plan=body.get("billing_plan", "free"),
            domain=body.get("domain", ""),
            branding=body.get("branding"),
            features=body.get("features"),
            max_operators=body.get("max_operators", 5),
            max_leads_per_month=body.get("max_leads_per_month", 1000),
        )
        if not result.get("ok"):
            status = 409 if "already exists" in (result.get("error") or "") else 400
            return JSONResponse(result, status_code=status)
        return result

    # ── UPDATE ORG ─────────────────────────────────────────────────
    @app.put("/api/v1/organizations/{org_id}")
    async def org_update(org_id: str, request: Request, op: dict = Depends(require_owner)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        result = await org_engine.update_organization(
            org_id,
            name=body.get("name"),
            domain=body.get("domain"),
            billing_plan=body.get("billing_plan"),
            billing_status=body.get("billing_status"),
            branding=body.get("branding"),
            features=body.get("features"),
            max_operators=body.get("max_operators"),
            max_leads_per_month=body.get("max_leads_per_month"),
            meta=body.get("meta"),
        )
        if isinstance(result, dict) and result.get("ok") is False:
            return JSONResponse(result, status_code=400)
        return result

    # ── DELETE ORG ─────────────────────────────────────────────────
    @app.delete("/api/v1/organizations/{org_id}")
    async def org_delete(org_id: str, op: dict = Depends(require_owner)):
        result = await org_engine.delete_organization(org_id)
        return result

    # ── BRANDING ───────────────────────────────────────────────────
    @app.get("/api/v1/organizations/{org_id}/branding")
    async def org_branding_get(org_id: str, op: dict = Depends(require_auth)):
        branding = await org_engine.get_branding(org_id)
        return branding

    @app.put("/api/v1/organizations/{org_id}/branding")
    async def org_branding_set(org_id: str, request: Request, op: dict = Depends(require_owner)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        result = await org_engine.set_branding(org_id, body)
        if isinstance(result, dict) and result.get("ok") is False:
            return JSONResponse(result, status_code=400)
        branding = await org_engine.get_branding(org_id)
        return branding

    # ── OPERATORS IN ORG ───────────────────────────────────────────
    @app.get("/api/v1/organizations/{org_id}/operators")
    async def org_operators_list(org_id: str, op: dict = Depends(require_owner)):
        operators = await org_engine.get_org_operators(org_id)
        return {"operators": operators, "count": len(operators)}

    @app.post("/api/v1/organizations/{org_id}/operators/{operator_id}")
    async def org_operators_add(org_id: str, operator_id: str, op: dict = Depends(require_owner)):
        result = await org_engine.add_operator_to_org(operator_id, org_id)
        return result

    # ── QUOTA ──────────────────────────────────────────────────────
    @app.get("/api/v1/organizations/{org_id}/quota")
    async def org_quota(org_id: str, op: dict = Depends(require_auth)):
        return await org_engine.check_quota(org_id)

    # ── SNAPSHOT ───────────────────────────────────────────────────
    @app.get("/api/v1/organizations/snapshot")
    async def org_snapshot(op: dict = Depends(require_owner)):
        return await org_engine.snapshot()

    # ── CURRENT ORG (from auth context) ────────────────────────────
    @app.get("/api/v1/organizations/me")
    async def org_current(op: dict = Depends(require_auth)):
        org_id = op.get("org_id")
        if not org_id:
            return {"organization": None}
        org = await org_engine.get_organization(org_id)
        if not org:
            return {"organization": None}
        branding = await org_engine.get_branding(org_id)
        return {"organization": org, "branding": branding}

    log.info("[org] Routes registered · /api/v1/organizations/*")
