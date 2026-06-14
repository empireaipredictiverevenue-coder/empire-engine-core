"""
Empire AI · Content Pulse Product
==================================
Automated SEO-optimized content generation.
Wraps bots/seo_agent.py (SEOAgent) and bots/content_agent.py (ContentAgent)
with tier-based API, usage metering, and entitlement gating.

Tiers: CONTENT_PULSE_STARTER ($99) · CONTENT_PULSE_GROWTH ($249) · CONTENT_PULSE_ENTERPRISE ($499)
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

log = logging.getLogger("empire.content_pulse")

# ── Tier limits ──────────────────────────────────────────────────────────────
TIER_LIMITS = {
    "CONTENT_PULSE_STARTER":    {"max_checks": 500,  "landing_pages": True,  "bulk": False},
    "CONTENT_PULSE_GROWTH":     {"max_checks": 2000, "landing_pages": True,  "bulk": True},
    "CONTENT_PULSE_ENTERPRISE": {"max_checks": 10000,"landing_pages": True,  "bulk": True},
}

# ── Pydantic models ─────────────────────────────────────────────────────────
class ContentGenerateRequest(BaseModel):
    keyword: str = ""
    niche: str = "Roofing Restoration"
    metro: str = ""
    content_type: str = "landing_page"  # landing_page | property_desc | neighborhood | storm_risk | email_content
    address: str = ""
    style: str = "cinematic"


class ContentPulse:
    """Content Pulse engine — wraps SEOAgent and ContentAgent for content generation."""

    def __init__(self, guard: Optional[Callable] = None):
        self.guard = guard
        self.stats = {"generations": 0, "landing_pages": 0, "audits": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": True, "tier": "CONTENT_PULSE_GROWTH", "limits": TIER_LIMITS["CONTENT_PULSE_GROWTH"]}
        result = await self.guard(account_id, "content_pulse")
        if not result.get("ok"):
            return result
        tier = result.get("tier", "CONTENT_PULSE_STARTER")
        return {"ok": True, "tier": tier, "limits": TIER_LIMITS.get(tier, TIER_LIMITS["CONTENT_PULSE_STARTER"])}

    async def generate(self, req: ContentGenerateRequest) -> dict:
        """Generate SEO-optimized content."""
        self.stats["generations"] += 1
        if req.content_type == "landing_page":
            self.stats["landing_pages"] += 1
        try:
            from bots.seo_agent import get_seo_agent
            agent = get_seo_agent()
            result = await agent.generate_content(req.keyword, req.niche, req.metro)
            if result:
                return result
            # Fallback to ContentAgent for landing pages
            from bots.content_agent import get_content_agent
            content_agent = get_content_agent()
            if req.content_type == "landing_page":
                return await content_agent.generate_landing_page(
                    address=req.address, metro=req.metro, niche=req.niche, style=req.style,
                )
            elif req.content_type == "email_content":
                return await content_agent.generate_email_content(
                    {"address": req.address}, None, req.niche,
                )
            elif req.content_type == "storm_risk":
                return await content_agent.generate_storm_risk_content(
                    {}, None, req.niche,
                )
            return {"error": f"Unknown content type: {req.content_type}"}
        except Exception as e:
            return {"error": f"Generation failed: {str(e)[:200]}"}

    async def audit(self, url: str, niche: str = "Local SEO & HVAC") -> dict:
        """Run an SEO audit on a website."""
        self.stats["audits"] += 1
        try:
            from bots.seo_agent import get_seo_agent
            agent = get_seo_agent()
            return await agent.audit_site(url, niche)
        except Exception as e:
            return {"error": f"Audit failed: {str(e)[:200]}"}

    async def performance(self) -> dict:
        """Return content generation performance snapshot."""
        try:
            from bots.content_agent import get_content_agent
            content_agent = get_content_agent()
            return await content_agent.performance_snapshot()
        except Exception:
            return {"stats": dict(self.stats)}

    def stats_snapshot(self) -> dict:
        return {
            "engine": dict(self.stats),
            "limits": TIER_LIMITS,
            "tiers": list(TIER_LIMITS.keys()),
        }


class ContentPulseRoutes:
    """FastAPI route registration for Content Pulse product."""

    def __init__(self, engine: ContentPulse, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app: FastAPI):
        require_auth = self.require_auth

        @app.get("/api/v6/suite/content-pulse/health")
        async def content_pulse_health(auth: bool = Depends(require_auth) if require_auth else None):
            return {"status": "operational", "service": "content_pulse", "timestamp": datetime.now(timezone.utc).isoformat()}

        @app.post("/api/v6/suite/content-pulse/generate")
        async def content_pulse_generate(body: ContentGenerateRequest, auth: bool = Depends(require_auth) if require_auth else None):
            return await self.engine.generate(body)

        @app.post("/api/v6/suite/content-pulse/audit")
        async def content_pulse_audit(url: str, niche: str = "Local SEO & HVAC", auth: bool = Depends(require_auth) if require_auth else None):
            return await self.engine.audit(url, niche)

        @app.get("/api/v6/suite/content-pulse/performance")
        async def content_pulse_performance(auth: bool = Depends(require_auth) if require_auth else None):
            return await self.engine.performance()

        @app.get("/api/v6/suite/content-pulse/stats")
        async def content_pulse_stats(auth: bool = Depends(require_auth) if require_auth else None):
            return self.engine.stats_snapshot()

        log.info("[content_pulse] Routes registered · /api/v6/suite/content-pulse/*")
