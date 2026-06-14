"""
EMPIRE V49 · PRODUCT: STRIKE CAMPAIGNS
=======================================
Multi-touch SMS & email campaign builder. Wraps the existing SMSSequenceEngine
and EmailSequenceEngine into a productized campaign builder with tier-based
rate limits, campaign CRUD, bulk enrollment, and analytics aggregation.

Tiers:
  STRIKE_STARTER     — $99/mo, 500 campaign runs/mo, basic SMS + email
  STRIKE_GROWTH      — $249/mo, 2,000 runs/mo, multi-channel + analytics
  STRIKE_ENTERPRISE  — $499/mo, 10,000 runs/mo, A/B testing + custom templates

Integration:
    engine = StrikeCampaigns(guard, log_usage, sms_engine, email_engine)
    result = await engine.create_campaign(account_id, campaign_data)
    report = await engine.run_campaign(account_id, campaign_id, leads)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Any

log = logging.getLogger("empire.product.strike_campaigns")

# Tier limits (campaign runs per month = enrollments + sequences triggered)
_TIER_LIMITS = {
    "STRIKE_STARTER": 500,
    "STRIKE_GROWTH": 2000,
    "STRIKE_ENTERPRISE": 10000,
}

# Default campaign types (maps to existing sequence_type in sms_sequences)
_DEFAULT_CAMPAIGN_TYPES = {
    "storm_strike": {
        "name": "Storm Strike",
        "description": "5-touch SMS + 4-touch email for storm-affected properties",
        "channels": ["sms", "email"],
        "template_set": "storm_strike",
    },
    "nurture": {
        "name": "Nurture",
        "description": "3-touch SMS follow-up for warm leads",
        "channels": ["sms"],
        "template_set": "nurture",
    },
    "recall": {
        "name": "Recall Sniper",
        "description": "5-touch legal recall sequence",
        "channels": ["sms", "email"],
        "template_set": "recall",
    },
}


class StrikeCampaigns:
    """
    Multi-touch SMS & email campaign builder.

    Wraps the existing empire_sms.SMSSequenceEngine and
    empire_email.EmailSequenceEngine into a productized campaign
    builder with tier-based rate limits, usage metering, and
    aggregated campaign analytics.

    Integration with Suite Gateway:
      - guard(account_id, "strike_campaigns") -> {"ok": bool, "tier": str, ...}
      - log_usage(account_id, "strike_campaigns", "campaign_run", quantity=1)
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,       # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,    # SuiteGuard.log_usage
        sms_engine: Optional[Any] = None,        # empire_sms.SMSSequenceEngine
        email_engine: Optional[Any] = None,      # empire_email.EmailSequenceEngine
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.sms_engine = sms_engine
        self.email_engine = email_engine

        # In-memory campaign definitions (production would persist to a DB)
        self._campaigns: Dict[str, Dict] = {}
        self._runs: Dict[str, List[Dict]] = {}  # campaign_id -> [run records]

        self.stats = {
            "campaigns_created": 0,
            "campaign_runs": 0,
            "sms_enrolled": 0,
            "email_enrolled": 0,
            "blocked": 0,
            "errors": 0,
        }

    # ── ENTITLEMENT ──────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has Strike Campaigns access."""
        if not self.guard:
            return {"ok": True, "tier": "STRIKE_STARTER"}
        return self.guard(account_id, "strike_campaigns")

    def _get_tier_limit(self, tier: str) -> int:
        return _TIER_LIMITS.get(tier, 500)

    # ── CAMPAIGN CRUD ───────────────────────────────────────────────

    async def create_campaign(
        self,
        account_id: str,
        campaign_data: dict,
    ) -> dict:
        """Create a new campaign definition.
        Body: {
          name: str (required),
          campaign_type: str ("storm_strike", "nurture", "recall", or "custom"),
          channels?: [str] (defaults to campaign type's channels),
          template_set?: str (defaults to campaign type),
          meta?: dict,
        }
        """
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        name = (campaign_data.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "Campaign name required"}

        campaign_type = campaign_data.get("campaign_type", "storm_strike")
        type_config = _DEFAULT_CAMPAIGN_TYPES.get(campaign_type, {})

        campaign_id = f"camp_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        campaign = {
            "campaign_id": campaign_id,
            "account_id": account_id,
            "name": name,
            "campaign_type": campaign_type,
            "channels": campaign_data.get("channels") or type_config.get("channels", ["sms"]),
            "template_set": campaign_data.get("template_set") or type_config.get("template_set", campaign_type),
            "description": type_config.get("description", ""),
            "tier": entitlement.get("tier", "STRIKE_STARTER"),
            "runs": 0,
            "total_enrolled": 0,
            "created_at": now,
            "updated_at": now,
            "meta": campaign_data.get("meta", {}),
        }

        self._campaigns[campaign_id] = campaign
        self.stats["campaigns_created"] += 1

        return {"ok": True, "campaign": campaign}

    def get_campaign(self, campaign_id: str) -> Optional[dict]:
        """Return a single campaign definition."""
        return self._campaigns.get(campaign_id)

    def list_campaigns(self, account_id: str) -> list:
        """Return all campaigns for an account."""
        return [
            c for c in self._campaigns.values()
            if c.get("account_id") == account_id
        ]

    def delete_campaign(self, campaign_id: str) -> dict:
        """Remove a campaign definition."""
        if campaign_id not in self._campaigns:
            return {"ok": False, "error": "Campaign not found"}
        del self._campaigns[campaign_id]
        self._runs.pop(campaign_id, None)
        return {"ok": True}

    # ── CAMPAIGN RUN ────────────────────────────────────────────────

    async def run_campaign(
        self,
        account_id: str,
        campaign_id: str,
        leads: List[dict],
    ) -> dict:
        """
        Execute a campaign against a batch of leads.

        Each lead in the list should be:
          {"phone": str, "email"?: str, "target_addr"?: str, "meta"?: dict}

        Enrolls each lead into the appropriate sequences based on
        the campaign's channel configuration. One campaign "run" =
        enrolling one lead into all its campaign channels.

        Returns summary with per-lead results.
        """
        # 1. Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "STRIKE_STARTER")
        limit = self._get_tier_limit(tier)

        # 2. Validate campaign exists
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"ok": False, "error": "Campaign not found"}

        if campaign.get("account_id") != account_id:
            self.stats["blocked"] += 1
            return {"ok": False, "error": "Campaign not owned by this account"}

        if not leads or not isinstance(leads, list):
            return {"ok": False, "error": "Invalid leads array"}

        # 3. Check tier limit
        total_runs = campaign.get("runs", 0)
        if total_runs >= limit:
            self.stats["blocked"] += 1
            return {
                "ok": False,
                "error": f"Monthly tier limit reached ({total_runs}/{limit})",
                "tier": tier,
                "limit": limit,
                "used": total_runs,
            }

        # 4. Cap batch to available runs
        available = limit - total_runs
        batch = leads[:available]

        channels = campaign.get("channels", ["sms"])
        template_set = campaign.get("template_set", "storm_strike")
        results = []
        sms_count = 0
        email_count = 0

        for lead in batch:
            if not isinstance(lead, dict):
                continue

            lead_result = {"phone": lead.get("phone", ""), "email": lead.get("email", "")}
            lead_ok = True

            # Enroll in SMS sequence
            if "sms" in channels and lead.get("phone"):
                if self.sms_engine:
                    try:
                        sms_result = await self.sms_engine.enroll(
                            phone=lead["phone"],
                            target_addr=lead.get("target_addr", ""),
                            sequence_type=template_set,
                            meta=lead.get("meta", {}),
                        )
                        lead_result["sms"] = sms_result
                        if sms_result.get("ok"):
                            sms_count += 1
                    except Exception as e:
                        lead_result["sms_error"] = str(e)[:100]
                        lead_ok = False
                else:
                    lead_result["sms"] = {"ok": True, "note": "sms engine not available; stub enrollment"}

            # Enroll in email sequence
            if "email" in channels and lead.get("email"):
                if self.email_engine:
                    try:
                        email_result = await self.email_engine.enroll(
                            email=lead["email"],
                            target_addr=lead.get("target_addr", ""),
                            sequence_type=template_set,
                            meta=lead.get("meta", {}),
                        )
                        lead_result["email"] = email_result
                        if email_result.get("ok"):
                            email_count += 1
                    except Exception as e:
                        lead_result["email_error"] = str(e)[:100]
                        lead_ok = False
                else:
                    lead_result["email"] = {"ok": True, "note": "email engine not available; stub enrollment"}

            lead_result["ok"] = lead_ok
            results.append(lead_result)

        # 5. Update campaign state
        runs_used = len(batch)
        campaign["runs"] = total_runs + runs_used
        campaign["total_enrolled"] = campaign.get("total_enrolled", 0) + runs_used
        campaign["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._campaigns[campaign_id] = campaign

        self.stats["campaign_runs"] += runs_used
        self.stats["sms_enrolled"] += sms_count
        self.stats["email_enrolled"] += email_count

        # 6. Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "strike_campaigns", "campaign_run",
                               quantity=runs_used, metadata={
                                   "campaign_id": campaign_id,
                                   "campaign_name": campaign.get("name", ""),
                                   "sms": sms_count,
                                   "email": email_count,
                               })
            except Exception:
                pass

        # Record the run
        run_record = {
            "campaign_id": campaign_id,
            "account_id": account_id,
            "run_id": uuid.uuid4().hex[:12],
            "batch_size": runs_used,
            "sms_enrolled": sms_count,
            "email_enrolled": email_count,
            "run_at": datetime.now(timezone.utc).isoformat(),
        }
        self._runs.setdefault(campaign_id, []).append(run_record)

        return {
            "ok": True,
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("name", ""),
            "tier": tier,
            "batch_size": runs_used,
            "sms_enrolled": sms_count,
            "email_enrolled": email_count,
            "limit_used": total_runs + runs_used,
            "limit_max": limit,
            "results": results,
            "run_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── ANALYTICS ───────────────────────────────────────────────────

    async def campaign_stats(self, account_id: str, campaign_id: str,
                             get_db: Optional[Callable] = None) -> dict:
        """
        Return analytics for a specific campaign.

        If get_db is provided, queries Supabase sms_sequences and
        email_sequences for live stats. Otherwise returns in-memory
        campaign state only.
        """
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"ok": False, "error": "Campaign not found"}

        campaign_data = dict(campaign)
        run_history = self._runs.get(campaign_id, [])

        # If DB available, get live sequence stats
        live_stats = {}
        if get_db:
            try:
                db = get_db()

                # Total SMS sequences for this campaign
                sms_total = 0
                sms_active = 0
                sms_replied = 0
                sms_opted_out = 0
                try:
                    r = db.table("sms_sequences").select("status") \
                        .eq("meta->>campaign_id", campaign_id) \
                        .execute()
                    for s in (r.data or []):
                        sms_total += 1
                        st = s.get("status", "")
                        if st == "active":
                            sms_active += 1
                        elif st == "replied":
                            sms_replied += 1
                        elif st == "opted_out":
                            sms_opted_out += 1
                except Exception:
                    pass

                # Total email sequences for this campaign
                email_total = 0
                email_active = 0
                email_replied = 0
                email_unsub = 0
                try:
                    r = db.table("email_sequences").select("status") \
                        .eq("meta->>campaign_id", campaign_id) \
                        .execute()
                    for s in (r.data or []):
                        email_total += 1
                        st = s.get("status", "")
                        if st == "active":
                            email_active += 1
                        elif st == "replied":
                            email_replied += 1
                        elif st == "unsubscribed":
                            email_unsub += 1
                except Exception:
                    pass

                live_stats = {
                    "sms_sequences": {
                        "total": sms_total,
                        "active": sms_active,
                        "replied": sms_replied,
                        "opted_out": sms_opted_out,
                    },
                    "email_sequences": {
                        "total": email_total,
                        "active": email_active,
                        "replied": email_replied,
                        "unsubscribed": email_unsub,
                    },
                }
            except Exception:
                live_stats = {}

        return {
            "ok": True,
            "campaign": campaign_data,
            "runs": run_history,
            "total_runs": len(run_history),
            "live_stats": live_stats,
        }

    async def snapshot(self, account_id: str,
                       get_db: Optional[Callable] = None) -> dict:
        """Return full Strike Campaigns snapshot for the dashboard."""
        campaigns = self.list_campaigns(account_id)
        total_runs = sum(c.get("runs", 0) for c in campaigns)

        db_stats = {}
        if get_db:
            try:
                db = get_db()
                # Aggregate across all campaigns
                sms_total = 0
                try:
                    r = db.table("sms_sequences").select("id", count="exact").execute()
                    sms_total = getattr(r, "count", 0) or 0
                except Exception:
                    pass
                email_total = 0
                try:
                    r = db.table("email_sequences").select("id", count="exact").execute()
                    email_total = getattr(r, "count", 0) or 0
                except Exception:
                    pass
                db_stats = {
                    "total_sms_sequences": sms_total,
                    "total_email_sequences": email_total,
                }
            except Exception:
                pass

        return {
            "campaigns": campaigns,
            "campaign_count": len(campaigns),
            "total_runs": total_runs,
            "total_sms_enrolled": self.stats["sms_enrolled"],
            "total_email_enrolled": self.stats["email_enrolled"],
            "db_stats": db_stats,
            "tier_limits": _TIER_LIMITS,
            "available_types": {k: v["name"] for k, v in _DEFAULT_CAMPAIGN_TYPES.items()},
        }

    async def health_check(self) -> dict:
        """Return Strike Campaigns health status."""
        sms_ok = self.sms_engine is not None
        email_ok = self.email_engine is not None
        return {
            "status": "operational" if (sms_ok or email_ok) else "degraded",
            "service": "strike_campaigns",
            "engines": {
                "sms": "connected" if sms_ok else "unavailable",
                "email": "connected" if email_ok else "unavailable",
            },
            "stats": dict(self.stats),
            "campaign_count": len(self._campaigns),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────

class StrikeCampaignsRoutes:
    """Wire Strike Campaigns endpoints into the FastAPI app."""

    def __init__(self, engine: StrikeCampaigns, require_auth: Optional[Callable] = None,
                 get_db: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth
        self.get_db = get_db

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/strike-campaigns/create")
        async def create_campaign(
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Create a new campaign definition.
            Body: {
              account_id: str (required),
              name: str (required),
              campaign_type?: str ("storm_strike"|"nurture"|"recall"|"custom"),
              channels?: [str],
              template_set?: str,
              meta?: dict,
            }
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            if not account_id:
                raise HTTPException(400, "account_id required")

            result = await self.engine.create_campaign(account_id, body)
            status = 200 if result.get("ok") else 400
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/strike-campaigns/list")
        async def list_campaigns(
            account_id: str = "",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """List campaigns. ?account_id filters to one account."""
            if not account_id:
                raise HTTPException(400, "account_id required")
            campaigns = self.engine.list_campaigns(account_id)
            return JSONResponse({"campaigns": campaigns, "count": len(campaigns)})

        @app.get("/api/v6/suite/strike-campaigns/{campaign_id}")
        async def get_campaign(
            campaign_id: str,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Get a single campaign with stats."""
            result = await self.engine.campaign_stats(
                "", campaign_id,
                get_db=self.get_db,
            )
            status = 200 if result.get("ok") else 404
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/suite/strike-campaigns/{campaign_id}/run")
        async def run_campaign(
            campaign_id: str,
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Execute a campaign against a batch of leads.
            Body: {
              account_id: str (required),
              leads: [{phone?, email?, target_addr?, meta?}]
            }
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            leads = body.get("leads", [])

            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(leads, list) or len(leads) == 0:
                raise HTTPException(400, "leads must be a non-empty array")

            result = await self.engine.run_campaign(account_id, campaign_id, leads)
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (
                200 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.delete("/api/v6/suite/strike-campaigns/{campaign_id}")
        async def delete_campaign(
            campaign_id: str,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Delete a campaign definition."""
            result = self.engine.delete_campaign(campaign_id)
            status = 200 if result.get("ok") else 404
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/strike-campaigns/stats")
        async def campaigns_stats(
            account_id: str = "",
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Strike Campaigns stats snapshot."""
            if not account_id:
                raise HTTPException(400, "account_id required")
            return JSONResponse(await self.engine.snapshot(
                account_id, get_db=self.get_db,
            ))

        @app.get("/api/v6/suite/strike-campaigns/health")
        async def campaigns_health(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Strike Campaigns health check."""
            return JSONResponse(await self.engine.health_check())

        @app.get("/api/v6/suite/strike-campaigns/types")
        async def campaigns_types(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """List available campaign types and their configurations."""
            return JSONResponse({
                "types": {
                    k: {
                        "name": v["name"],
                        "description": v["description"],
                        "channels": v["channels"],
                    }
                    for k, v in _DEFAULT_CAMPAIGN_TYPES.items()
                }
            })

        log.info("[strike-campaigns] Routes registered · /api/v6/suite/strike-campaigns/*")
