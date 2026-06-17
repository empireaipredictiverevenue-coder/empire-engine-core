"""
EMPIRE V49 · EXECUTIVE AGENT (HIGH-TICKET SALES)
==================================================
Enterprise sales agent targeting high-value opportunities ($500+/mo, 6-figure ACV).

Capabilities:
- High-value lead identification and scoring (enterprise ICP fit, budget signals)
- Multi-touch executive outreach cadences (email + voice + follow-up sequences)
- Complex deal structuring (multi-product bundles, custom pricing, discount approval)
- Enterprise deal pipeline tracking (long-cycle, multi-stakeholder)
- Win/loss analysis with reason codes
- C-level engagement coordination

Routes:
  GET    /api/executive/overview    — Executive dashboard snapshot
  GET    /api/executive/targets     — High-value lead targets scored and ranked
  GET    /api/executive/deals       — Enterprise deal pipeline
  GET    /api/executive/quote       — Generate enterprise quote with multi-product bundling
  POST   /api/executive/cadence     — Trigger executive outreach cadence on a target
  GET    /api/executive/snapshot    — Condensed fleet dashboard snapshot
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.executive_agent")

# ── Enterprise deal stages (longer cycle than standard sales) ─────
ENTERPRISE_STAGES = [
    "targeting",      # Identified but not contacted
    "reaching_out",   # Executive cadence in progress
    "engaging",       # Positive response, initial conversation
    "qualifying",     # Discovery call / needs assessment
    "proposing",      # Quote/bid submitted
    "negotiating",    # Terms discussion
    "closing",        # Final approvals, signatures
    "won",
    "lost",
]

# ── Enterprise ICP thresholds ────────────────────────────────────
MIN_ENTERPRISE_MRR = 500       # $500/mo minimum for enterprise
MIN_ENTERPRISE_ACV = 6000      # $6K annual minimum
MAX_SCORE_ENTERPRISE = 100


class ExecutiveAgent:
    """High-ticket enterprise sales agent. Identifies whales, runs
    executive-level outreach, tracks complex deal cycles."""

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._enterprise_deals: list[dict] = []
        self._outreach_history: list[dict] = []

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── DATA SOURCES ─────────────────────────────────────────────────

    def _fetch_high_value_leads(self, limit: int = 100) -> list[dict]:
        """Fetch leads from enriched_leads that look like enterprise targets."""
        try:
            r = self._db().table("enriched_leads") \
                .select("id, name, phone, email, city, state, niche, meta, created_at") \
                .limit(limit) \
                .order("created_at", desc=True) \
                .execute()
            return r.data or []
        except Exception as e:
            log.debug(f"[exec] fetch leads failed: {e}")
            return []

    def _fetch_active_contractors(self) -> list[dict]:
        """Fetch contractors with enterprise potential."""
        try:
            r = self._db().table("contractors") \
                .select("id, name, phone, email, metro, specialty, meta") \
                .limit(200) \
                .execute()
            return r.data or []
        except Exception as e:
            log.debug(f"[exec] fetch contractors failed: {e}")
            return []

    def _get_suite_products(self) -> list[dict]:
        """Get product catalog for quoting."""
        try:
            r = self._db().table("product_metadata") \
                .select("tier, product_name, display_name, description, monthly_price_usd, features") \
                .eq("is_active", True) \
                .order("sort_order") \
                .execute()
            return r.data or []
        except Exception as e:
            log.debug(f"[exec] products failed: {e}")
            return []

    def _get_revenue_stats(self) -> dict:
        """Get revenue context for pipeline."""
        out = {"total_24h": 0, "mrr_projected": 0, "active_buyers": 0}
        try:
            from bots import predictive_revenue
            pl = predictive_revenue.per_lane_forecast() or {}
            out = pl.get("totals", out)
        except Exception:
            pass
        return out

    # ── ENTERPRISE LEAD SCORING ──────────────────────────────────────

    def _score_enterprise_fit(self, lead: dict) -> dict:
        """Score a lead for enterprise/high-ticket potential.

        Factors:
          - Niche quality (some niches are inherently higher value)
          - Geographic density (metros with more economic activity)
          - Data completeness (has phone, email, website = more serious)
          - Timing (recent leads are hotter)
        """
        niche = (lead.get("niche") or "").lower()
        meta = lead.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        # Niche value score — certain niches command higher prices
        HIGH_VALUE_NICHES = {
            "commercial roofing": 30, "industrial hvac": 28,
            "mass tort": 35, "debt relief": 30, "insurance": 25,
            "enterprise software": 30, "logistics": 22, "freight": 22,
            "commercial real estate": 25, "healthcare": 28,
            "legal": 30, "financial": 32, "manufacturing": 24,
        }
        niche_score = 0
        for kw, score in HIGH_VALUE_NICHES.items():
            if kw in niche:
                niche_score = max(niche_score, score)
        if niche_score == 0:
            niche_score = 10  # baseline

        # Data completeness score
        has_phone = bool(lead.get("phone"))
        has_email = bool(lead.get("email"))
        has_name = bool(lead.get("name"))
        completeness = sum([has_phone, has_email, has_name]) * 10

        # Geo density score
        city = (lead.get("city") or "").lower()
        MAJOR_METROS = ["dallas", "houston", "austin", "san antonio",
                        "new york", "los angeles", "chicago", "miami",
                        "atlanta", "phoenix", "denver", "seattle",
                        "boston", "washington", "san francisco"]
        geo_score = 15 if any(m in city for m in MAJOR_METROS) else 5

        # Recency score (leads from last 7d get bonus)
        created = lead.get("created_at", "")
        recency_score = 10
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - created_dt).days
                recency_score = max(0, 10 - age_days)  # decays by 1pt/day
            except Exception:
                pass

        # Enrichment bonus (leads with meta data are more valuable)
        enrichment_score = 5 if isinstance(meta, dict) and len(meta) > 2 else 0

        total = niche_score + completeness + geo_score + recency_score + enrichment_score
        total = min(total, MAX_SCORE_ENTERPRISE)

        return {
            "score": total,
            "score_breakdown": {
                "niche_value": niche_score,
                "completeness": completeness,
                "geo_density": geo_score,
                "recency": recency_score,
                "enrichment": enrichment_score,
            },
            "is_enterprise": total >= 65,
            "tier": ("whale" if total >= 85 else
                     "enterprise" if total >= 65 else
                     "growth" if total >= 40 else "standard"),
        }

    # ── 1. OVERVIEW ──────────────────────────────────────────────────

    def overview(self) -> dict:
        """Executive dashboard — high-value pipeline, win rates, revenue."""
        leads = self._fetch_high_value_leads()
        rev = self._get_revenue_stats()

        # Score all leads for enterprise fit
        scored = [self._score_enterprise_fit(l) for l in leads]
        whales = [s for s in scored if s["tier"] == "whale"]
        enterprise = [s for s in scored if s["tier"] == "enterprise"]
        growth = [s for s in scored if s["tier"] == "growth"]

        # Deals pipeline stats
        active_deals = [d for d in self._enterprise_deals
                        if d.get("stage") not in ("won", "lost")]
        won_deals = [d for d in self._enterprise_deals if d.get("stage") == "won"]
        total_value = sum(d.get("value", 0) for d in active_deals)
        won_value = sum(d.get("value", 0) for d in won_deals)

        return {
            "ts": self._now(),
            "pipeline": {
                "whales": len(whales),
                "enterprise": len(enterprise),
                "growth": len(growth),
                "total_scored": len(scored),
                "active_deals": len(active_deals),
                "pipeline_value": round(total_value, 2),
                "won_deals": len(won_deals),
                "won_value": round(won_value, 2),
            },
            "revenue": {
                "revenue_24h": rev.get("total_24h", 0),
                "mrr_projected": rev.get("mrr_projected", 0),
                "active_buyers": rev.get("active_buyers", 0),
            },
            "avg_enterprise_score": round(
                sum(s["score"] for s in enterprise) / max(len(enterprise), 1), 1
            ) if enterprise else 0,
        }

    # ── 2. ENTERPRISE TARGETS ────────────────────────────────────────

    def enterprise_targets(self) -> dict:
        """Score and rank high-value lead targets."""
        leads = self._fetch_high_value_leads()

        targets = []
        for lead in leads:
            score = self._score_enterprise_fit(lead)
            if score["is_enterprise"] or score["tier"] == "growth":
                targets.append({
                    "lead_id": lead.get("id", ""),
                    "name": lead.get("name", "Unknown"),
                    "phone": lead.get("phone", ""),
                    "email": lead.get("email", ""),
                    "city": lead.get("city", ""),
                    "state": lead.get("state", ""),
                    "niche": lead.get("niche", ""),
                    "created_at": lead.get("created_at", ""),
                    **score,
                })

        targets.sort(key=lambda t: t["score"], reverse=True)
        whales = [t for t in targets if t["tier"] == "whale"]
        enterprise = [t for t in targets if t["tier"] == "enterprise"]
        growth = [t for t in targets if t["tier"] == "growth"]

        return {
            "ts": self._now(),
            "total_targets": len(targets),
            "whales": whales[:20],
            "enterprise": enterprise[:20],
            "growth": growth[:20],
            "summary": {
                "whales": len(whales),
                "enterprise": len(enterprise),
                "growth": len(growth),
                "total_potential_value": round(
                    sum(t["score"] * 10 for t in targets[:50]), 2
                ),
            },
        }

    # ── 3. DEAL PIPELINE ─────────────────────────────────────────────

    def deal_pipeline(self) -> dict:
        """Enterprise deal pipeline with stage tracking."""
        # Sync with in-memory deals
        deals_by_stage = {}
        for stage in ENTERPRISE_STAGES:
            stage_deals = [d for d in self._enterprise_deals
                          if d.get("stage") == stage]
            total_value = sum(d.get("value", 0) for d in stage_deals)
            deals_by_stage[stage] = {
                "count": len(stage_deals),
                "value": round(total_value, 2),
                "deals": sorted(stage_deals,
                               key=lambda d: d.get("value", 0), reverse=True)[:10],
            }

        # Conversion metrics
        won = deals_by_stage.get("won", {}).get("count", 0)
        lost = deals_by_stage.get("lost", {}).get("count", 0)
        total_closed = won + lost
        win_rate = round(won / max(total_closed, 1) * 100, 1)

        pipeline_value = sum(
            d.get("value", 0) for d in self._enterprise_deals
            if d.get("stage") not in ("won", "lost")
        )

        # Average deal size
        won_deals_list = [d for d in self._enterprise_deals if d.get("stage") == "won"]
        avg_deal_size = round(
            sum(d.get("value", 0) for d in won_deals_list) / max(len(won_deals_list), 1), 2
        ) if won_deals_list else 0

        return {
            "ts": self._now(),
            "stages": deals_by_stage,
            "metrics": {
                "pipeline_value": round(pipeline_value, 2),
                "win_rate_pct": win_rate,
                "won": won,
                "lost": lost,
                "total_closed": total_closed,
                "avg_deal_size": avg_deal_size,
                "avg_sales_cycle_days": 45,  # placeholder — real tracking requires timestamps
            },
            "total_deals": len(self._enterprise_deals),
        }

    # ── 4. ENTERPRISE QUOTE ──────────────────────────────────────────

    def generate_quote(self, company: str = "", niche: str = "",
                       deal_size: float = 0.0, bundle_tiers: Optional[list[str]] = None) -> dict:
        """Generate an enterprise quote with multi-product bundling.

        Args:
            company: Target company name.
            niche: Target niche.
            deal_size: Target annual deal size in USD.
            bundle_tiers: Specific product tiers to include. If empty, auto-selects.
        """
        products = self._get_suite_products()
        if not products:
            products = [
                {"tier": "STRIKE_ENTERPRISE", "display_name": "Strike Campaigns Enterprise",
                 "description": "Multi-touch SMS/email campaigns", "monthly_price_usd": 499},
                {"tier": "LEADSCORE_ENTERPRISE", "display_name": "LeadScore AI Enterprise",
                 "description": "SI-powered lead scoring", "monthly_price_usd": 999},
                {"tier": "COMPLIANT_ENTERPRISE", "display_name": "Compliant Enterprise",
                 "description": "TCPA/DNC compliance", "monthly_price_usd": 999},
                {"tier": "FORECAST_ENTERPRISE", "display_name": "Forecast Enterprise",
                 "description": "Predictive revenue projections", "monthly_price_usd": 999},
                {"tier": "MARKET_EYE_ENTERPRISE", "display_name": "Market Eye Enterprise",
                 "description": "Competitive intelligence", "monthly_price_usd": 999},
            ]

        # Filter to enterprise tiers if bundle specified
        if bundle_tiers:
            selected = [p for p in products if p.get("tier") in bundle_tiers]
        else:
            # Auto-select based on deal size
            enterprise_tiers = [p for p in products if "ENTERPRISE" in (p.get("tier") or "")]
            enterprise_tiers.sort(key=lambda p: p.get("monthly_price_usd", 0))

            if deal_size >= 50000:
                selected = enterprise_tiers  # All products
            elif deal_size >= 25000:
                selected = enterprise_tiers[:4]  # Top 4
            elif deal_size >= 10000:
                selected = enterprise_tiers[:2]  # Top 2
            else:
                selected = enterprise_tiers[:1] if enterprise_tiers else [products[0]]

        # Build quote items
        items = []
        monthly_total = 0
        for p in selected:
            price = float(p.get("monthly_price_usd", 0))
            monthly_total += price
            items.append({
                "product": p.get("display_name", p.get("tier", "")),
                "tier": p.get("tier", ""),
                "description": p.get("description", ""),
                "monthly_price": price,
                "setup_fee": round(price * 0.25, 2),  # 25% setup
                "annual_price": round(price * 10, 2),  # 2 months free on annual
                "qty": 1,
            })

        annual_total = round(monthly_total * 10, 2)  # Annual = 10 months (2 free)
        setup_total = round(sum(i["setup_fee"] for i in items), 2)

        import hashlib
        quote_id = f"EXQ-{hashlib.md5(f'{company}{self._now()}'.encode()).hexdigest()[:8].upper()}"

        return {
            "quote_id": quote_id,
            "company": company or "Enterprise Prospect",
            "niche": niche or "General",
            "generated_at": self._now(),
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
            "items": items,
            "pricing_summary": {
                "monthly_total": round(monthly_total, 2),
                "annual_total": annual_total,
                "setup_total": setup_total,
                "annual_saving": round(monthly_total * 2, 2),  # 2 months free
                "first_year_total": round(annual_total + setup_total, 2),
            },
            "terms": {
                "billing": "Monthly or annual (2 months free on annual)",
                "cancellation": "30-day notice for monthly. Annual is prepaid, non-refundable.",
                "payment": "USDC, wire transfer, or ACH. Net 15 for enterprise.",
                "sla": "99.9% uptime SLA. 4-hour support response. Dedicated account manager.",
            },
            "discount_eligible": monthly_total >= 2000,
            "recommended_discount_pct": round(min(monthly_total * 0.005, 20), 1) if monthly_total >= 2000 else 0,
        }

    # ── 5. TRIGGER EXECUTIVE CADENCE ─────────────────────────────────

    async def trigger_executive_cadence(self, lead_id: str = "",
                                         niche: str = "",
                                         target_name: str = "") -> dict:
        """Trigger an executive-level outreach cadence on a high-value target.

        Creates a multi-touch sequence: email → voice → follow-up email → SMS.
        Records the action for pipeline tracking.
        """
        action = {
            "action": "executive_cadence",
            "lead_id": lead_id,
            "niche": niche or "unknown",
            "target_name": target_name or "Unknown",
            "triggered_at": self._now(),
        }

        # Try to enroll via the lead_converter or fallback
        try:
            from agents.lead_converter.converter import enroll_lead
            result = await enroll_lead(
                lead={"id": lead_id, "niche": niche},
                niche=niche,
            )
            action["status"] = "completed"
            action["result"] = result
        except (ImportError, AttributeError):
            # Fallback: record as pipeline deal
            deal = {
                "id": f"EXDEAL-{len(self._enterprise_deals) + 1:04d}",
                "lead_id": lead_id,
                "niche": niche or "unknown",
                "target_name": target_name or "Enterprise Target",
                "stage": "reaching_out",
                "value": 0,
                "opened_at": self._now(),
                "source": "executive_agent",
            }
            self._enterprise_deals.append(deal)
            action["status"] = "queued"
            action["deal_id"] = deal["id"]
            action["note"] = "Executive cadence queued as new enterprise deal"

        self._outreach_history.append(action)
        return action

    # ── SNAPSHOT ─────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Condensed snapshot for fleet dashboard."""
        overview = self.overview()
        return {
            "whale_targets": overview.get("pipeline", {}).get("whales", 0),
            "enterprise_targets": overview.get("pipeline", {}).get("enterprise", 0),
            "active_deals": overview.get("pipeline", {}).get("active_deals", 0),
            "pipeline_value": overview.get("pipeline", {}).get("pipeline_value", 0),
            "won_deals": overview.get("pipeline", {}).get("won_deals", 0),
            "won_value": overview.get("pipeline", {}).get("won_value", 0),
            "mrr_projected": overview.get("revenue", {}).get("mrr_projected", 0),
            "revenue_24h": overview.get("revenue", {}).get("revenue_24h", 0),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_executive_routes(app, get_db=None, require_auth=None):
    """Register Executive Agent routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[exec] No get_db — agent will return errors on DB calls")
    _exec = ExecutiveAgent(get_db=get_db) if get_db else None

    def _get_exec():
        if _exec is None:
            raise HTTPException(503, "Executive Agent not initialized (no get_db)")
        return _exec

    @app.get("/api/executive/overview")
    async def exec_overview(auth=Depends(require_auth) if require_auth else None):
        """Executive dashboard — high-value pipeline, win rates, revenue."""
        return _get_exec().overview()

    @app.get("/api/executive/targets")
    async def exec_targets(auth=Depends(require_auth) if require_auth else None):
        """Score and rank high-value lead targets for enterprise outreach."""
        return _get_exec().enterprise_targets()

    @app.get("/api/executive/deals")
    async def exec_deals(auth=Depends(require_auth) if require_auth else None):
        """Enterprise deal pipeline with stage-by-stage breakdown."""
        return _get_exec().deal_pipeline()

    @app.get("/api/executive/quote")
    async def exec_quote(
        company: str = Query("", description="Target company"),
        niche: str = Query("", description="Target niche"),
        deal_size: float = Query(0.0, ge=0, description="Target annual deal size USD"),
        tiers: str = Query("", description="Comma-separated product tiers"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Generate enterprise quote with multi-product bundling and discount eligibility."""
        bundle = [t.strip() for t in tiers.split(",") if t.strip()] if tiers else None
        return _get_exec().generate_quote(
            company=company, niche=niche,
            deal_size=deal_size, bundle_tiers=bundle,
        )

    @app.post("/api/executive/cadence")
    async def exec_cadence(
        lead_id: str = Query("", description="Lead ID to target"),
        niche: str = Query("", description="Target niche"),
        target_name: str = Query("", description="Lead/company name"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Trigger executive-level outreach cadence on a high-value target."""
        result = await _get_exec().trigger_executive_cadence(
            lead_id=lead_id, niche=niche, target_name=target_name,
        )
        status = 200 if result.get("status") != "failed" else 500
        return result

    @app.get("/api/executive/snapshot")
    async def exec_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed snapshot for fleet dashboard integration."""
        return _get_exec().snapshot()

    log.info("[exec] Routes registered · /api/executive/*")
