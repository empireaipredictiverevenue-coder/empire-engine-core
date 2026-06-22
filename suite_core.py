"""
EMPIRE V49 · UNIFIED MULTI-PRODUCT MRR SUITE CORE
==================================================
Productizes multi-product subscriptions under a single subscription + feature-flag
gatekeeping system. Supports two runtime modes:

  1. **Standalone** (uvicorn on port 8040) — independent gateway, used by
     external API consumers who don't go through the main hub.

  2. **Integrated** (wired into hub.py) — routes auto-register on the main
     API so the Empire command SPA and internal subsystems call the same
     gatecheck/entitlement logic without an extra hop.

Architecture:
    suite_core.py (this file)
        │
        ├─ SuiteSubscriptionEngine  — manage subscriptions, caps, billing
        ├─ SuiteGuard               — feature-flag gatecheck + usage metering
        └─ register_suite_routes()  — wire FastAPI routes into any app
            │
            ├─ POST /api/v6/suite/gatecheck   — entitlement check
            ├─ POST /api/v6/suite/usage/log   — record a usage event
            ├─ GET  /api/v6/suite/usage       — usage summary
            ├─ GET  /api/v6/suite/subscriptions      — list subscriptions
            ├─ POST /api/v6/suite/subscriptions      — create subscription
            ├─ POST /api/v6/suite/subscriptions/{id}/update — update status
            ├─ GET  /api/v6/suite/stats        — suite-wide stats snapshot
            └─ GET  /api/v6/suite/health       — simple health check

DATA STORE: Supabase (postgrest)
  - product_subscriptions   — tiers, MRR, billing periods
  - product_feature_flags   — per-account feature entitlements
  - product_usage_log       — usage metering events for billing
"""

import json as _json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger("empire.suite")

VALID_TIERS = {"ROUTER_SaaS", "DATA_ENTERPRISE", "SPY_DATA", "ALL_ACCESS",
                "SEO_STARTER", "SEO_GROWTH", "SEO_PRO",
                "LEADSCORE_STARTER", "LEADSCORE_GROWTH", "LEADSCORE_ENTERPRISE",
                "COMPLIANT_STARTER", "COMPLIANT_GROWTH", "COMPLIANT_ENTERPRISE",
                "STRIKE_STARTER", "STRIKE_GROWTH", "STRIKE_ENTERPRISE",
                "FORECAST_LITE", "FORECAST_PRO", "FORECAST_ENTERPRISE",
                "MARKET_EYE_STARTER", "MARKET_EYE_GROWTH", "MARKET_EYE_ENTERPRISE",
                "CONTENT_PULSE_STARTER", "CONTENT_PULSE_GROWTH", "CONTENT_PULSE_ENTERPRISE",
                "CONTRACTOR_EXCHANGE_STARTER", "CONTRACTOR_EXCHANGE_GROWTH", "CONTRACTOR_EXCHANGE_ENTERPRISE",
                "HEXSTRIKE_STARTER", "HEXSTRIKE_GROWTH", "HEXSTRIKE_ENTERPRISE",
                "ANALYZER_LITE", "ANALYZER_GROWTH", "ANALYZER_ENTERPRISE",
                "MEETILY_STARTER", "MEETILY_PRO", "MEETILY_ENTERPRISE",
                "SCRAPER_STARTER", "SCRAPER_PRO", "SCRAPER_ENTERPRISE",
                "CLOSER_STARTER", "CLOSER_PRO", "CLOSER_ENTERPRISE", "EXECUTIVE_WHALE"}
VALID_PRODUCTS = {"inbound_router", "data_vault", "buyer_spy", "seo_optimizer", "lead_score", "compliant", "strike_campaigns", "forecast", "market_eye", "content_pulse", "contractor_exchange", "hexstrike", "analyzer", "meetily", "elite_scraper", "ai_closer"}
VALID_STATUSES = {"ACTIVE", "PAST_DUE", "CANCELED", "TRIALING"}

