"""
EMPIRE V49 · UNIFIED MULTI-PRODUCT MRR SUITE CORE
==================================================
Productizes three micro-products under a single subscription + feature-flag
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
"""

import json as _json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger("empire.suite")

# ── Config ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"

VALID_TIERS = {"ROUTER_SaaS", "DATA_ENTERPRISE", "SPY_DATA", "ALL_ACCESS",
                "SEO_STARTER", "SEO_GROWTH", "SEO_PRO"}
VALID_PRODUCTS = {"inbound_router", "data_vault", "buyer_spy", "seo_optimizer"}
VALID_STATUSES = {"ACTIVE", "PAST_DUE", "CANCELED", "TRIALING"}


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
# DATABASE HELPERS
# ═════════════════════════════════════════════════════════════════════════

def _get_conn() -> sqlite3.Connection:
    """Return a connection to the local SQLite DB (storm_alerts.sqlite)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_suite_db():
    """Run the suite extension SQL against the local SQLite DB.
    Idempotent — uses IF NOT EXISTS throughout."""
    sql_path = BASE_DIR / "database" / "empire_suite_extension.sql"
    if not sql_path.exists():
        log.warning(f"[suite] extension SQL not found at {sql_path}")
        return
    sql = sql_path.read_text()
    conn = _get_conn()
    try:
        # Split by semicolons but preserve statements with function bodies
        stmts = []
        current = ""
        in_dollar = False
        for line in sql.split("\n"):
            stripped = line.strip()
            if stripped.startswith("--") or not stripped:
                continue
            current += line + "\n"
            if not in_dollar and stripped.rstrip(";").endswith("BEGIN"):
                in_dollar = True
            if in_dollar and stripped.rstrip(";").endswith("END;"):
                in_dollar = False
            if not in_dollar and current.strip().endswith(";"):
                stmts.append(current.strip())
                current = ""
        for stmt in stmts:
            if stmt:
                try:
                    conn.execute(stmt)
                except Exception as e:
                    log.debug(f"[suite] init stmt skipped: {e}")
        conn.commit()
        log.info("[suite] DB schema initialized from empire_suite_extension.sql")
    except Exception as e:
        log.warning(f"[suite] init failed: {e}")
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION ENGINE
# ═════════════════════════════════════════════════════════════════════════

class SuiteSubscriptionEngine:
    """Manage product subscriptions: CRUD, status transitions, period tracking."""

    def __init__(self, get_db: Optional[Callable] = None):
        self._get_db = get_db  # Optional Supabase get_db for hub integration
        self.stats = {"created": 0, "lookups": 0, "errors": 0}

    # ── INTERNAL DB ACCESS ────────────────────────────────────────────────

    def _conn(self):
        return _get_conn()

    # ── QUERIES ───────────────────────────────────────────────────────────

    def get_subscription(self, account_id: str) -> Optional[dict]:
        """Return a single subscription by customer_account_id."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT * FROM product_subscriptions WHERE customer_account_id = ?",
                (account_id,),
            )
            row = cur.fetchone()
            self.stats["lookups"] += 1
            return dict(row) if row else None
        except Exception as e:
            self.stats["errors"] += 1
            log.warning(f"[suite.subs] lookup error: {e}")
            return None
        finally:
            conn.close()

    def get_subscription_by_id(self, sub_id: str) -> Optional[dict]:
        """Return a single subscription by subscription_id."""
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT * FROM product_subscriptions WHERE subscription_id = ?",
                (sub_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            return None
        finally:
            conn.close()

    def list_subscriptions(
        self, tier: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict]:
        """Return all subscriptions, optionally filtered."""
        conn = self._conn()
        try:
            query = "SELECT * FROM product_subscriptions WHERE 1=1"
            params = []
            if tier and tier in VALID_TIERS:
                query += " AND tier_level = ?"
                params.append(tier)
            if status and status in VALID_STATUSES:
                query += " AND subscription_status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            self.stats["errors"] += 1
            return []
        finally:
            conn.close()

    # ── MUTATIONS ─────────────────────────────────────────────────────────

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

        import uuid
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO product_subscriptions
                   (subscription_id, customer_account_id, tier_level,
                    monthly_recurring_revenue, billing_anchor_day,
                    current_period_start, notes,
                    stripe_customer_id, stripe_subscription_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sub_id, customer_account_id, tier_level,
                    monthly_recurring_revenue, billing_anchor_day,
                    now, notes[:500],
                    stripe_customer_id or None, stripe_subscription_id or None,
                    now, now,
                ),
            )
            conn.commit()
            self.stats["created"] += 1

            # Auto-create feature flags based on tier
            flags = self._tier_to_flags(tier_level)
            self._upsert_flags(customer_account_id, flags)

            log.info(f"[suite.subs] created {sub_id} ({tier_level}) for {customer_account_id}")
            return {
                "ok": True,
                "subscription_id": sub_id,
                "customer_account_id": customer_account_id,
                "tier_level": tier_level,
                "monthly_recurring_revenue": monthly_recurring_revenue,
            }
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}
        finally:
            conn.close()

    @staticmethod
    def _tier_to_flags(tier: str) -> dict:
        """Return default feature flags for a given tier."""
        flags = {
            "inbound_router_enabled": 0,
            "data_retention_enabled": 0,
            "buyer_spy_enabled": 0,
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
        return flags

    def _upsert_flags(self, account_id: str, flags: dict):
        """Insert or update feature flags for an account."""
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute(
                """INSERT INTO product_feature_flags
                   (customer_account_id,
                    inbound_router_enabled, data_retention_enabled, buyer_spy_enabled,
                    inbound_router_max_calls, data_retention_days, buyer_spy_analyze_per_day,
                    seo_audits_enabled, seo_keyword_tracking_enabled, seo_content_generation_enabled,
                    seo_research_pipeline_enabled, seo_landing_pages_enabled,
                    seo_audits_per_month, seo_keywords_per_month, seo_content_pieces_per_month,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(customer_account_id) DO UPDATE SET
                     inbound_router_enabled        = COALESCE(EXCLUDED.inbound_router_enabled, product_feature_flags.inbound_router_enabled),
                     data_retention_enabled        = COALESCE(EXCLUDED.data_retention_enabled, product_feature_flags.data_retention_enabled),
                     buyer_spy_enabled             = COALESCE(EXCLUDED.buyer_spy_enabled, product_feature_flags.buyer_spy_enabled),
                     inbound_router_max_calls      = COALESCE(EXCLUDED.inbound_router_max_calls, product_feature_flags.inbound_router_max_calls),
                     data_retention_days           = COALESCE(EXCLUDED.data_retention_days, product_feature_flags.data_retention_days),
                     buyer_spy_analyze_per_day     = COALESCE(EXCLUDED.buyer_spy_analyze_per_day, product_feature_flags.buyer_spy_analyze_per_day),
                     seo_audits_enabled            = COALESCE(EXCLUDED.seo_audits_enabled, product_feature_flags.seo_audits_enabled),
                     seo_keyword_tracking_enabled  = COALESCE(EXCLUDED.seo_keyword_tracking_enabled, product_feature_flags.seo_keyword_tracking_enabled),
                     seo_content_generation_enabled = COALESCE(EXCLUDED.seo_content_generation_enabled, product_feature_flags.seo_content_generation_enabled),
                     seo_research_pipeline_enabled  = COALESCE(EXCLUDED.seo_research_pipeline_enabled, product_feature_flags.seo_research_pipeline_enabled),
                     seo_landing_pages_enabled      = COALESCE(EXCLUDED.seo_landing_pages_enabled, product_feature_flags.seo_landing_pages_enabled),
                     seo_audits_per_month          = COALESCE(EXCLUDED.seo_audits_per_month, product_feature_flags.seo_audits_per_month),
                     seo_keywords_per_month        = COALESCE(EXCLUDED.seo_keywords_per_month, product_feature_flags.seo_keywords_per_month),
                     seo_content_pieces_per_month  = COALESCE(EXCLUDED.seo_content_pieces_per_month, product_feature_flags.seo_content_pieces_per_month),
                     updated_at = ?""",
                (
                    account_id,
                    flags.get("inbound_router_enabled", 0),
                    flags.get("data_retention_enabled", 0),
                    flags.get("buyer_spy_enabled", 0),
                    flags.get("inbound_router_max_calls", 0),
                    flags.get("data_retention_days", 90),
                    flags.get("buyer_spy_analyze_per_day", 100),
                    flags.get("seo_audits_enabled", 0),
                    flags.get("seo_keyword_tracking_enabled", 0),
                    flags.get("seo_content_generation_enabled", 0),
                    flags.get("seo_research_pipeline_enabled", 0),
                    flags.get("seo_landing_pages_enabled", 0),
                    flags.get("seo_audits_per_month", 0),
                    flags.get("seo_keywords_per_month", 0),
                    flags.get("seo_content_pieces_per_month", 0),
                    now, now, now,
                ),
            )
            conn.commit()
        except Exception as e:
            log.warning(f"[suite.subs] upsert flags failed: {e}")
        finally:
            conn.close()

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

        conn = self._conn()
        try:
            set_clause = ", ".join(f"{k} = ?" for k in update_data)
            values = list(update_data.values()) + [sub_id]
            conn.execute(
                f"UPDATE product_subscriptions SET {set_clause} WHERE subscription_id = ?",
                values,
            )
            conn.commit()
            log.info(f"[suite.subs] updated {sub_id}: {update_data}")
            return {"ok": True, "subscription_id": sub_id, "updates": update_data}
        except Exception as e:
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}
        finally:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════
