"""
EMPIRE V49 · PRODUCT: LEADSCORE AI
====================================
Standalone lead enrichment & scoring engine. Wraps the existing SI-powered
lead enricher agent into a productized API service with tier-based rate
limits, usage metering, and a dashboard snapshot endpoint.

Tiers:
  LEADSCORE_STARTER    — $299/mo, 500 scored leads/mo, basic enrichment
  LEADSCORE_GROWTH     — $599/mo, 2,000 scored leads/mo, custom thresholds
  LEADSCORE_ENTERPRISE — $999/mo, 10,000 scored leads/mo, custom SI models

Integration:
    scorer = LeadScoreAI(guard, log_usage)
    result = await scorer.score_lead(account_id, lead_data)
    report = await scorer.score_batch(account_id, [lead_data, ...])
"""

import asyncio
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Any

log = logging.getLogger("empire.product.lead_score")

# ── DEFAULT SCORING CONFIG ─────────────────────────────────────────────
# Import scoring primitives from the SI core to avoid duplication
from empire_si_core import beta_posterior

# Import the enricher's feature engineering function to wrap, not reimplement
try:
    from agents.lead_enricher.enricher import _engineer_features as _enricher_features
except ImportError:
    # Fallback: inline feature engineering if enricher module not importable
    _enricher_features = None
    _FEATURE_WEIGHTS = [0.40, 0.15, 0.25, 0.20]  # urgency, completeness, asset, contact
    _REQUIRED_FIELDS = ["address", "city", "state", "warehouse_name"]
    _FEATURE_COUNT = 4

# Tier limits (scored leads per month)
_TIER_LIMITS = {
    "LEADSCORE_STARTER": 500,
    "LEADSCORE_GROWTH": 2000,
    "LEADSCORE_ENTERPRISE": 10000,
}


