"""
Empire AI · Market Eye Product
===============================
Competitive intelligence & market monitoring.
Monitors competitor websites, reviews, pricing, and generates
weekly competitive briefs.

Tiers: MARKET_EYE_STARTER ($199) · MARKET_EYE_GROWTH ($499) · MARKET_EYE_ENTERPRISE ($999)
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

log = logging.getLogger("empire.market_eye")

# ── Tier limits ──────────────────────────────────────────────────────────────
TIER_LIMITS = {
    "MARKET_EYE_STARTER":    {"max_checks": 500,  "brief": False, "alerts": False},
    "MARKET_EYE_GROWTH":     {"max_checks": 2000, "brief": True,  "alerts": True},
    "MARKET_EYE_ENTERPRISE": {"max_checks": 10000,"brief": True,  "alerts": True},
}

# ── Pydantic models ─────────────────────────────────────────────────────────
class CompetitorCreate(BaseModel):
    name: str
    website: str
    niche: str = ""
    notes: str = ""


class MarketEye:
    """Market Eye engine — competitive intelligence monitoring."""

    def __init__(self, guard: Optional[Callable] = None):
        self.guard = guard
        self.stats = {"competitors": 0, "scrapes": 0, "briefs": 0, "alerts": 0}
        self._competitors: Dict[str, dict] = {}  # in-memory for now

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": True, "tier": "MARKET_EYE_GROWTH", "limits": TIER_LIMITS["MARKET_EYE_GROWTH"]}
        result = await self.guard(account_id, "market_eye")
        if not result.get("ok"):
            return result
        tier = result.get("tier", "MARKET_EYE_STARTER")
        return {"ok": True, "tier": tier, "limits": TIER_LIMITS.get(tier, TIER_LIMITS["MARKET_EYE_STARTER"])}

    def add_competitor(self, name: str, website: str, niche: str = "", notes: str = "") -> dict:
        """Register a competitor to monitor."""
        cid = f"comp_{len(self._competitors) + 1}"
        self._competitors[cid] = {
            "id": cid, "name": name, "website": website,
            "niche": niche, "notes": notes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_scraped": None,
        }
        self.stats["competitors"] += 1
        return self._competitors[cid]

    def list_competitors(self) -> list:
        return list(self._competitors.values())

    def scrape_competitor(self, competitor_id: str) -> dict:
        """Scrape a competitor's website for changes."""
        comp = self._competitors.get(competitor_id)
        if not comp:
            return {"error": "Competitor not found"}
        self.stats["scrapes"] += 1
        comp["last_scraped"] = datetime.now(timezone.utc).isoformat()
        # Basic scrape — fetch page and extract key info
        try:
            import httpx
            r = httpx.get(comp["website"], timeout=15.0, follow_redirects=True)
            content = r.text[:5000]
            # Extract title as a basic signal
            title = ""
            if "<title>" in content:
                title = content.split("<title>")[1].split("</title>")[0]
            comp["last_title"] = title
            comp["last_status"] = r.status_code
            return {
                "competitor": comp["name"],
                "status_code": r.status_code,
                "title": title,
                "content_length": len(r.text),
                "scraped_at": comp["last_scraped"],
            }
        except Exception as e:
            return {"error": f"Scrape failed: {str(e)[:200]}"}

    def generate_brief(self) -> dict:
        """Generate a competitive intelligence brief."""
        self.stats["briefs"] += 1
        if not self._competitors:
            return {"error": "No competitors registered", "brief": None}
        briefs = []
        for cid, comp in self._competitors.items():
            scrape = self.scrape_competitor(cid)
            briefs.append({
                "competitor": comp["name"],
                "website": comp["website"],
                "niche": comp.get("niche", ""),
                "last_scraped": comp.get("last_scraped"),
                "scrape_result": scrape,
            })
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "competitor_count": len(briefs),
            "briefs": briefs,
            "summary": f"Monitorando {len(briefs)} competitors across {len(set(c.get('niche') for c in self._competitors.values()))} niches",
        }

    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "limits": TIER_LIMITS,
            "tiers": list(TIER_LIMITS.keys()),
            "competitors": len(self._competitors),
        }


class MarketEyeRoutes:
    """FastAPI route registration for Market Eye product."""

    def __init__(self, engine: MarketEye, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app: FastAPI):
        require_auth = self.require_auth

        @app.get("/api/v6/suite/market-eye/health")
        async def market_eye_health(auth: bool = Depends(require_auth) if require_auth else None):
            return {"status": "operational", "service": "market_eye", "timestamp": datetime.now(timezone.utc).isoformat()}

        @app.post("/api/v6/suite/market-eye/competitors")
        async def market_eye_add_competitor(body: CompetitorCreate, auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.add_competitor(body.name, body.website, body.niche, body.notes)

        @app.get("/api/v6/suite/market-eye/competitors")
        async def market_eye_list_competitors(auth: bool = Depends(require_auth) if require_auth else None):
            return {"competitors": self.engine.list_competitors(), "count": len(self.engine._competitors)}

        @app.post("/api/v6/suite/market-eye/scrape/{competitor_id}")
        async def market_eye_scrape(competitor_id: str, auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.scrape_competitor(competitor_id)

        @app.get("/api/v6/suite/market-eye/brief")
        async def market_eye_brief(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.generate_brief()

        @app.get("/api/v6/suite/market-eye/stats")
        async def market_eye_stats(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.stats_snapshot()

        log.info("[market_eye] Routes registered · /api/v6/suite/market-eye/*")
