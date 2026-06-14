"""
Empire AI · Forecast Product
=============================
Standalone predictive revenue forecasting product.
Wraps bots/predictive_revenue.py with tier-based API, usage metering,
and entitlement gating.

Tiers: FORECAST_LITE ($199) · FORECAST_PRO ($499) · FORECAST_ENTERPRISE ($999)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

log = logging.getLogger("empire.forecast")

# ── Tier limits ──────────────────────────────────────────────────────────────
TIER_LIMITS = {
    "FORECAST_LITE":       {"max_checks": 500,  "narrative": False, "what_if": False},
    "FORECAST_PRO":        {"max_checks": 2000, "narrative": True,  "what_if": False},
    "FORECAST_ENTERPRISE": {"max_checks": 10000,"narrative": True,  "what_if": True},
}

class Forecast:
    """Forecast product engine — wraps predictive revenue functions."""

    def __init__(self, guard: Optional[Callable] = None):
        self.guard = guard
        self.stats = {"snapshots": 0, "per_lane": 0, "health": 0, "accuracy": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        """Check subscription + feature access for forecast product."""
        if not self.guard:
            return {"ok": True, "tier": "FORECAST_PRO", "limits": TIER_LIMITS["FORECAST_PRO"]}
        result = await self.guard(account_id, "forecast")
        if not result.get("ok"):
            return result
        tier = result.get("tier", "FORECAST_LITE")
        return {"ok": True, "tier": tier, "limits": TIER_LIMITS.get(tier, TIER_LIMITS["FORECAST_LITE"])}

    def snapshot(self) -> dict:
        """Return comprehensive forecast."""
        self.stats["snapshots"] += 1
        try:
            from bots.predictive_revenue import adaptive_forecast
            return adaptive_forecast()
        except Exception as e:
            return {"error": str(e)[:200]}

    def per_lane(self) -> dict:
        """Return per-lane forecast breakdown."""
        self.stats["per_lane"] += 1
        try:
            from bots.predictive_revenue import per_lane_forecast
            return per_lane_forecast()
        except Exception as e:
            return {"error": str(e)[:200]}

    def health_check(self) -> dict:
        """Return revenue health status."""
        self.stats["health"] += 1
        try:
            from bots.predictive_revenue import revenue_health_check
            return revenue_health_check()
        except Exception as e:
            return {"error": str(e)[:200]}

    def accuracy_timeseries(self, days: int = 14) -> dict:
        """Return forecast vs actual accuracy time-series."""
        self.stats["accuracy"] += 1
        try:
            from bots.predictive_revenue import get_accuracy_timeseries
            return get_accuracy_timeseries(days=days)
        except Exception as e:
            return {"error": str(e)[:200]}

    def stats_snapshot(self) -> dict:
        """Return engine stats for dashboard."""
        return {
            "engine": dict(self.stats),
            "limits": TIER_LIMITS,
            "tiers": list(TIER_LIMITS.keys()),
        }


class ForecastRoutes:
    """FastAPI route registration for Forecast product."""

    def __init__(self, engine: Forecast, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app: FastAPI):
        require_auth = self.require_auth

        @app.get("/api/v6/suite/forecast/health")
        async def forecast_health(auth: bool = Depends(require_auth) if require_auth else None):
            return {"status": "operational", "service": "forecast", "timestamp": datetime.now(timezone.utc).isoformat()}

        @app.get("/api/v6/suite/forecast/snapshot")
        async def forecast_snapshot(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.snapshot()

        @app.get("/api/v6/suite/forecast/per-lane")
        async def forecast_per_lane(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.per_lane()

        @app.get("/api/v6/suite/forecast/health-check")
        async def forecast_health_check(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.health_check()

        @app.get("/api/v6/suite/forecast/accuracy")
        async def forecast_accuracy(days: int = 14, auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.accuracy_timeseries(days=max(1, min(90, days)))

        @app.get("/api/v6/suite/forecast/stats")
        async def forecast_stats(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.stats_snapshot()

        log.info("[forecast] Routes registered · /api/v6/suite/forecast/*")