# GUARD / GATECHECK
# ═════════════════════════════════════════════════════════════════════════

class SuiteGuard:
    """Feature-flag gatekeeper + usage meter for the suite products."""

    FEATURE_MAP = {
        "inbound_router": "inbound_router_enabled",
        "data_vault":     "data_retention_enabled",
        "buyer_spy":      "buyer_spy_enabled",
    }

    def __init__(
        self,
        subscriptions: SuiteSubscriptionEngine,
    ):
        self.subscriptions = subscriptions
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
                from datetime import datetime
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
        """Return feature flags for an account."""
        conn = _get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM product_feature_flags WHERE customer_account_id = ?",
                (account_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()

    def log_usage(self, account_id: str, product_name: str, usage_event: str,
                  quantity: int = 1, unit: str = "count", metadata: dict = None) -> dict:
        """Record a usage metering event for billing."""
        if product_name not in VALID_PRODUCTS:
            return {"ok": False, "error": f"Invalid product: {product_name}"}

        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO product_usage_log
                   (customer_account_id, product_name, usage_event, quantity, unit, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    account_id, product_name, usage_event,
                    quantity, unit,
                    _json.dumps(metadata or {}),
                ),
            )
            conn.commit()
            self.stats["usage_logged"] += 1
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}
        finally:
            conn.close()

    def usage_summary(self, account_id: Optional[str] = None,
                      product_name: Optional[str] = None,
                      days: int = 30) -> list[dict]:
        """Return usage log entries, optionally filtered."""
        conn = _get_conn()
        try:
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(days=days)
            query = "SELECT * FROM product_usage_log WHERE created_at >= ?"
            params = [since.isoformat(timespec="seconds")]

            if account_id:
                query += " AND customer_account_id = ?"
                params.append(account_id)
            if product_name:
                query += " AND product_name = ?"
                params.append(product_name)

            query += " ORDER BY created_at DESC LIMIT 1000"
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()


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
        subscriptions = SuiteSubscriptionEngine()
    if guard is None:
        guard = SuiteGuard(subscriptions=subscriptions)

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
        total_mrr = sum(s.get("monthly_recurring_revenue", 0) for s in active_subs)

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
    """Create a standlone FastAPI app for the Suite Gateway on port 8040.
    This runs independently of the main hub for external API consumers."""
    app = FastAPI(title="Empire AI · Suite Gateway", version="1.0.0")

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Init DB
    _init_suite_db()

    sub_engine = SuiteSubscriptionEngine()
    guard = SuiteGuard(subscriptions=sub_engine)
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