# ── Feature flag column mapping ──────────────────────────────────
# Core flags: columns that exist in Supabase product_feature_flags
# (migration 018). Extended flags are stored in the `meta` JSONB
# column to avoid schema drift across later product migrations.
CORE_FLAG_COLUMNS = {
    "inbound_router_enabled", "data_retention_enabled", "buyer_spy_enabled",
    "omni_bridge_enabled", "agent_orchestrator_enabled", "b2b_pro_enabled",
    "inbound_router_max_calls", "data_retention_days", "buyer_spy_analyze_per_day",
}


# ═════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═════════════════════════════════════════════════════════════════════════

class GatecheckPayload(BaseModel):
    customer_account_id: str
    feature_requested: str  # 'inbound_router' | 'data_vault' | 'buyer_spy'


class UsageLogPayload(BaseModel):
    customer_account_id: str
    product_name: str       # 'inbound_router' | 'data_vault' | 'buyer_spy'
    usage_event: str        # e.g. 'inbound_call', 'data_upload', 'spy_analysis'
    quantity: int = 1
    unit: str = "count"
    metadata: dict = {}


class SubscriptionCreatePayload(BaseModel):
    customer_account_id: str
    tier_level: str         # 'ROUTER_SaaS' | 'DATA_ENTERPRISE' | 'SPY_DATA' | 'ALL_ACCESS'
    monthly_recurring_revenue: float = 0.0
    billing_anchor_day: int = 1
    notes: str = ""


class SubscriptionUpdatePayload(BaseModel):
    subscription_status: Optional[str] = None
    tier_level: Optional[str] = None
    monthly_recurring_revenue: Optional[float] = None


# ═════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION ENGINE  (Supabase)
# ═════════════════════════════════════════════════════════════════════════

