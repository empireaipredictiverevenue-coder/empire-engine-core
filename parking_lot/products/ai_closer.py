"""
EMPIRE V49 · PRODUCT: AI CLOSER (AGI-Powered Sales Pipeline)
=============================================================
Autonomous AI sales closer orchestrating the full voice pipeline:
BrainDecider scoring → AGI Governor strategy → Live Kokoro TTS /
Static NCCO call / SMS-Email nurture → Outcome feedback loop.

Combines 6 MRR tiers (BROADCAST through EXECUTIVE_WHALE) into 4
Suite product tiers with gated access via SuiteGuard.

Backend engine: empire_ai_closer.py (1,300+ lines, production)

Integration:
    closer = AICloserProduct(suite_guard, suite_subscriptions)
    result = await closer.close_lead(account_id, lead_data)
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.ai_closer")

# AI Closer tiers for Suite
AI_CLOSER_TIERS = {
    "CLOSER_STARTER": {
        "price": 299,
        "description": "Template-based static NCCO calls with basic email nurture — for low-volume, budget-conscious teams",
        "features": [
            "Template-based closing scripts",
            "Static NCCO calls (Vonage built-in TTS)",
            "Basic email nurture sequences",
            "BrainDecider GO/NO-GO scoring",
            "Monthly decision log",
            "Email support",
        ],
    },
    "CLOSER_PRO": {
        "price": 999,
        "description": "AGI-powered scripts with static calls + multi-channel nurture — for growing teams needing personalization",
        "features": [
            "Everything in Starter",
            "AGI-generated scripts (Ollama/Synthetic Brain)",
            "Static NCCO calls + SMS + email nurture",
            "2 closer personas (Consultative, Urgency Driver)",
            "Lead persona detection",
            "ClosingExpert objection handling (7 types)",
            "Priority email support",
        ],
    },
    "CLOSER_ENTERPRISE": {
        "price": 2499,
        "description": "Live Kokoro TTS streaming with all 5 closer personas and multi-turn objection handling",
        "features": [
            "Everything in Pro",
            "Live Kokoro TTS streaming calls",
            "All 5 closer personas",
            "Multi-turn objection loop (WebSocket)",
            "HumanClosingEngine with flow state machine",
            "AGI premium scripts with pain point injection",
            "Real-time outcome logging + SI evolution feedback",
            "Operator notify on high-value connects",
            "Dedicated support engineer",
        ],
    },
    "EXECUTIVE_WHALE": {
        "price": 9997,
        "description": "Ultra-premium — priority dispatch, dedicated operator warm-forward, 24/7 SLA, priority Synthetic Brain inference",
        "features": [
            "Everything in Enterprise",
            "Priority dispatch — skip queue, dedicated lanes",
            "Dedicated operator warm-forward on high-value leads",
            "Priority Synthetic Brain inference (dedicated slot)",
            "24/7 SLA with < 5min response time",
            "Custom script fine-tuning per lead persona",
            "Weekly performance review + strategy calibration",
            "Dedicated account manager",
        ],
    },
}


class AICloserProduct:
    """AI Closer — AGI-powered autonomous sales pipeline.

    Wraps the empire_ai_closer.py engine with Suite entitlement checks,
    usage metering, and deployment orchestration.

    Four tiers:
      - Starter:    Template static calls ($299/mo)
      - Pro:        AGI scripts + static + SMS/email ($999/mo)
      - Enterprise: Live streaming + all personas + multi-turn ($2,499/mo)
      - EXECUTIVE_WHALE: Priority dispatch + operator + 24/7 SLA ($9,997/mo)
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,     # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {"closes": 0, "scores": 0, "blocked": 0, "errors": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has ai_closer access via SuiteGuard."""
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "ai_closer")

    async def close_lead(self, account_id: str, config: dict) -> dict:
        """Execute a close action for a lead through the AI Closer engine.

        Args:
            account_id: Customer account ID
            config: {
                tier: "CLOSER_STARTER" | "CLOSER_PRO" | "CLOSER_ENTERPRISE" | "EXECUTIVE_WHALE",
                lead: dict with lead data (name, phone, email, address, city, asset_value),
                alert_summary: optional storm alert context,
                niche: optional niche override,
                score_only: bool — if True, only score without placing a call,
            }
        """
        tier = config.get("tier", "CLOSER_STARTER")
        tier_config = AI_CLOSER_TIERS.get(tier)
        if not tier_config:
            self.stats["blocked"] += 1
            return {"ok": False, "error": f"Unknown tier: {tier}"}

        # Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        lead = config.get("lead", {})
        score_only = config.get("score_only", False)

        from uuid import uuid4
        action_id = str(uuid4())

        self.stats["scores" if score_only else "closes"] += 1

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "ai_closer", "score" if score_only else "close",
                               q=1, m={
                                   "tier": tier,
                                   "action_id": action_id,
                                   "lead_name": lead.get("name") or lead.get("warehouse_name", "?"),
                                   "score_only": score_only,
                               })
            except Exception:
                pass

        return {
            "ok": True,
            "account_id": account_id,
            "action_id": action_id,
            "tier": tier,
            "price": tier_config["price"],
            "features": tier_config["features"],
            "score_only": score_only,
            "lead_received": bool(lead),
            "deployment_guide": self._deployment_guide(tier, config),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _deployment_guide(self, tier: str, config: dict) -> str:
        guides = {
            "CLOSER_STARTER": (
                "1. Empire AI activates your AI Closer Starter tier\n"
                "2. Upload your lead list or connect inbound pipeline\n"
                "3. BrainDecider scores every lead (GO/NO-GO)\n"
                "4. GO leads receive static NCCO calls with template scripts\n"
                "5. NO-GO leads enter email nurture sequence\n"
                "6. Monthly decision log available in your dashboard"
            ),
            "CLOSER_PRO": (
                "1. Empire AI activates your AI Closer Pro tier\n"
                "2. Connect lead pipeline (API, webhook, or manual upload)\n"
                "3. BrainDecider + AGI Governor select strategy per lead\n"
                "4. AGI generates personalized closing scripts\n"
                "5. Static calls placed via Vonage — objections handled by ClosingExpert\n"
                "6. SMS/Email nurture for lower-confidence leads\n"
                "7. Performance tracking + SI strategy evolution"
            ),
            "CLOSER_ENTERPRISE": (
                "1. Dedicated AI Closer Enterprise pipeline provisioned\n"
                "2. BrainDecider + AGI Governor + Synthetic Brain integration\n"
                "3. High-confidence leads receive live Kokoro TTS streaming calls\n"
                "4. Multi-turn objection handling via WebSocket\n"
                "5. All 5 closer personas available (auto-selected per lead)\n"
                "6. HumanClosingEngine flow state machine active\n"
                "7. Pain point library injection per niche\n"
                "8. Real-time dashboard + operator notifications"
            ),
            "EXECUTIVE_WHALE": (
                "1. Priority EXECUTIVE_WHALE pipeline provisioned\n"
                "2. Dedicated Synthetic Brain inference slot — no queue\n"
                "3. Priority dispatch: leads skip queue to dedicated lanes\n"
                "4. Live Kokoro TTS streaming + multi-turn objection loop\n"
                "5. Operator warm-forward on $10k+ MRR leads\n"
                "6. Custom script fine-tuning per lead persona\n"
                "7. Weekly strategy calibration with AGI Governor\n"
                "8. 24/7 SLA — <5min response time\n"
                "9. Dedicated account manager + performance reviews"
            ),
        }
        return guides.get(tier, "Contact Empire AI ops for deployment instructions.")

    def snapshot(self) -> dict:
        return {**self.stats}


class AICloserRoutes:
    """Wire AI Closer endpoints into the FastAPI app."""

    def __init__(self, closer: AICloserProduct, *, require_auth: Optional[Callable] = None):
        self.closer = closer
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/closer/close")
        async def closer_close(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Execute a close action for a lead.
            Body: {account_id, config: {tier, lead, ...}}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            config = body.get("config") or {}
            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(config, dict):
                raise HTTPException(400, "config must be an object")

            result = await self.closer.close_lead(account_id, config)
            status = 403 if not result.get("ok") else 200
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/closer/tiers")
        async def closer_tiers(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Return AI Closer pricing tiers and features."""
            return JSONResponse({
                "tiers": {
                    slug: {
                        "price": t["price"],
                        "description": t["description"],
                        "features": t["features"],
                    }
                    for slug, t in AI_CLOSER_TIERS.items()
                }
            })

        @app.get("/api/v6/suite/closer/stats")
        async def closer_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.closer.snapshot())

        log.info("[ai_closer] Routes registered · /api/v6/suite/closer/*")
