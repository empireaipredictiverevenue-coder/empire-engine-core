"""
EMPIRE V49 · PRODUCT 1: INBOUND ROUTER (Traffic Control)
=========================================================
Routes inbound leads through qualification, enrichment, and AI closer pipelines.
Part of the Suite Gateway monetization — only available to accounts with
inbound_router_enabled feature flag.

Integration:
    router = InboundRouter(suite_guard, suite_subscriptions)
    result = await router.route_lead(account_id, lead_data)
"""
import json as _json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.inbound_router")


class InboundRouter:
    """Route inbound leads through the Empire pipeline with tier-based caps,
    per-account routing rules, and usage metering."""

    def __init__(
        self,
        guard: Optional[Callable] = None,     # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {"routed": 0, "blocked": 0, "errors": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has inbound_router access. Returns gatecheck result."""
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "inbound_router")

    async def route_lead(self, account_id: str, lead_data: dict) -> dict:
        """Route a single lead through the inbound pipeline.
        Steps: 1) gatecheck → 2) enrich → 3) qualify → 4) dispatch.
        Returns routing result with tier-based processing.

        In the full product, this would call into empire_inbound.py,
        empire_enricher_ai.py, etc. For now, it's the service boundary
        that validates entitlement and meters usage."""
        # 1. Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied"),
                    "step": "entitlement"}

        # 2. Enrich (stub — real enrichment calls AI enricher)
        enriched = self._enrich(lead_data)

        # 3. Route decision
        route = self._decide_route(enriched)

        self.stats["routed"] += 1

        # 4. Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "inbound_router", "inbound_call",
                               quantity=1, metadata={"route": route, "lead_name": lead_data.get("name", "")})
            except Exception:
                pass

        return {
            "ok": True,
            "account_id": account_id,
            "lead_id": lead_data.get("id") or lead_data.get("lead_id", ""),
            "route": route,
            "tier": entitlement.get("tier", "unknown"),
            "enriched_fields": list(enriched.keys()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _enrich(self, lead: dict) -> dict:
        """Extract and normalize lead fields. In production, calls
        AIEnricher and appends derived data."""
        enriched = {}
        if lead.get("phone"):
            enriched["phone_normalized"] = lead["phone"].strip()
        if lead.get("email"):
            enriched["email_domain"] = lead["email"].split("@")[-1].lower() if "@" in lead["email"] else ""
        if lead.get("address"):
            enriched["address_normalized"] = lead["address"].strip().title()
        if lead.get("vertical") or lead.get("niche"):
            enriched["industry"] = lead.get("vertical") or lead.get("niche", "")
        return enriched

    @staticmethod
    def _decide_route(lead: dict) -> str:
        """Determine the best routing path for this lead based on enriched data.
        Returns one of: 'ai_closer', 'email_sequence', 'sms_blast', 'dispatch'."""
        industry = lead.get("industry", "").lower()
        if "roofing" in industry or "storm" in industry:
            return "ai_closer"
        if "legal" in industry:
            return "dispatch"
        return "email_sequence"

    def snapshot(self) -> dict:
        return {**self.stats}


class InboundRouterRoutes:
    """Wire InboundRouter endpoints into the FastAPI app.
    Used by the Suite Gateway or hub.py."""

    def __init__(self, router: InboundRouter, require_auth: Optional[Callable] = None):
        self.router = router
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/inbound-router/route")
        async def route_inbound(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Route a single lead through the inbound router pipeline.
            Body: {account_id, lead: {name, phone, ...}}"""
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            lead_data = body.get("lead") or body.get("lead_data", {})
            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(lead_data, dict) or not lead_data.get("name"):
                raise HTTPException(400, "lead must have a name")

            result = await self.router.route_lead(account_id, lead_data)
            status = 403 if result.get("step") == "entitlement" else (200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/inbound-router/stats")
        async def router_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.router.snapshot())

        log.info("[inbound-router] Routes registered")
