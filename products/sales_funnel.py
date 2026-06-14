"""
Empire AI · Sales Funnel Engine
================================
One-time purchase flows, trial signup → activation, upgrade/downgrade paths,
renewal reminders, and churn prevention. Works alongside SuiteSubscriptionEngine
for subscription management and EmailEngine/SMSEngine for sequence delivery.

13 products with 3 tiers each = 39 SKUs tracked through the funnel.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel

log = logging.getLogger("empire.sales_funnel")

# ── Product catalog with all 13 products ─────────────────────────────────────
PRODUCT_CATALOG = {
    "inbound_router": {
        "name": "Inbound Router",
        "tiers": {"ROUTER_SaaS": {"price": 499, "checks": 500, "features": ["call triage", "multi-channel dispatch", "urgency scoring"]}},
    },
    "data_vault": {
        "name": "Data Vault",
        "tiers": {"DATA_ENTERPRISE": {"price": 799, "checks": 50000, "features": ["retention policies", "encryption", "audit trail"]}},
    },
    "buyer_spy": {
        "name": "Buyer Spy AI",
        "tiers": {"SPY_DATA": {"price": 1499, "checks": 100, "features": ["transcript analysis", "network mapping", "buying signals"]}},
    },
    "lead_score": {
        "name": "LeadScore AI",
        "tiers": {
            "LEADSCORE_STARTER":    {"price": 299,  "checks": 500,  "features": ["Bayesian scoring", "basic reports"]},
            "LEADSCORE_GROWTH":     {"price": 599,  "checks": 2000, "features": ["advanced models", "batch scoring", "export"]},
            "LEADSCORE_ENTERPRISE": {"price": 999,  "checks": 10000,"features": ["custom models", "API access", "SLA"]},
        },
    },
    "compliant": {
        "name": "Compliant",
        "tiers": {
            "COMPLIANT_STARTER":    {"price": 199,  "checks": 500,  "features": ["TCPA check", "DNC scan"]},
            "COMPLIANT_GROWTH":     {"price": 499,  "checks": 2000, "features": ["quiet hours", "opt-out mgmt", "audit log"]},
            "COMPLIANT_ENTERPRISE": {"price": 999,  "checks": 10000,"features": ["custom rules", "bulk check", "compliance report"]},
        },
    },
    "strike_campaigns": {
        "name": "Strike Campaigns",
        "tiers": {
            "STRIKE_STARTER":    {"price": 99,   "checks": 5,   "features": ["5 campaigns", "SMS only"]},
            "STRIKE_GROWTH":     {"price": 249,  "checks": 25,  "features": ["SMS + email", "analytics", "A/B testing"]},
            "STRIKE_ENTERPRISE": {"price": 499,  "checks": 100, "features": ["unlimited", "all channels", "SI optimization"]},
        },
    },
    "forecast": {
        "name": "Forecast",
        "tiers": {
            "FORECAST_LITE":       {"price": 199,  "checks": 500,  "features": ["per-lane pipeline", "health alerts"]},
            "FORECAST_PRO":        {"price": 499,  "checks": 2000, "features": ["LLM narrative", "accuracy tracking", "SI evolution"]},
            "FORECAST_ENTERPRISE": {"price": 999,  "checks": 10000,"features": ["what-if scenarios", "multi-account", "export"]},
        },
    },
    "market_eye": {
        "name": "Market Eye",
        "tiers": {
            "MARKET_EYE_STARTER":    {"price": 199,  "checks": 500,  "features": ["competitor tracking"]},
            "MARKET_EYE_GROWTH":     {"price": 499,  "checks": 2000, "features": ["weekly briefs", "alerts", "scraping"]},
            "MARKET_EYE_ENTERPRISE": {"price": 999,  "checks": 10000,"features": ["unlimited", "custom sources", "API"]},
        },
    },
    "content_pulse": {
        "name": "Content Pulse",
        "tiers": {
            "CONTENT_PULSE_STARTER":    {"price": 99,   "checks": 500,  "features": ["landing pages", "basic SEO"]},
            "CONTENT_PULSE_GROWTH":     {"price": 249,  "checks": 2000, "features": ["bulk generation", "email content", "audits"]},
            "CONTENT_PULSE_ENTERPRISE": {"price": 499,  "checks": 10000,"features": ["unlimited", "custom templates", "API"]},
        },
    },
    "contractor_exchange": {
        "name": "Contractor Exchange",
        "tiers": {
            "CONTRACTOR_EXCHANGE_STARTER":    {"price": 299,  "checks": 500,  "features": ["contractor list", "search"]},
            "CONTRACTOR_EXCHANGE_GROWTH":     {"price": 599,  "checks": 2000, "features": ["trust scoring", "vetting", "matching"]},
            "CONTRACTOR_EXCHANGE_ENTERPRISE": {"price": 999,  "checks": 10000,"features": ["unlimited", "API", "custom workflow"]},
        },
    },
}

# ── Upsell paths — tier → recommended_next_tier ──────────────────────────────
UPSELL_PATHS = {
    "LEADSCORE_STARTER":           "LEADSCORE_GROWTH",
    "LEADSCORE_GROWTH":            "LEADSCORE_ENTERPRISE",
    "COMPLIANT_STARTER":           "COMPLIANT_GROWTH",
    "COMPLIANT_GROWTH":            "COMPLIANT_ENTERPRISE",
    "STRIKE_STARTER":              "STRIKE_GROWTH",
    "STRIKE_GROWTH":               "STRIKE_ENTERPRISE",
    "FORECAST_LITE":               "FORECAST_PRO",
    "FORECAST_PRO":                "FORECAST_ENTERPRISE",
    "MARKET_EYE_STARTER":          "MARKET_EYE_GROWTH",
    "MARKET_EYE_GROWTH":           "MARKET_EYE_ENTERPRISE",
    "CONTENT_PULSE_STARTER":       "CONTENT_PULSE_GROWTH",
    "CONTENT_PULSE_GROWTH":        "CONTENT_PULSE_ENTERPRISE",
    "CONTRACTOR_EXCHANGE_STARTER": "CONTRACTOR_EXCHANGE_GROWTH",
    "CONTRACTOR_EXCHANGE_GROWTH":  "CONTRACTOR_EXCHANGE_ENTERPRISE",
}

UPGRADE_MONTHLY_SAVINGS = {
    "LEADSCORE_STARTER→GROWTH":   300,   # $599 - $299 = $300/mo more
    "COMPLIANT_STARTER→GROWTH":   300,
    "STRIKE_STARTER→GROWTH":      150,
    "FORECAST_LITE→PRO":          300,
    "CONTENT_PULSE_STARTER→GROWTH": 150,
    "CONTRACTOR_EXCHANGE_STARTER→GROWTH": 300,
}

# ── Trial config per product ─────────────────────────────────────────────────
TRIAL_CONFIG = {
    # product_slug -> {days, checks, trial_tier (default: computed as {UPPER}_STARTER)}
    "lead_score":           {"days": 14, "checks": 50, "trial_tier": "LEADSCORE_STARTER"},
    "compliant":            {"days": 7,  "checks": 25, "trial_tier": "COMPLIANT_STARTER"},
    "strike_campaigns":     {"days": 7,  "checks": 2,  "trial_tier": "STRIKE_STARTER"},
    "forecast":             {"days": 14, "checks": 50, "trial_tier": "FORECAST_LITE"},
    "market_eye":           {"days": 7,  "checks": 25, "trial_tier": "MARKET_EYE_STARTER"},
    "content_pulse":        {"days": 7,  "checks": 25, "trial_tier": "CONTENT_PULSE_STARTER"},
    "contractor_exchange":  {"days": 14, "checks": 50, "trial_tier": "CONTRACTOR_EXCHANGE_STARTER"},
}

# ── Pydantic models ─────────────────────────────────────────────────────────
class TrialSignup(BaseModel):
    email: str
    product_slug: str
    name: str = ""
    company: str = ""


class OneTimePurchase(BaseModel):
    customer_account_id: str
    product_slug: str
    tier: str
    promo_code: str = ""


class SalesFunnelEngine:
    """Sales funnel engine — handles one-time purchases, trials, upsells, renewals."""

    def __init__(
        self,
        get_db: Optional[Callable] = None,
        guard: Optional[Callable] = None,
        subscriptions: Optional[object] = None,
    ):
        self.get_db = get_db
        self.guard = guard
        self.subscriptions = subscriptions  # SuiteSubscriptionEngine instance
        self.stats = {"trials": 0, "purchases": 0, "upsells": 0, "renewals": 0, "churn": 0}

    # ── Trial signup ────────────────────────────────────────────────────────
    async def start_trial(self, req: TrialSignup) -> dict:
        """Start a free trial for a product."""
        self.stats["trials"] += 1
        config = TRIAL_CONFIG.get(req.product_slug)
        if not config:
            return {"ok": False, "error": f"Product '{req.product_slug}' not available for trial"}

        try:
            db = self.get_db()
            # Check if already trialed
            existing = db.table("sales_events") \
                .select("*") \
                .eq("email", req.email) \
                .eq("product_slug", req.product_slug) \
                .eq("event_type", "trial_start") \
                .limit(1) \
                .execute()
            if existing.data:
                return {"ok": False, "error": "Trial already started for this product", "existing": existing.data[0]}

            # Create trial subscription via SuiteSubscriptionEngine if available
            subscription_id = None
            tier = config.get("trial_tier", f"{req.product_slug.upper()}_STARTER")
            if self.subscriptions and req.email:
                sub_result = self.subscriptions.create_subscription(
                    customer_account_id=req.email,
                    tier_level=tier,
                    monthly_recurring_revenue=0.0,
                    notes=f"Free trial — {config['days']} days",
                )
                if sub_result.get("ok"):
                    subscription_id = sub_result.get("subscription_id")

            trial_end = (datetime.now(timezone.utc) + timedelta(days=config["days"])).isoformat()
            # Log trial event
            db.table("sales_events").insert({
                "email": req.email,
                "product_slug": req.product_slug,
                "event_type": "trial_start",
                "tier": tier,
                "trial_end": trial_end,
                "max_checks": config["checks"],
                "name": req.name,
                "company": req.company,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            return {
                "ok": True,
                "subscription_id": subscription_id,
                "product": req.product_slug,
                "tier": tier,
                "trial_days": config["days"],
                "max_checks": config["checks"],
                "trial_ends": trial_end,
            }
        except Exception as e:
            log.error(f"[sales] trial start failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    # ── One-time purchase ───────────────────────────────────────────────────
    async def purchase(self, req: OneTimePurchase) -> dict:
        """Process a one-time purchase or subscription signup."""
        self.stats["purchases"] += 1
        product = PRODUCT_CATALOG.get(req.product_slug)
        if not product:
            return {"ok": False, "error": f"Unknown product: {req.product_slug}"}
        tier_data = product["tiers"].get(req.tier)
        if not tier_data:
            return {"ok": False, "error": f"Unknown tier '{req.tier}' for product '{req.product_slug}'"}

        # Apply promo code if provided (simple 20% off for now)
        price = tier_data["price"]
        if req.promo_code and req.promo_code.upper() == "LAUNCH20":
            price = round(price * 0.8, 2)

        try:
            db = self.get_db()
            db.table("sales_events").insert({
                "customer_account_id": req.customer_account_id,
                "product_slug": req.product_slug,
                "event_type": "purchase",
                "tier": req.tier,
                "amount_usd": price,
                "promo_code": req.promo_code,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            # Create actual subscription via SuiteSubscriptionEngine if available
            subscription_id = None
            if self.subscriptions:
                sub_result = self.subscriptions.create_subscription(
                    customer_account_id=req.customer_account_id,
                    tier_level=req.tier,
                    monthly_recurring_revenue=price,
                    notes=f"Purchase via sales funnel — {'promo: ' + req.promo_code if req.promo_code else 'full price'}",
                )
                if sub_result.get("ok"):
                    subscription_id = sub_result.get("subscription_id")

            return {
                "ok": True,
                "subscription_id": subscription_id,
                "product": req.product_slug,
                "tier": req.tier,
                "price": price,
                "promo_applied": bool(req.promo_code),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── Upsell recommendation ───────────────────────────────────────────────
    def suggest_upsell(self, current_tier: str, usage_pct: float = 0.0) -> Optional[dict]:
        """Given a current tier and usage %, suggest the next tier up."""
        next_tier = UPSELL_PATHS.get(current_tier)
        if not next_tier:
            return None
        # Find which product this tier belongs to
        for slug, product in PRODUCT_CATALOG.items():
            if current_tier in product["tiers"]:
                next_data = product["tiers"].get(next_tier)
                current_data = product["tiers"][current_tier]
                if not next_data:
                    return None
                return {
                    "product": slug,
                    "product_name": product["name"],
                    "current_tier": current_tier,
                    "current_price": current_data["price"],
                    "suggested_tier": next_tier,
                    "suggested_price": next_data["price"],
                    "price_increase": next_data["price"] - current_data["price"],
                    "additional_features": next_data["features"],
                    "usage_pct": usage_pct,
                    "upsell_reason": "usage" if usage_pct > 75 else "features",
                }
        return None

    # ── Renewal reminder ────────────────────────────────────────────────────
    def renewal_reminder(self, days_until_expiry: int, tier: str, price: float) -> dict:
        """Build renewal reminder data."""
        urgency = "critical" if days_until_expiry <= 3 else ("warning" if days_until_expiry <= 7 else "info")
        return {
            "days_until_expiry": days_until_expiry,
            "tier": tier,
            "price": price,
            "urgency": urgency,
            "action_url": "/command#/products",
        }

    # ── Churn prediction ────────────────────────────────────────────────────
    def churn_risk(self, days_since_last_use: int, usage_count: int) -> dict:
        """Predict churn risk based on inactivity and usage patterns."""
        if days_since_last_use > 30 or usage_count == 0:
            risk = "high"
            action = "reactivation_email"
        elif days_since_last_use > 14:
            risk = "medium"
            action = "engagement_email"
        else:
            risk = "low"
            action = None
        return {"risk": risk, "days_inactive": days_since_last_use, "recommended_action": action}

    # ── Stats snapshot ──────────────────────────────────────────────────────
    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "products": len(PRODUCT_CATALOG),
            "upsell_paths": len(UPSELL_PATHS),
            "trial_products": list(TRIAL_CONFIG.keys()),
        }


class SalesFunnelRoutes:
    """FastAPI route registration for Sales Funnel."""

    def __init__(self, engine: SalesFunnelEngine, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app: FastAPI):
        require_auth = self.require_auth

        @app.get("/api/v6/suite/sales/health")
        async def sales_health(auth: bool = Depends(require_auth) if require_auth else None):
            return {"status": "operational", "service": "sales_funnel", "timestamp": datetime.now(timezone.utc).isoformat()}

        @app.post("/api/v6/suite/sales/trial")
        async def sales_start_trial(body: TrialSignup, auth: bool = Depends(require_auth) if require_auth else None):
            return await self.engine.start_trial(body)

        @app.post("/api/v6/suite/sales/purchase")
        async def sales_purchase(body: OneTimePurchase, auth: bool = Depends(require_auth) if require_auth else None):
            result = await self.engine.purchase(body)
            if not result.get("ok"):
                raise HTTPException(400, result.get("error", "Purchase failed"))
            return result

        @app.get("/api/v6/suite/sales/upsell")
        async def sales_upsell(current_tier: str, usage_pct: float = 0.0, auth: bool = Depends(require_auth) if require_auth else None):
            suggestion = self.engine.suggest_upsell(current_tier, usage_pct)
            return {"suggestion": suggestion, "current_tier": current_tier}

        @app.get("/api/v6/suite/sales/catalog")
        async def sales_catalog(auth: bool = Depends(require_auth) if require_auth else None):
            """Return the full product catalog with pricing and features."""
            return {
                "products": {
                    slug: {
                        "name": data["name"],
                        "tiers": {
                            tier: {"price": t["price"], "checks": t["checks"], "features": t["features"]}
                            for tier, t in data["tiers"].items()
                        }
                    }
                    for slug, data in PRODUCT_CATALOG.items()
                },
                "trial_available": list(TRIAL_CONFIG.keys()),
                "upsell_paths": UPSELL_PATHS,
            }

        @app.get("/api/v6/suite/sales/churn-risk")
        async def sales_churn_risk(days_since_last_use: int = 0, usage_count: int = 0, auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.churn_risk(days_since_last_use, usage_count)

        @app.get("/api/v6/suite/sales/stats")
        async def sales_stats(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.stats_snapshot()

        log.info("[sales_funnel] Routes registered · /api/v6/suite/sales/*")
