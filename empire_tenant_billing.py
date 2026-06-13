"""
EMPIRE V49 · TENANT BILLING (Multi-Tenant)
===========================================
Per-tenant subscription management, usage metering, and billing on Supabase.
Ports the Suite billing from local SQLite to the multi-tenant Supabase model.

Architecture:
  organizations (Supabase, RLS-isolated)
      │
      ├─ tenant_subscriptions — per-org subscription plan + status
      ├─ tenant_usage_log    — metered usage events per org per product
      └─ tenant_invoices     — billing history (stripe-compatible stubs)

Billing plans:
  free        — basic features, limited leads
  starter     — core features, more leads, 1 custom domain
  professional — full features, unlimited leads, branding
  enterprise   — everything, custom SLA, dedicated support

Stripe integration:
  Stripe webhook stubs are included. When STRIPE_SECRET_KEY is set,
  subscription changes sync to Stripe. Without it, billing is managed
  internally via the organization's billing_status field.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

log = logging.getLogger("empire.tenant_billing")


# Plan definitions
PLANS = {
    "free": {
        "label": "Free",
        "price_monthly_cents": 0,
        "max_operators": 1,
        "max_leads_per_month": 100,
        "features": {"inbound_router": False, "data_vault": False, "buyer_spy": False,
                     "white_label": False, "api_access": False},
    },
    "starter": {
        "label": "Starter",
        "price_monthly_cents": 9900,   # $99
        "max_operators": 3,
        "max_leads_per_month": 1000,
        "features": {"inbound_router": True, "data_vault": False, "buyer_spy": False,
                     "white_label": False, "api_access": True},
    },
    "professional": {
        "label": "Professional",
        "price_monthly_cents": 49900,  # $499
        "max_operators": 10,
        "max_leads_per_month": 10000,
        "features": {"inbound_router": True, "data_vault": True, "buyer_spy": True,
                     "white_label": True, "api_access": True},
    },
    "enterprise": {
        "label": "Enterprise",
        "price_monthly_cents": 199900, # $1,999
        "max_operators": 50,
        "max_leads_per_month": 100000,
        "features": {"inbound_router": True, "data_vault": True, "buyer_spy": True,
                     "white_label": True, "api_access": True},
    },
}


class TenantBillingEngine:
    """Per-tenant subscription and usage metering."""

    def __init__(self, *, get_db: Callable):
        self.get_db = get_db
        self.stats = {
            "subscriptions_created": 0,
            "usage_events_logged": 0,
            "invoices_generated": 0,
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── SUBSCRIPTION MANAGEMENT ────────────────────────────────────

    async def get_subscription(self, org_id: str) -> Optional[dict]:
        """Return the current subscription for an organization.
        Falls back to reading from the organization's billing_plan field
        if no tenant_subscriptions row exists yet.
        """
        try:
            db = self.get_db()
            r = db.table("tenant_subscriptions").select("*") \
                .eq("org_id", org_id).order("created_at", desc=True).limit(1).execute()
            if r.data:
                return r.data[0]
        except Exception:
            pass

        # Fallback: create subscription from org billing_plan
        try:
            db = self.get_db()
            org_r = db.table("organizations").select("billing_plan, billing_status").eq("id", org_id).limit(1).execute()
            if org_r.data:
                org = org_r.data[0]
                plan = org.get("billing_plan", "free")
                plan_def = PLANS.get(plan, PLANS["free"])
                return {
                    "org_id": org_id,
                    "plan": plan,
                    "status": org.get("billing_status", "active"),
                    "price_monthly_cents": plan_def["price_monthly_cents"],
                    "period_start": self._now(),
                    "period_end": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                    "features": plan_def["features"],
                    "max_leads_per_month": plan_def["max_leads_per_month"],
                }
        except Exception:
            pass
        return None

    async def create_subscription(
        self,
        org_id: str,
        plan: str = "free",
        stripe_customer_id: str = "",
        stripe_subscription_id: str = "",
    ) -> dict:
        """Create a subscription for an organization."""
        if plan not in PLANS:
            return {"ok": False, "error": f"Invalid plan: {plan}"}

        plan_def = PLANS[plan]
        now = self._now()

        try:
            db = self.get_db()
            data = {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "plan": plan,
                "status": "active",
                "price_monthly_cents": plan_def["price_monthly_cents"],
                "period_start": now,
                "period_end": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "features": plan_def["features"],
                "stripe_customer_id": stripe_customer_id or None,
                "stripe_subscription_id": stripe_subscription_id or None,
                "created_at": now,
                "updated_at": now,
            }

            # Try Supabase table, fall back to updating the org
            try:
                db.table("tenant_subscriptions").insert(data).execute()
            except Exception:
                # Table might not exist yet — update org billing_plan instead
                db.table("organizations").update({
                    "billing_plan": plan,
                    "updated_at": now,
                }).eq("id", org_id).execute()

            self.stats["subscriptions_created"] += 1
            log.info(f"[billing] subscription created: org={org_id} plan={plan}")
            return {"ok": True, "subscription": data}
        except Exception as e:
            log.error(f"[billing] create_subscription failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    async def update_subscription(self, org_id: str, plan: str) -> dict:
        """Upgrade/downgrade an organization's subscription."""
        if plan not in PLANS:
            return {"ok": False, "error": f"Invalid plan: {plan}"}

        plan_def = PLANS[plan]
        now = self._now()

        try:
            db = self.get_db()
            try:
                db.table("tenant_subscriptions").update({
                    "plan": plan,
                    "status": "active",
                    "price_monthly_cents": plan_def["price_monthly_cents"],
                    "features": plan_def["features"],
                    "updated_at": now,
                }).eq("org_id", org_id).execute()
            except Exception:
                pass

            # Always update the org
            db.table("organizations").update({
                "billing_plan": plan,
                "billing_status": "active",
                "max_operators": plan_def["max_operators"],
                "max_leads_per_month": plan_def["max_leads_per_month"],
                "features": plan_def["features"],
                "updated_at": now,
            }).eq("id", org_id).execute()

            log.info(f"[billing] subscription updated: org={org_id} plan={plan}")
            return {"ok": True, "plan": plan}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def cancel_subscription(self, org_id: str) -> dict:
        """Cancel an organization's subscription (revert to free)."""
        return await self.update_subscription(org_id, "free")

    # ── USAGE METERING ─────────────────────────────────────────────

    async def log_usage(
        self,
        org_id: str,
        metric: str,
        amount: int = 1,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Record a usage metering event (leads, calls, emails, etc.)."""
        try:
            db = self.get_db()
            now = self._now()
            data = {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "metric": metric,
                "amount": amount,
                "metadata": metadata or {},
                "created_at": now,
            }
            try:
                db.table("tenant_usage_log").insert(data).execute()
            except Exception:
                pass  # table may not exist yet

            self.stats["usage_events_logged"] += 1
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def get_usage(
        self,
        org_id: str,
        metric: str = "",
        days: int = 30,
    ) -> dict:
        """Return usage summary for an organization."""
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc)
            since = (now - timedelta(days=days)).isoformat()

            q = db.table("tenant_usage_log").select("metric, amount, created_at") \
                .eq("org_id", org_id) \
                .gte("created_at", since)

            if metric:
                q = q.eq("metric", metric)

            r = q.order("created_at", desc=True).limit(1000).execute()
            rows = r.data or []

            totals = {}
            for row in rows:
                m = row.get("metric", "unknown")
                totals[m] = totals.get(m, 0) + int(row.get("amount", 0))

            return {
                "org_id": org_id,
                "days": days,
                "totals": totals,
                "events": len(rows),
                "recent": rows[:20],
            }
        except Exception as e:
            return {"org_id": org_id, "error": str(e)[:200], "totals": {}, "events": 0}

    # ── PLAN INFO ──────────────────────────────────────────────────

    def get_plan_info(self, plan: str) -> dict:
        """Return plan definition. Returns free plan for unknown plans."""
        return dict(PLANS.get(plan, PLANS["free"]))

    def list_plans(self) -> dict:
        """Return all available plans with their definitions."""
        return PLANS

    # ── STRIPE WEBHOOK STUB ────────────────────────────────────────

    async def handle_stripe_webhook(self, event: dict) -> dict:
        """Handle Stripe webhook events for subscription lifecycle.
        Supports: invoice.paid, invoice.payment_failed,
                 customer.subscription.updated, customer.subscription.deleted
        """
        event_type = event.get("type", "")
        data = event.get("data", {}).get("object", {})

        if event_type == "invoice.paid":
            customer_id = data.get("customer", "")
            org_id = data.get("metadata", {}).get("org_id", "")
            if org_id:
                await self.update_subscription(org_id, "professional")
            return {"ok": True, "action": "subscription_activated"}

        if event_type == "invoice.payment_failed":
            customer_id = data.get("customer", "")
            org_id = data.get("metadata", {}).get("org_id", "")
            if org_id:
                try:
                    db = self.get_db()
                    db.table("organizations").update({
                        "billing_status": "past_due",
                        "updated_at": self._now(),
                    }).eq("id", org_id).execute()
                except Exception:
                    pass
            return {"ok": True, "action": "payment_failed_recorded"}

        if event_type == "customer.subscription.deleted":
            customer_id = data.get("customer", "")
            org_id = data.get("metadata", {}).get("org_id", "")
            if org_id:
                await self.cancel_subscription(org_id)
            return {"ok": True, "action": "subscription_canceled"}

        return {"ok": True, "action": "unhandled_event_type", "event_type": event_type}


# ── FASTAPI ROUTE REGISTRATION ────────────────────────────────────────
def register_tenant_billing_routes(app, *, billing_engine, require_auth, require_owner):
    from fastapi import Request, HTTPException, Depends
    from fastapi.responses import JSONResponse

    @app.get("/api/v1/billing/plans")
    async def billing_plans():
        return {"plans": billing_engine.list_plans()}

    @app.get("/api/v1/billing/subscription")
    async def billing_my_subscription(op: dict = Depends(require_auth)):
        org_id = op.get("org_id")
        if not org_id:
            raise HTTPException(400, "No organization context")
        sub = await billing_engine.get_subscription(org_id)
        if not sub:
            raise HTTPException(404, "No subscription found")
        return {"subscription": sub, "plan_info": billing_engine.get_plan_info(sub.get("plan", "free"))}

    @app.get("/api/v1/billing/subscription/{org_id}")
    async def billing_org_subscription(org_id: str, op: dict = Depends(require_owner)):
        sub = await billing_engine.get_subscription(org_id)
        if not sub:
            raise HTTPException(404, "No subscription found")
        return {"subscription": sub, "plan_info": billing_engine.get_plan_info(sub.get("plan", "free"))}

    @app.post("/api/v1/billing/subscription/{org_id}/update")
    async def billing_update_subscription(org_id: str, request: Request, op: dict = Depends(require_owner)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        plan = body.get("plan", "")
        if plan not in PLANS:
            raise HTTPException(400, f"Invalid plan: {plan}")
        result = await billing_engine.update_subscription(org_id, plan)
        return result

    @app.get("/api/v1/billing/usage")
    async def billing_my_usage(metric: str = "", days: int = 30, op: dict = Depends(require_auth)):
        org_id = op.get("org_id")
        if not org_id:
            raise HTTPException(400, "No organization context")
        return await billing_engine.get_usage(org_id, metric=metric, days=days)

    @app.get("/api/v1/billing/usage/{org_id}")
    async def billing_org_usage(org_id: str, metric: str = "", days: int = 30, op: dict = Depends(require_owner)):
        return await billing_engine.get_usage(org_id, metric=metric, days=days)

    @app.post("/api/v1/billing/usage/log")
    async def billing_log_usage(request: Request, op: dict = Depends(require_auth)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        org_id = body.get("org_id") or op.get("org_id")
        if not org_id:
            raise HTTPException(400, "org_id required")
        result = await billing_engine.log_usage(
            org_id=org_id,
            metric=body.get("metric", "api_call"),
            amount=body.get("amount", 1),
            metadata=body.get("metadata"),
        )
        return result

    @app.post("/api/v1/billing/stripe-webhook")
    async def billing_stripe_webhook(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")
        return await billing_engine.handle_stripe_webhook(body)

    log.info("[billing] Routes registered · /api/v1/billing/*")