class LeadScoreAI:
    """
    Lead enrichment & scoring engine.

    Scores leads using Bayesian probability calibrated by the SI core,
    with feature engineering across urgency, completeness, asset value,
    and contact readiness.

    Integration with Suite Gateway:
      - guard(account_id, "lead_score") -> {"ok": bool, "tier": str, ...}
      - log_usage(account_id, "lead_score", "scored_lead", quantity=1)
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,      # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,   # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {
            "scored": 0,
            "blocked": 0,
            "errors": 0,
            "batch_jobs": 0,
        }
        # In-memory results (production would persist to Supabase enriched_leads)
        self._results: Dict[str, List[Dict]] = {}
        # Outcome history for Bayesian prior (loaded from DB on first use)
        self._outcome_history: Dict[str, Any] = {"wins": 0, "losses": 0}
        self._outcome_loaded = False

    # ── ENTITLEMENT ──────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has LeadScore access."""
        if not self.guard:
            return {"ok": True, "tier": "LEADSCORE_STARTER"}
        return self.guard(account_id, "lead_score")

    def _get_tier_limit(self, tier: str) -> int:
        return _TIER_LIMITS.get(tier, 500)

    # ── OUTCOME HISTORY ──────────────────────────────────────────────

    def _load_outcome_history(self):
        """Load historical win/loss data from Supabase for Bayesian prior.
        In production this reads from enriched_leads table."""
        if self._outcome_loaded:
            return
        try:
            from supabase import create_client
            import os
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            if url and key:
                sb = create_client(url, key)
                r = sb.table("enriched_leads") \
                    .select("status") \
                    .in_("status", ["pending_outreach", "blocked", "contacted", "converted", "lost"]) \
                    .limit(5000).execute()
                rows = r.data or []
                wins = sum(1 for row in rows if row.get("status") in ("contacted", "converted"))
                losses = sum(1 for row in rows if row.get("status") in ("blocked", "lost"))
                self._outcome_history = {"wins": wins, "losses": losses}
                log.info(f"[lead_score] loaded outcome history: {wins} wins, {losses} losses ({len(rows)} total)")
        except Exception as e:
            log.debug(f"[lead_score] outcome history load skipped: {e}")
        self._outcome_loaded = True

    # ── SCORING ENGINE ───────────────────────────────────────────────
    # Wraps the SI core's beta_posterior and the enricher's feature
    # engineering. Falls back to inline logic if those aren't importable.

    @staticmethod
    def _age_days(created_at_iso: Optional[str]) -> float:
        """Days since the lead was created."""
        if not created_at_iso:
            return 9999.0
        try:
            if isinstance(created_at_iso, str):
                dt = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
            else:
                dt = created_at_iso
            return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
        except Exception:
            return 9999.0

    def _engineer_features(self, lead: dict) -> tuple:
        """
        Engineer features from a lead dict.
        Delegates to the enricher agent's _engineer_features when available,
        falls back to inline logic.
        Returns (feature_vector, trace).
        """
        if _enricher_features is not None:
            try:
                return _enricher_features(lead)
            except Exception:
                pass
        # Fallback inline feature engineering
        trace = {}
        age = self._age_days(lead.get("created_at"))
        urgency = max(0.05, min(0.95, 1.0 - 1.0 / (1.0 + math.exp(-(age - 7.0)))))
        have = sum(1 for f in _REQUIRED_FIELDS if lead.get(f))
        completeness = have / len(_REQUIRED_FIELDS)
        wh = (lead.get("warehouse_name") or "").lower()
        contact = 1.0 if (lead.get("phone") or lead.get("email")) else 0.0
        asset_score = 0.33 if wh else 0.0
        return [urgency, completeness, asset_score, contact], trace

    def _features_to_probability(self, features: List[float]) -> dict:
        """
        Convert feature vector to calibrated probability using SI core's
        Bayesian beta posterior with historical outcome prior.
        """
        feature_score = sum(f * w for f, w in zip(features, _FEATURE_WEIGHTS))
        feature_score = max(0.05, min(0.95, feature_score))

        prior = beta_posterior(
            self._outcome_history.get("wins", 0),
            self._outcome_history.get("losses", 0),
        )
        prior_mean = prior["mean"] if prior["mean"] > 0 else 0.5

        pseudo_n = 5.0
        pseudo_wins = feature_score * pseudo_n
        total_alpha = prior["alpha"] + pseudo_wins
        total_beta = prior["beta"] + (pseudo_n - pseudo_wins)
        posterior_mean = total_alpha / (total_alpha + total_beta) if (total_alpha + total_beta) > 0 else 0.5
        calibrated = max(0.01, min(0.99, posterior_mean))

        return {
            "feature_score": round(feature_score, 4),
            "prior_mean": round(prior_mean, 4),
            "posterior_mean": round(calibrated, 4),
            "prior_alpha": round(prior["alpha"], 2),
            "prior_beta": round(prior["beta"], 2),
        }

    def _score_lead_data(self, lead: dict, threshold: float = 0.35) -> dict:
        """
        Score a single lead dict. Returns full scoring result with
        features, probability, and recommendation.
        """
        self._load_outcome_history()

        features, trace = self._engineer_features(lead)
        prob = self._features_to_probability(features)
        above = prob["posterior_mean"] >= threshold

        return {
            "lead_id": lead.get("id") or lead.get("lead_id", ""),
            "features": [round(f, 3) for f in features],
            "feature_trace": trace,
            "probability": prob,
            "score": prob["posterior_mean"],
            "threshold": threshold,
            "above_threshold": above,
            "recommendation": "engage" if above else "block",
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── PUBLIC API ──────────────────────────────────────────────────

    async def score_lead(self, account_id: str, lead_data: dict,
                         threshold: Optional[float] = None) -> dict:
        """
        Score a single lead. Returns scoring result with calibrated
        probability and engagement recommendation.

        Entitlement-gated by tier. Metered as one scored lead.
        Tier limit enforced: rejects if account exceeds monthly cap.
        """
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        if not lead_data or not isinstance(lead_data, dict):
            return {"ok": False, "error": "Invalid lead data"}

        tier = entitlement.get("tier", "LEADSCORE_STARTER")
        limit = self._get_tier_limit(tier)

        # Check tier limit: count scored leads for this account
        account_count = len(self._results.get(account_id, []))
        if account_count >= limit:
            self.stats["blocked"] += 1
            return {
                "ok": False,
                "error": f"Monthly tier limit reached ({account_count}/{limit})",
                "account_id": account_id,
                "tier": tier,
                "limit": limit,
                "used": account_count,
            }

        # Score the lead
        result = self._score_lead_data(
            lead_data,
            threshold=threshold or 0.35,
        )
        result["ok"] = True
        result["account_id"] = account_id
        result["tier"] = tier
        result["limit_used"] = account_count + 1
        result["limit_max"] = limit

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "lead_score", "scored_lead",
                               quantity=1, metadata={
                                   "lead_id": result["lead_id"],
                                   "score": result["score"],
                               })
            except Exception:
                pass

        self.stats["scored"] += 1
        self._results.setdefault(account_id, []).append(result)

        return result

    async def score_batch(self, account_id: str, leads: List[dict],
                          threshold: Optional[float] = None) -> dict:
        """
        Score a batch of leads. Returns summary with per-lead results.
        """
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        if not leads or not isinstance(leads, list):
            return {"ok": False, "error": "Invalid leads array"}

        tier = entitlement.get("tier", "LEADSCORE_STARTER")
        limit = self._get_tier_limit(tier)
        results = []
        above = 0

        for lead in leads[:limit]:
            if not isinstance(lead, dict):
                continue
            result = self._score_lead_data(
                lead,
                threshold=threshold or 0.35,
            )
            result["ok"] = True
            result["account_id"] = account_id
            result["tier"] = tier
            results.append(result)
            if result["above_threshold"]:
                above += 1

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "lead_score", "scored_lead",
                               quantity=len(results))
            except Exception:
                pass

        self.stats["scored"] += len(results)
        self.stats["batch_jobs"] += 1
        self._results.setdefault(account_id, []).extend(results)

        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "batch_size": len(results),
            "above_threshold": above,
            "below_threshold": len(results) - above,
            "threshold_used": threshold or 0.35,
            "results": results,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    async def health_check(self) -> dict:
        """Return LeadScore AI health status and stats."""
        return {
            "status": "operational",
            "service": "lead_score",
            "stats": dict(self.stats),
            "historical_outcomes_loaded": self._outcome_loaded,
            "accounts_with_data": len(self._results),
        }

    def snapshot(self) -> dict:
        """Return full snapshot for SPA dashboard."""
        total_above = sum(
            1 for a_list in self._results.values()
            for r in a_list if r.get("above_threshold")
        )
        total_scored = sum(len(a_list) for a_list in self._results.values())
        avg_score = (
            round(
                sum(r.get("score", 0) for a_list in self._results.values() for r in a_list)
                / max(total_scored, 1), 3
            )
            if total_scored > 0 else 0
        )
        return {
            "stats": {
                "total_scored": self.stats["scored"],
                "total_blocked": self.stats["blocked"],
                "total_errors": self.stats["errors"],
                "batch_jobs": self.stats["batch_jobs"],
                "above_threshold": total_above,
                "avg_score": avg_score,
                "accounts_active": len(self._results),
            },
            "outcome_history": self._outcome_history,
            "tier_limits": _TIER_LIMITS,
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────

class LeadScoreRoutes:
    """Wire LeadScoreAI endpoints into the FastAPI app."""

    def __init__(self, scorer: LeadScoreAI, require_auth: Optional[Callable] = None):
        self.scorer = scorer
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request, Query
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/lead-score/score")
        async def score_single(request: Request,
                               auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Score a single lead.
            Body: {account_id, lead: {...}, threshold? (optional, default 0.35)}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            lead_data = body.get("lead") or body.get("lead_data", {})
            threshold = body.get("threshold")

            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(lead_data, dict) or not lead_data.get("warehouse_name"):
                raise HTTPException(400, "lead must have at least warehouse_name")

            result = await self.scorer.score_lead(account_id, lead_data, threshold=threshold)
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (
                200 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/suite/lead-score/score-batch")
        async def score_batch(request: Request,
                              auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Score a batch of leads.
            Body: {account_id, leads: [{...}, ...], threshold?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            leads = body.get("leads") or body.get("lead_data", [])
            threshold = body.get("threshold")

            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(leads, list) or len(leads) == 0:
                raise HTTPException(400, "leads must be a non-empty array")

            result = await self.scorer.score_batch(account_id, leads, threshold=threshold)
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (
                200 if result.get("ok") else 400
            )
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/lead-score/health")
        async def leadscore_health(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """LeadScore AI health check."""
            return JSONResponse(await self.scorer.health_check())

        @app.get("/api/v6/suite/lead-score/stats")
        async def leadscore_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """LeadScore AI stats snapshot."""
            return JSONResponse(self.scorer.snapshot())

        log.info("[lead-score] Routes registered · /api/v6/suite/lead-score/*")
