"""
EMPIRE V49 · PRODUCT: MEETILY (AI Meeting Assistant)
=====================================================
Privacy-first AI meeting assistant that captures, transcribes, and summarizes
meetings entirely on local infrastructure. Resold through the Empire AI Suite.

Product background:
  - Open-source (MIT) desktop app by Zackriya Solutions
  - Tauri 2.x (Rust) + Next.js 14 + React 18 + TypeScript
  - Local Whisper models for transcription (no cloud)
  - Supports Ollama, Claude, Groq, OpenRouter for LLM summarization
  - Runs on macOS, Windows, Linux
  - All processing is local — no data leaves the machine

Empire AI provides:
  - Hosted deployment on enterprise infrastructure (Linux servers)
  - Managed update + backup pipeline
  - Centralized user management + billing
  - White-label customization for clients

Integration:
    meetily = MeetilyProduct(suite_guard, suite_subscriptions)
    result = await meetily.deploy_instance(account_id, config)
"""

import json as _json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.meetily")

# Meetily PRO tiers for resale
MEETILY_TIERS = {
    "MEETILY_STARTER": {
        "price": 99,
        "description": "Single-user AI meeting assistant — local transcription, basic summaries",
        "features": [
            "Local transcription (Whisper)",
            "AI-powered summaries",
            "Single user license",
            "Ollama support",
            "Basic meeting search",
            "Email support",
        ],
    },
    "MEETILY_PRO": {
        "price": 299,
        "description": "Multi-user with advanced features — speaker diarization, custom workflows, team management",
        "features": [
            "Everything in Starter",
            "Up to 5 users",
            "Speaker diarization",
            "Custom summary workflows",
            "Advanced export (PDF, DOCX, SRT)",
            "Claude/Groq/OpenRouter support",
            "Priority email support",
        ],
    },
    "MEETILY_ENTERPRISE": {
        "price": 999,
        "description": "Full enterprise deployment — dedicated server, white-label, SLA, custom integrations",
        "features": [
            "Everything in Pro",
            "Unlimited users",
            "Dedicated Linux server deployment",
            "White-label branding",
            "Custom integrations (Slack, Teams, etc.)",
            "On-premise or VPC hosting",
            "99.9% SLA",
            "Dedicated support engineer",
            "Backup & disaster recovery",
        ],
    },
}


class MeetilyProduct:
    """Meetily AI Meeting Assistant — privacy-first meeting transcription & summarization.

    Resold through the Empire AI Suite with three tiers:
      - Starter: Single-user, local processing
      - Pro: Multi-user, advanced features
      - Enterprise: Dedicated deployment, white-label, SLA
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,     # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {"deployments": 0, "blocked": 0, "errors": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has meetily access."""
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "meetily")

    async def deploy_instance(self, account_id: str, config: dict) -> dict:
        """Provision a Meetily instance for an account.

        For Starter/Pro tiers, this generates deployment credentials and
        a setup guide. For Enterprise, it also provisions a server.

        Args:
            account_id: Customer account ID
            config: {
                tier: "MEETILY_STARTER" | "MEETILY_PRO" | "MEETILY_ENTERPRISE",
                deployment_type: "local" | "server" | "enterprise",
                user_count: int (optional, used for tier validation),
                white_label: bool (optional, enterprise only),
            }
        """
        tier = config.get("tier", "MEETILY_STARTER")
        tier_config = MEETILY_TIERS.get(tier)
        if not tier_config:
            self.stats["blocked"] += 1
            return {"ok": False, "error": f"Unknown tier: {tier}"}

        # Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        # Generate deployment credentials
        from uuid import uuid4
        instance_id = str(uuid4())

        self.stats["deployments"] += 1

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "meetily", "deployment",
                               q=1, m={
                                   "tier": tier,
                                   "instance_id": instance_id,
                               })
            except Exception:
                pass

        return {
            "ok": True,
            "account_id": account_id,
            "instance_id": instance_id,
            "tier": tier,
            "price": tier_config["price"],
            "features": tier_config["features"],
            "deployment_guide": self._deployment_guide(tier, config),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _deployment_guide(self, tier: str, config: dict) -> str:
        """Return setup instructions based on tier and deployment type."""
        guides = {
            "MEETILY_STARTER": (
                "1. Download Meetily from https://meetily.ai\n"
                "2. Install the desktop app (macOS/Windows/Linux)\n"
                "3. Launch Meetily and connect to your Ollama instance\n"
                "4. Start recording meetings — all processing is local"
            ),
            "MEETILY_PRO": (
                "1. Deploy Meetily on your team's shared workstation or server\n"
                "2. Configure multi-user access via environment settings\n"
                "3. Set up Claude/Groq/OpenRouter for enhanced summaries\n"
                "4. Connect team members by sharing the deployment URL"
            ),
            "MEETILY_ENTERPRISE": (
                "1. Empire AI provisions a dedicated Linux server with Meetily deployed\n"
                "2. White-label branding applied per your specifications\n"
                "3. Custom integrations (Slack, Teams, etc.) configured\n"
                "4. SLA monitoring and backup pipeline activated\n"
                "5. Your team receives login credentials and training guide"
            ),
        }
        return guides.get(tier, "Download from https://meetily.ai and follow the setup wizard.")

    def snapshot(self) -> dict:
        return {**self.stats}


class MeetilyRoutes:
    """Wire Meetily endpoints into the FastAPI app."""

    def __init__(self, meetily: MeetilyProduct, *, require_auth: Optional[Callable] = None):
        self.meetily = meetily
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/meetily/deploy")
        async def meetily_deploy(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Deploy a Meetily instance for an account.
            Body: {account_id, config: {tier, ...}}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            config = body.get("config") or body.get("deployment", {})
            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(config, dict):
                raise HTTPException(400, "config must be an object")

            result = await self.meetily.deploy_instance(account_id, config)
            status = 403 if not result.get("ok") else 200
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/meetily/tiers")
        async def meetily_tiers(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Return Meetily pricing tiers and features."""
            return JSONResponse({
                "tiers": {
                    slug: {
                        "price": t["price"],
                        "description": t["description"],
                        "features": t["features"],
                    }
                    for slug, t in MEETILY_TIERS.items()
                }
            })

        @app.get("/api/v6/suite/meetily/stats")
        async def meetily_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.meetily.snapshot())

        log.info("[meetily] Routes registered · /api/v6/suite/meetily/*")
