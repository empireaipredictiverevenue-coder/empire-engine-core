"""
Empire AI · Contractor Exchange Product
========================================
Vetted contractor marketplace wrapping existing contractor onboarding
and dispatch infrastructure with tier-based API, trust scoring, and
automated job matching.

Tiers: CONTRACTOR_EXCHANGE_STARTER ($299) · CONTRACTOR_EXCHANGE_GROWTH ($599)
       CONTRACTOR_EXCHANGE_ENTERPRISE ($999)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Callable, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

log = logging.getLogger("empire.contractor_exchange")

# ── Tier limits ──────────────────────────────────────────────────────────────
TIER_LIMITS = {
    "CONTRACTOR_EXCHANGE_STARTER":    {"max_checks": 500,  "matching": True,  "vetting": False},
    "CONTRACTOR_EXCHANGE_GROWTH":     {"max_checks": 2000, "matching": True,  "vetting": True},
    "CONTRACTOR_EXCHANGE_ENTERPRISE": {"max_checks": 10000,"matching": True,  "vetting": True},
}

# ── Pydantic models ─────────────────────────────────────────────────────────
class ContractorFilter(BaseModel):
    metro: str = ""
    specialty: str = ""
    min_trust_score: float = 0.0
    limit: int = 50


class ContractorExchange:
    """Contractor Exchange engine — wraps existing contractor infra."""

    def __init__(self, guard: Optional[Callable] = None, get_db: Optional[Callable] = None):
        self.guard = guard
        self.get_db = get_db
        self.stats = {"contractors": 0, "matches": 0, "searches": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": True, "tier": "CONTRACTOR_EXCHANGE_GROWTH", "limits": TIER_LIMITS["CONTRACTOR_EXCHANGE_GROWTH"]}
        result = await self.guard(account_id, "contractor_exchange")
        if not result.get("ok"):
            return result
        tier = result.get("tier", "CONTRACTOR_EXCHANGE_STARTER")
        return {"ok": True, "tier": tier, "limits": TIER_LIMITS.get(tier, TIER_LIMITS["CONTRACTOR_EXCHANGE_STARTER"])}

    def list_contractors(self, metro: str = "", specialty: str = "", min_score: float = 0.0, limit: int = 50) -> list:
        """List vetted contractors with optional filters."""
        self.stats["searches"] += 1
        try:
            if not self.get_db:
                return [{"error": "No database connection"}]
            db = self.get_db()
            q = db.table("contractors").select("*").eq("active", True)
            if metro:
                q = q.ilike("metro", f"%{metro}%")
            if min_score > 0:
                q = q.gte("trust_score", min_score)
            if specialty:
                q = q.contains("specialties", [specialty])
            rows = q.limit(limit).execute().data or []
            self.stats["contractors"] = len(rows)
            return rows
        except Exception as e:
            return [{"error": str(e)[:200]}]

    def get_contractor(self, contractor_id: str) -> Optional[dict]:
        """Get a single contractor by ID."""
        try:
            if not self.get_db:
                return None
            db = self.get_db()
            r = db.table("contractors").select("*").eq("id", contractor_id).limit(1).execute()
            return r.data[0] if r.data else None
        except Exception:
            return None

    def match_contractors(self, metro: str, specialty: str = "", limit: int = 5) -> list:
        """Match contractors to a job by metro + specialty, sorted by trust_score."""
        self.stats["matches"] += 1
        try:
            if not self.get_db:
                return []
            db = self.get_db()
            q = db.table("contractors").select("*").eq("active", True).ilike("metro", f"%{metro}%")
            if specialty:
                q = q.contains("specialties", [specialty])
            rows = q.order("trust_score", desc=True).limit(limit).execute().data or []
            return [
                {
                    "id": r["id"], "name": r.get("name", ""),
                    "metro": r.get("metro", ""), "specialties": r.get("specialties", []),
                    "trust_score": r.get("trust_score", 0), "completed_jobs": r.get("completed_jobs", 0),
                }
                for r in rows
            ]
        except Exception as e:
            return [{"error": str(e)[:200]}]

    def trust_score_distribution(self) -> dict:
        """Return trust score distribution for dashboard."""
        try:
            if not self.get_db:
                return {}
            db = self.get_db()
            rows = db.table("contractors").select("trust_score,active").limit(500).execute().data or []
            active = [r for r in rows if r.get("active")]
            if not active:
                return {"avg_score": 0, "count": 0, "distribution": {}}
            scores = [float(r.get("trust_score", 0)) for r in active]
            return {
                "avg_score": round(sum(scores) / len(scores), 1),
                "count": len(active),
                "max_score": max(scores),
                "min_score": min(scores),
            }
        except Exception:
            return {"avg_score": 0, "count": 0}

    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "limits": TIER_LIMITS,
            "tiers": list(TIER_LIMITS.keys()),
        }


class ContractorExchangeRoutes:
    """FastAPI route registration for Contractor Exchange product."""

    def __init__(self, engine: ContractorExchange, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app: FastAPI):
        require_auth = self.require_auth

        @app.get("/api/v6/suite/contractor-exchange/health")
        async def ce_health(auth: bool = Depends(require_auth) if require_auth else None):
            return {"status": "operational", "service": "contractor_exchange", "timestamp": datetime.now(timezone.utc).isoformat()}

        @app.get("/api/v6/suite/contractor-exchange/contractors")
        async def ce_list_contractors(
            metro: str = "", specialty: str = "", min_score: float = 0.0, limit: int = 50,
            auth: bool = Depends(require_auth) if require_auth else None,
        ):
            return {
                "contractors": self.engine.list_contractors(metro, specialty, min_score, min(limit, 200)),
                "count": 0,
            }

        @app.get("/api/v6/suite/contractor-exchange/contractors/{contractor_id}")
        async def ce_get_contractor(contractor_id: str, auth: bool = Depends(require_auth) if require_auth else None):
            c = self.engine.get_contractor(contractor_id)
            if not c:
                raise HTTPException(404, "Contractor not found")
            return c

        @app.get("/api/v6/suite/contractor-exchange/match")
        async def ce_match(
            metro: str = "", specialty: str = "", limit: int = 5,
            auth: bool = Depends(require_auth) if require_auth else None,
        ):
            return {
                "matches": self.engine.match_contractors(metro, specialty, min(limit, 20)),
                "query": {"metro": metro, "specialty": specialty},
            }

        @app.get("/api/v6/suite/contractor-exchange/trust-distribution")
        async def ce_trust_distribution(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.trust_score_distribution()

        @app.get("/api/v6/suite/contractor-exchange/stats")
        async def ce_stats(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.stats_snapshot()

        log.info("[contractor_exchange] Routes registered · /api/v6/suite/contractor-exchange/*")