class SuiteSubscriptionEngine:
    """Manage product subscriptions: CRUD, status transitions, period tracking.

    All state lives in Supabase. No local SQLite dependency."""

    def __init__(self, get_db: Callable):
        self._get_db = get_db
        self.stats = {"created": 0, "lookups": 0, "errors": 0}

    # ── QUERIES ──────────────────────────────────────────────────────

    def get_subscription(self, account_id: str) -> Optional[dict]:
        """Return a single subscription by customer_account_id."""
        try:
            db = self._get_db()
            r = db.table("product_subscriptions") \
                .select("*") \
                .eq("customer_account_id", account_id) \
                .limit(1) \
                .execute()
            self.stats["lookups"] += 1
            return dict(r.data[0]) if r.data else None
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[suite.subs] lookup error: {e}")
            return None

    def get_subscription_by_id(self, sub_id: str) -> Optional[dict]:
        """Return a single subscription by subscription_id."""
        try:
            db = self._get_db()
            r = db.table("product_subscriptions") \
                .select("*") \
                .eq("subscription_id", sub_id) \
                .limit(1) \
                .execute()
            return dict(r.data[0]) if r.data else None
        except Exception:
            return None

    def list_subscriptions(
        self, tier: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        """Return all subscriptions, optionally filtered."""
        try:
            db = self._get_db()
            query = db.table("product_subscriptions").select("*")
            if tier and tier in VALID_TIERS:
                query = query.eq("tier_level", tier)
            if status and status in VALID_STATUSES:
                query = query.eq("subscription_status", status)
            query = query.order("created_at", desc=True)
            r = query.execute()
            return [dict(row) for row in (r.data or [])]
        except Exception as e:
            self.stats["errors"] += 1
            return []

    # ── MUTATIONS ────────────────────────────────────────────────────

    def create_subscription(
        self,
        customer_account_id: str,
        tier_level: str,
        monthly_recurring_revenue: float = 0.0,
        billing_anchor_day: int = 1,
        notes: str = "",
        stripe_customer_id: str = "",
        stripe_subscription_id: str = "",
    ) -> dict:
        """Create a new product subscription. Idempotent — returns existing
        subscription if one already exists for this account."""
        tier_level = tier_level.upper()
        if tier_level not in VALID_TIERS:
            return {"ok": False, "error": f"Invalid tier: {tier_level}"}

        # Check for existing subscription
        existing = self.get_subscription(customer_account_id)
        if existing:
            return {
                "ok": False,
                "error": "Account already has a subscription",
                "existing": existing,
            }

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="seconds")

        try:
            db = self._get_db()
            r = db.table("product_subscriptions").insert({
                "customer_account_id": customer_account_id,
                "tier_level": tier_level,
                "subscription_status": "ACTIVE",
                "monthly_recurring_revenue": monthly_recurring_revenue,
                "billing_anchor_day": max(1, min(28, billing_anchor_day)),
                "current_period_start": now,
                "current_period_end": period_end,
                "notes": notes[:500] if notes else "",
                "stripe_customer_id": stripe_customer_id or None,
                "stripe_subscription_id": stripe_subscription_id or None,
                "created_at": now,
                "updated_at": now,
            }).execute()

            sub_id = r.data[0]["subscription_id"] if r.data else None
            self.stats["created"] += 1

            # Auto-create feature flags based on tier
            flags = self._tier_to_flags(tier_level)
            self._upsert_flags(customer_account_id, flags)

            log.info(f"[suite.subs] created {sub_id} ({tier_level}) for {customer_account_id}")
            return {
                "ok": True,
                "subscription_id": str(sub_id),
                "customer_account_id": customer_account_id,
                "tier_level": tier_level,
                "monthly_recurring_revenue": monthly_recurring_revenue,
            }
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    @staticmethod
    def _tier_to_flags(tier: str) -> dict:
        """Return default feature flags for a given tier."""
        flags = {
            "inbound_router_enabled": 0,
            "data_retention_enabled": 0,
            "buyer_spy_enabled": 0,
            "hexstrike_enabled": 0,
            "analyzer_enabled": 0,
            "inbound_router_max_calls": 0,
            "data_retention_days": 90,
            "buyer_spy_analyze_per_day": 100,
            "seo_audits_enabled": 0,
            "seo_keyword_tracking_enabled": 0,
            "seo_content_generation_enabled": 0,
            "seo_research_pipeline_enabled": 0,
            "seo_landing_pages_enabled": 0,
            "seo_audits_per_month": 0,
            "seo_keywords_per_month": 0,
            "seo_content_pieces_per_month": 0,
        }
        if "HEXSTRIKE" in tier:
            flags["hexstrike_enabled"] = 1
        if "ANALYZER" in tier:
            flags["analyzer_enabled"] = 1
            flags["hexstrike_enabled"] = 1
        if tier == "ROUTER_SaaS":
            flags["inbound_router_enabled"] = 1
        elif tier == "DATA_ENTERPRISE":
            flags["data_retention_enabled"] = 1
        elif tier == "SPY_DATA":
            flags["buyer_spy_enabled"] = 1
        elif tier == "ALL_ACCESS":
            flags["inbound_router_enabled"] = 1
            flags["data_retention_enabled"] = 1
            flags["buyer_spy_enabled"] = 1
            flags["seo_audits_enabled"] = 1
            flags["seo_keyword_tracking_enabled"] = 1
            flags["seo_content_generation_enabled"] = 1
            flags["seo_research_pipeline_enabled"] = 1
            flags["seo_landing_pages_enabled"] = 1
            flags["seo_audits_per_month"] = 0
            flags["seo_keywords_per_month"] = 0
            flags["seo_content_pieces_per_month"] = 0
            flags["meetily_enabled"] = 1
            flags["elite_scraper_enabled"] = 1
        elif tier == "SEO_STARTER":
            flags["seo_audits_enabled"] = 1
            flags["seo_keyword_tracking_enabled"] = 1
            flags["seo_content_generation_enabled"] = 1
            flags["seo_audits_per_month"] = 5
            flags["seo_keywords_per_month"] = 50
            flags["seo_content_pieces_per_month"] = 10
        elif tier == "SEO_GROWTH":
            flags["seo_audits_enabled"] = 1
            flags["seo_keyword_tracking_enabled"] = 1
            flags["seo_content_generation_enabled"] = 1
            flags["seo_research_pipeline_enabled"] = 1
            flags["seo_landing_pages_enabled"] = 1
            flags["seo_audits_per_month"] = 15
            flags["seo_keywords_per_month"] = 200
            flags["seo_content_pieces_per_month"] = 20
        elif tier == "SEO_PRO":
            flags["seo_audits_enabled"] = 1
            flags["seo_keyword_tracking_enabled"] = 1
            flags["seo_content_generation_enabled"] = 1
            flags["seo_research_pipeline_enabled"] = 1
            flags["seo_landing_pages_enabled"] = 1
            flags["seo_audits_per_month"] = 0
            flags["seo_keywords_per_month"] = 0
            flags["seo_content_pieces_per_month"] = 0
        elif "MEETILY" in tier:
            flags["meetily_enabled"] = 1
        elif "SCRAPER" in tier:
            flags["elite_scraper_enabled"] = 1
        elif "CLOSER" in tier or tier == "EXECUTIVE_WHALE":
            flags["closer_enabled"] = 1
        return flags

    def _upsert_flags(self, account_id: str, flags: dict):
        """Insert or update feature flags for an account.

        Core flags (inbound_router_enabled, data_retention_enabled, etc.)
        are written to their named columns. Extended flags (seo_*,
        hexstrike_*, analyzer_*, etc.) are stored in the `meta` JSONB
        column to avoid schema drift."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Split into core columns and extended (meta) flags
        core = {}
        extended = {}
        for k, v in flags.items():
            if k in CORE_FLAG_COLUMNS:
                core[k] = v
            else:
                extended[k] = v

        try:
            db = self._get_db()

            # Read existing meta, merge with new extended flags
            existing_meta = {}
            try:
                r = db.table("product_feature_flags") \
                    .select("meta") \
                    .eq("customer_account_id", account_id) \
                    .limit(1) \
                    .execute()
                if r.data and r.data[0].get("meta") is not None:
                    m = r.data[0]["meta"]
                    if isinstance(m, str):
                        existing_meta = _json.loads(m)
                    elif isinstance(m, dict):
                        existing_meta = dict(m)
            except Exception:
                pass

            merged_meta = {**existing_meta, **extended}

            # Upsert: check if row exists
            r = db.table("product_feature_flags") \
                .select("id") \
                .eq("customer_account_id", account_id) \
                .limit(1) \
                .execute()

            if r.data:
                # Update existing row
                db.table("product_feature_flags") \
                    .update({
                        **core,
                        "meta": merged_meta,
                        "updated_at": now,
                    }) \
                    .eq("customer_account_id", account_id) \
                    .execute()
            else:
                # Insert new row
                db.table("product_feature_flags").insert({
                    "customer_account_id": account_id,
                    **core,
                    "meta": merged_meta,
                    "created_at": now,
                    "updated_at": now,
                }).execute()

        except Exception as e:
            log.warning(f"[suite.subs] upsert flags failed for {account_id}: {e}")

    def update_subscription(self, sub_id: str, updates: dict) -> dict:
        """Update subscription fields (status, tier, MRR)."""
        allowed = {"subscription_status", "tier_level", "monthly_recurring_revenue"}
        update_data = {k: v for k, v in updates.items() if k in allowed and v is not None}

        if "tier_level" in update_data:
            t = update_data["tier_level"].upper()
            if t not in VALID_TIERS:
                return {"ok": False, "error": f"Invalid tier: {t}"}
            update_data["tier_level"] = t
            # Update feature flags to match new tier
            sub = self.get_subscription_by_id(sub_id)
            if sub:
                flags = self._tier_to_flags(t)
                self._upsert_flags(sub["customer_account_id"], flags)

        if "subscription_status" in update_data:
            s = update_data["subscription_status"].upper()
            if s not in VALID_STATUSES:
                return {"ok": False, "error": f"Invalid status: {s}"}
            update_data["subscription_status"] = s

        if not update_data:
            return {"ok": False, "error": "No valid fields to update"}

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            db = self._get_db()
            db.table("product_subscriptions") \
                .update(update_data) \
                .eq("subscription_id", sub_id) \
                .execute()
            log.info(f"[suite.subs] updated {sub_id}: {update_data}")
            return {"ok": True, "subscription_id": sub_id, "updates": update_data}
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}


# ═════════════════════════════════════════════════════════════════════════
# GUARD / GATECHECK  (Supabase)
# ═════════════════════════════════════════════════════════════════════════

class SuiteGuard:
    """Feature-flag gatekeeper + usage meter for the suite products."""

    FEATURE_MAP = {
        "inbound_router":         "inbound_router_enabled",
        "data_vault":             "data_retention_enabled",
        "buyer_spy":              "buyer_spy_enabled",
        "lead_score":             "leadscore_enabled",
        "compliant":              "compliant_enabled",
        "strike_campaigns":       "strike_campaigns_enabled",
        "forecast":               "forecast_enabled",
        "market_eye":             "market_eye_enabled",
        "content_pulse":          "content_pulse_enabled",
        "contractor_exchange":     "contractor_exchange_enabled",
        "hexstrike":               "hexstrike_enabled",
        "analyzer":                "analyzer_enabled",
        "meetily":                 "meetily_enabled",
        "elite_scraper":           "elite_scraper_enabled",
        "ai_closer":               "closer_enabled",
    }

    def __init__(
        self,
        subscriptions: SuiteSubscriptionEngine,
        get_db: Callable,
    ):
        self.subscriptions = subscriptions
        self._get_db = get_db
        self.stats = {"gatechecks": 0, "granted": 0, "denied": 0, "usage_logged": 0}

    def check_access(self, account_id: str, feature: str) -> dict:
        """Verify that an account has access to a given feature.
        Returns the gatecheck result with the full access decision."""
        self.stats["gatechecks"] += 1

        # Validate feature name
        db_col = self.FEATURE_MAP.get(feature)
        if not db_col:
            return {
                "ok": False,
                "status": "ACCESS_DENIED",
                "error": f"Unknown feature: '{feature}'. Valid: {list(self.FEATURE_MAP.keys())}",
            }

        # 1. Check subscription exists and is active
        sub = self.subscriptions.get_subscription(account_id)
        if not sub:
            self.stats["denied"] += 1
            return {
                "ok": False,
                "status": "ACCESS_DENIED",
                "error": f"No subscription found for account '{account_id}'",
            }

        if sub["subscription_status"] not in ("ACTIVE", "TRIALING"):
            self.stats["denied"] += 1
            return {
                "ok": False,
                "status": "ACCESS_DENIED",
                "error": f"Subscription status is '{sub['subscription_status']}' (must be ACTIVE or TRIALING)",
            }

        # 2. Check per-period cap (period_end check)
        period_end = sub.get("current_period_end")
        if period_end:
            try:
                end = datetime.fromisoformat(str(period_end).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > end:
                    self.stats["denied"] += 1
                    return {
                        "ok": False,
                        "status": "PERIOD_EXPIRED",
                        "error": f"Billing period ended {end.isoformat()}",
                    }
            except (ValueError, TypeError):
                pass

        # 3. Check feature flag
        flags = self._get_flags(account_id)
        if not flags or not flags.get(db_col, 0):
            self.stats["denied"] += 1
            return {
                "ok": False,
                "status": "FEATURE_LOCKED",
                "error": f"Feature '{feature}' is not enabled for account '{account_id}'. Upgrade your Empire AI tier subscription.",
            }

        self.stats["granted"] += 1
        return {
            "ok": True,
            "status": "ACCESS_GRANTED",
            "account": account_id,
            "authorized_feature": feature,
            "tier": sub["tier_level"],
            "mrr": sub["monthly_recurring_revenue"],
        }

    def _get_flags(self, account_id: str) -> Optional[dict]:
        """Return feature flags for an account from Supabase.

        Merges core columns (inbound_router_enabled, etc.) with the
        `meta` JSONB column which stores extended flags (seo_*,
        hexstrike_*, etc.) added after migration 018."""
        try:
            db = self._get_db()
            r = db.table("product_feature_flags") \
                .select("*") \
                .eq("customer_account_id", account_id) \
                .limit(1) \
                .execute()
            if not r.data:
                return None

            row = dict(r.data[0])
            # Merge meta JSONB into flat dict for unified lookup
            meta = row.pop("meta", None) or {}
            if isinstance(meta, str):
                meta = _json.loads(meta)
            row.update(meta)
            return row
        except Exception:
            return None

    def log_usage(self, account_id: str, product_name: str, usage_event: str,
                  quantity: int = 1, unit: str = "count", metadata: dict = None) -> dict:
        """Record a usage metering event for billing (Supabase)."""
        if product_name not in VALID_PRODUCTS:
            return {"ok": False, "error": f"Invalid product: {product_name}"}

        try:
            db = self._get_db()
            db.table("product_usage_log").insert({
                "customer_account_id": account_id,
                "product_name": product_name,
                "usage_event": usage_event,
                "quantity": quantity,
                "unit": unit,
                "metadata": metadata or {},
            }).execute()
            self.stats["usage_logged"] += 1
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def usage_summary(self, account_id: Optional[str] = None,
                      product_name: Optional[str] = None,
                      days: int = 30) -> list[dict]:
        """Return usage log entries from Supabase, optionally filtered."""
        try:
            db = self._get_db()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")

            query = db.table("product_usage_log") \
                .select("*") \
                .gte("created_at", since)

            if account_id:
                query = query.eq("customer_account_id", account_id)
            if product_name:
                query = query.eq("product_name", product_name)

            query = query.order("created_at", desc=True).limit(1000)
            r = query.execute()
            return [dict(row) for row in (r.data or [])]
        except Exception:
            return []


# ═════════════════════════════════════════════════════════════════════════
# ROUTE REGISTRATION
# ═════════════════════════════════════════════════════════════════════════

def register_suite_routes(
    app: FastAPI,
    *,
    require_auth: Optional[Callable] = None,
    subscriptions: Optional[SuiteSubscriptionEngine] = None,
    guard: Optional[SuiteGuard] = None,
):
    """Wire Empire AI Suite API endpoints into the FastAPI app.

    Supports two modes:
      - **Integrated** (hub.py): pass require_auth= Depends(auth), and
        the routes will require authentication.
      - **Standalone** (uvicorn port 8040): omit require_auth, and the
        routes are unauthenticated (gatecheck uses the built-in account
        lookup and tier check for entitlement).
    """
    if subscriptions is None:
        raise ValueError("SuiteSubscriptionEngine required — pass get_db to constructor")
    if guard is None:
        raise ValueError("SuiteGuard required — pass get_db to constructor")

    # ── Health ──────────────────────────────────────────────────────────

    @app.get("/api/v6/suite/health")
    async def suite_health():
        """Simple health check for the suite gateway."""
        return {
            "status": "operational",
            "mode": "standalone" if require_auth is None else "integrated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Gatecheck ───────────────────────────────────────────────────────

    @app.post("/api/v6/suite/gatecheck")
    async def suite_gatecheck(
        payload: GatecheckPayload,
        request: Request,
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """Gatekeeper API endpoint verifying entitlement access.
        Checks subscription status, period validity, and feature flags.
        """
        result = guard.check_access(
            account_id=payload.customer_account_id.strip(),
            feature=payload.feature_requested.strip().lower(),
        )
        if not result.get("ok"):
            raise HTTPException(status_code=403, detail=result.get("error", "Access denied"))
        return result

    # ── Usage Logging ───────────────────────────────────────────────────

    @app.post("/api/v6/suite/usage/log")
    async def suite_log_usage(
        payload: UsageLogPayload,
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """Record a usage metering event for billing."""
        result = guard.log_usage(
            account_id=payload.customer_account_id.strip(),
            product_name=payload.product_name.strip().lower(),
            usage_event=payload.usage_event.strip(),
            quantity=payload.quantity,
            unit=payload.unit,
            metadata=payload.metadata,
        )
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Logging failed"))
        return result

    @app.get("/api/v6/suite/usage")
    async def suite_usage(
        account_id: str = Query(""),
        product: str = Query(""),
        days: int = Query(30),
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """Return usage log entries, optionally filtered."""
        entries = guard.usage_summary(
            account_id=account_id or None,
            product_name=product or None,
            days=min(days, 365),
        )
        return {"entries": entries, "count": len(entries)}

    # ── Subscription Management ─────────────────────────────────────────

    @app.get("/api/v6/suite/subscriptions")
    async def suite_list_subscriptions(
        tier: str = Query(""),
        status: str = Query(""),
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """List all subscriptions, optionally filtered by tier or status."""
        subs = subscriptions.list_subscriptions(
            tier=tier.upper() if tier else None,
            status=status.upper() if status else None,
        )
        return {"subscriptions": subs, "count": len(subs)}

    @app.post("/api/v6/suite/subscriptions")
    async def suite_create_subscription(
        payload: SubscriptionCreatePayload,
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """Create a new product subscription."""
        result = subscriptions.create_subscription(
            customer_account_id=payload.customer_account_id.strip(),
            tier_level=payload.tier_level,
            monthly_recurring_revenue=payload.monthly_recurring_revenue,
            billing_anchor_day=max(1, min(28, payload.billing_anchor_day)),
            notes=payload.notes,
        )
        if not result.get("ok"):
            status_code = 409 if "already has" in (result.get("error") or "") else 400
            raise HTTPException(status_code, result.get("error", "Creation failed"))
        return result

    @app.post("/api/v6/suite/subscriptions/{sub_id}/update")
    async def suite_update_subscription(
        sub_id: str,
        payload: SubscriptionUpdatePayload,
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """Update subscription status, tier, or MRR."""
        updates = {}
        if payload.subscription_status:
            updates["subscription_status"] = payload.subscription_status
        if payload.tier_level:
            updates["tier_level"] = payload.tier_level
        if payload.monthly_recurring_revenue is not None:
            updates["monthly_recurring_revenue"] = payload.monthly_recurring_revenue

        result = subscriptions.update_subscription(sub_id, updates)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Update failed"))
        return result

    # ── Stats ───────────────────────────────────────────────────────────

    @app.get("/api/v6/suite/stats")
    async def suite_stats(
        auth: bool = Depends(require_auth) if require_auth else None,
    ):
        """Suite-wide stats snapshot: subscriptions, usage, gatecheck activity."""
        all_subs = subscriptions.list_subscriptions()
        active_subs = [s for s in all_subs if s.get("subscription_status") == "ACTIVE"]
        total_mrr = sum(float(s.get("monthly_recurring_revenue", 0) or 0) for s in active_subs)

        return {
            "subscriptions": {
                "total": len(all_subs),
                "active": len(active_subs),
                "by_tier": {
                    tier: len([s for s in all_subs if s.get("tier_level") == tier])
                    for tier in sorted(VALID_TIERS)
                },
                "total_mrr": round(total_mrr, 2),
            },
            "guard": {
                "gatechecks": guard.stats["gatechecks"],
                "granted": guard.stats["granted"],
                "denied": guard.stats["denied"],
                "usage_logged": guard.stats["usage_logged"],
            },
            "products_available": sorted(VALID_PRODUCTS),
            "tiers_available": sorted(VALID_TIERS),
            "mode": "standalone" if require_auth is None else "integrated",
        }

    log.info("[suite] Routes registered · /api/v6/suite/*")


# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP (uvicorn port 8040)
# ═════════════════════════════════════════════════════════════════════════

def create_standalone_app() -> FastAPI:
    """Create a standalone FastAPI app for the Suite Gateway on port 8040.
    Uses Supabase for subscription data — no local SQLite dependency."""
    app = FastAPI(title="Empire AI · Suite Gateway", version="1.0.0")

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize Supabase client from env vars
    from supabase import create_client as _create_sb
    sb_url = os.environ.get("SUPABASE_URL", "")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    def get_db():
        return _create_sb(sb_url, sb_key)

    sub_engine = SuiteSubscriptionEngine(get_db=get_db)
    guard = SuiteGuard(subscriptions=sub_engine, get_db=get_db)
    register_suite_routes(app, subscriptions=sub_engine, guard=guard)

    @app.get("/")
    async def root():
        return {
            "service": "Empire AI Suite Gateway",
            "version": "1.0.0",
            "endpoints": [
                "GET  /api/v6/suite/health",
                "POST /api/v6/suite/gatecheck",
                "POST /api/v6/suite/usage/log",
                "GET  /api/v6/suite/usage",
                "GET  /api/v6/suite/subscriptions",
                "POST /api/v6/suite/subscriptions",
                "POST /api/v6/suite/subscriptions/{id}/update",
                "GET  /api/v6/suite/stats",
            ],
        }

    return app


# ── Standalone entry point ─────────────────────────────────────────────
standalone_app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SUITE_PORT", "8040"))
    host = os.environ.get("SUITE_HOST", "0.0.0.0")
    log.info(f"[suite] Starting standalone gateway on {host}:{port}")
    uvicorn.run(standalone_app, host=host, port=port, log_level="info")
