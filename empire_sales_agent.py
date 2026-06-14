"""
EMPIRE V49 · SALES AGENT
=========================
Full sales workflow management agent that:
- Manages pipeline stages, deals, and win rates
- Generates quotes, proposals, and pricing sheets
- Produces sales forecasts and close-rate projections
- Tracks territory planning and coverage gaps

Routes (registered via hub.py):
  GET  /api/sales/pipeline          — Pipeline overview by stage
  GET  /api/sales/quote             — Generate a quote for a lead
  GET  /api/sales/forecast          — Sales forecast with projections
  GET  /api/sales/territories       — Territory coverage analysis
  GET  /api/sales/deals             — Recent deals log
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.sales_agent")

# ── Pipeline stages ────────────────────────────────────────────────
PIPELINE_STAGES = [
    "prospecting", "qualification", "presentation", "negotiation",
    "closed_won", "closed_lost",
]


class SalesAgent:
    """Full sales workflow management: pipeline, quoting, forecasting, territories."""

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        self._deals: list[dict] = []
        self._quotes: list[dict] = []

    # ── HELPERS ────────────────────────────────────────────────────────────

    def _get_revenue(self) -> dict:
        """Fetch revenue data from predictive_revenue."""
        out = {"total_24h": 0, "mrr_projected": 0, "calls_24h": 0, "active_buyers": 0}
        try:
            from bots import predictive_revenue
            pl = predictive_revenue.per_lane_forecast() or {}
            totals = pl.get("totals", {}) or {}
            out["total_24h"] = totals.get("revenue_24h", 0)
            out["mrr_projected"] = totals.get("mrr_projected", 0)
            out["calls_24h"] = totals.get("calls_24h", 0)
            out["active_buyers"] = totals.get("active_buyers", 0)
        except Exception:
            pass
        return out

    def _get_closer_stats(self) -> dict:
        """Fetch AI Closer stats for pipeline insight."""
        try:
            from empire_ai_closer import AICloser
            # Try to get stats from closer singleton if available
            import sys
            for mod_name, mod in sorted(sys.modules.items()):
                if hasattr(mod, "_ai_closer_instance") and mod._ai_closer_instance:
                    inst = mod._ai_closer_instance
                    if hasattr(inst, "snapshot"):
                        return inst.snapshot()
        except Exception:
            pass
        return {}

    # ── PIPELINE ───────────────────────────────────────────────────────────

    def pipeline(self) -> dict:
        """
        Pipeline overview: deals by stage, conversion rates, velocity.
        """
        rev = self._get_revenue()
        closer = self._get_closer_stats()

        # Build stage counts from closer stats
        stage_counts = {
            "prospecting": closer.get("leads_processed", 0) - closer.get("brain_go", 0),
            "qualification": closer.get("brain_go", 0),
            "presentation": closer.get("agi_stream_calls", 0) + closer.get("static_calls", 0),
            "negotiation": closer.get("static_calls", 0),
            "closed_won": closer.get("agi_stream_calls", 0),
            "closed_lost": closer.get("brain_no_go", 0),
        }

        total = sum(stage_counts.values())
        stages = []
        for stage in PIPELINE_STAGES:
            count = stage_counts.get(stage, 0)
            pct = round(count / max(total, 1) * 100, 1)
            stages.append({
                "stage": stage,
                "count": count,
                "pct": pct,
                "label": stage.replace("_", " ").title(),
            })

        # Conversion rates between stages
        conversion = {}
        for i in range(len(PIPELINE_STAGES) - 1):
            frm = stage_counts.get(PIPELINE_STAGES[i], 0)
            to = stage_counts.get(PIPELINE_STAGES[i + 1], 0)
            rate = round(to / max(frm, 1) * 100, 1) if frm > 0 else 0
            conversion[f"{PIPELINE_STAGES[i]}_to_{PIPELINE_STAGES[i+1]}"] = {
                "from": PIPELINE_STAGES[i].replace("_", " ").title(),
                "to": PIPELINE_STAGES[i + 1].replace("_", " ").title(),
                "rate_pct": rate,
                "count": to,
            }

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_deals": total,
            "stages": stages,
            "conversion_rates": conversion,
            "revenue": {
                "revenue_24h": rev.get("total_24h", 0),
                "mrr_projected": rev.get("mrr_projected", 0),
                "active_buyers": rev.get("active_buyers", 0),
                "revenue_per_deal": round(
                    rev.get("total_24h", 0) / max(total, 1), 2
                ),
            },
        }

    # ── QUOTING ────────────────────────────────────────────────────────────

    def generate_quote(self, lead_name: str = "", tier: str = "", mrr: float = 0.0) -> dict:
        """
        Generate a quote/proposal for a lead.
        Looks up pricing from product_metadata when possible.
        """
        # Try to get pricing from product_metadata
        suite_products = []
        try:
            if self.get_db:
                db = self.get_db()
                r = db.table("product_metadata").select(
                    "tier,display_name,monthly_price_usd,description"
                ).eq("is_active", True).order("sort_order").execute()
                suite_products = r.data or []
        except Exception:
            pass

        if not suite_products:
            # Fallback pricing
            suite_products = [
                {"tier": "SEO_STARTER", "display_name": "SEO Starter", "monthly_price_usd": 99.0, "description": "Entry-level SEO"},
                {"tier": "SEO_GROWTH", "display_name": "SEO Growth", "monthly_price_usd": 199.0, "description": "Growth-tier SEO"},
                {"tier": "SEO_PRO", "display_name": "SEO Pro", "monthly_price_usd": 499.0, "description": "Pro SEO"},
                {"tier": "ALL_ACCESS", "display_name": "All Access", "monthly_price_usd": 2499.0, "description": "Full suite access"},
            ]

        # Find matching product or recommend based on MRR
        selected = None
        if tier:
            for p in suite_products:
                if p["tier"] == tier.upper():
                    selected = p
                    break
        if not selected and mrr > 0:
            for p in sorted(suite_products, key=lambda x: x["monthly_price_usd"], reverse=True):
                if mrr >= p["monthly_price_usd"]:
                    selected = p
                    break

        if not selected:
            # Default to first product
            selected = suite_products[0] if suite_products else {
                "tier": "CUSTOM", "display_name": "Custom Quote", "monthly_price_usd": 0.0
            }

        import hashlib
        quote_id = f"QTE-{hashlib.md5(f'{lead_name}{datetime.now().isoformat()}'.encode()).hexdigest()[:8].upper()}"

        quote = {
            "quote_id": quote_id,
            "lead_name": lead_name or "Prospective Client",
            "date": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "product": selected["display_name"],
                    "tier": selected["tier"],
                    "description": selected.get("description", ""),
                    "monthly_price": selected["monthly_price_usd"],
                    "setup_fee": round(selected["monthly_price_usd"] * 0.5, 2),
                    "qty": 1,
                }
            ],
            "monthly_total": selected["monthly_price_usd"],
            "setup_total": round(selected["monthly_price_usd"] * 0.5, 2),
            "annual_saving": round(selected["monthly_price_usd"] * 2, 2),  # 2 months free on annual
            "terms": "Monthly billing. 30-day cancellation notice.",
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        }

        self._quotes.append(quote)
        return quote

    # ── FORECAST ───────────────────────────────────────────────────────────

    def forecast(self, days: int = 30) -> dict:
        """
        Sales forecast with pipeline-based projections.
        """
        rev = self._get_revenue()
        pipe = self.pipeline()
        stages = pipe.get("stages", [])

        # Current deal value from pipeline
        total_deals = pipe.get("total_deals", 0)
        avg_deal_size = rev.get("revenue_24h", 0) / max(rev.get("calls_24h", 1), 1)

        # Forecast scenarios
        # Best case: all in-presentation close
        presentation_count = sum(s["count"] for s in stages if s["stage"] in ("presentation",))
        # Likely case: ~30% of negotiation close
        negotiation_count = sum(s["count"] for s in stages if s["stage"] in ("negotiation",))
        # Worst case: ~10% of qualification close
        qualification_count = sum(s["count"] for s in stages if s["stage"] in ("qualification",))

        best_case = round(presentation_count * avg_deal_size, 2)
        likely_case = round(negotiation_count * avg_deal_size * 0.3, 2)
        worst_case = round(qualification_count * avg_deal_size * 0.1, 2)

        # Build daily projection
        daily_values = []
        base_revenue = rev.get("total_24h", 0)
        for i in range(min(days, 90)):
            day_rev = round(base_revenue * (1 + i * 0.02), 2)  # 2% growth per day
            daily_values.append({
                "day": i + 1,
                "projected": day_rev,
                "cumulative": round(sum(daily_values[j]["projected"] for j in range(i)) + day_rev, 2) if i > 0 else day_rev,
            })

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "current_mrr": rev.get("mrr_projected", 0),
            "avg_deal_size": round(avg_deal_size, 2),
            "projected_new_revenue": {
                "best_case": best_case,
                "likely_case": likely_case,
                "worst_case": worst_case,
            },
            "projected_total_mrr": {
                "best_case": round(rev.get("mrr_projected", 0) + best_case, 2),
                "likely_case": round(rev.get("mrr_projected", 0) + likely_case, 2),
                "worst_case": round(rev.get("mrr_projected", 0) + worst_case, 2),
            },
            "daily_projection": daily_values,
        }

    # ── TERRITORIES ─────────────────────────────────────────────────────────

    def territories(self) -> dict:
        """
        Territory coverage analysis based on recent deals, calls, and buyer data.
        """
        rev = self._get_revenue()

        # Synthetic territory data from available sources
        territories = [
            {
                "name": "Southeast",
                "states": ["FL", "GA", "AL", "SC", "NC"],
                "active_leads": rev.get("active_buyers", 0),
                "calls_24h": rev.get("calls_24h", 0),
                "coverage_pct": 85,
                "priority": "high",
            },
            {
                "name": "Gulf Coast",
                "states": ["TX", "LA", "MS", "AL", "FL"],
                "active_leads": max(1, rev.get("active_buyers", 0) - 3),
                "calls_24h": max(0, rev.get("calls_24h", 0) - 5),
                "coverage_pct": 72,
                "priority": "high",
            },
            {
                "name": "Midwest",
                "states": ["IL", "IN", "OH", "MI", "MO", "KS"],
                "active_leads": max(1, rev.get("active_buyers", 0) - 5),
                "calls_24h": max(0, rev.get("calls_24h", 0) - 10),
                "coverage_pct": 60,
                "priority": "medium",
            },
            {
                "name": "Northeast",
                "states": ["NY", "NJ", "PA", "MA", "CT"],
                "active_leads": max(1, rev.get("active_buyers", 0) - 2),
                "calls_24h": max(0, rev.get("calls_24h", 0) - 3),
                "coverage_pct": 78,
                "priority": "medium",
            },
            {
                "name": "West Coast",
                "states": ["CA", "OR", "WA", "NV", "AZ"],
                "active_leads": max(1, rev.get("active_buyers", 0) - 4),
                "calls_24h": max(0, rev.get("calls_24h", 0) - 8),
                "coverage_pct": 55,
                "priority": "low",
            },
        ]

        # Coverage gaps
        gaps = [t for t in territories if t["coverage_pct"] < 70]

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "territories": territories,
            "coverage_gaps": gaps,
            "total_territories": len(territories),
            "avg_coverage": round(sum(t["coverage_pct"] for t in territories) / len(territories), 1),
        }

    # ── DEALS LOG ──────────────────────────────────────────────────────────

    def deals_log(self, limit: int = 20) -> list:
        """Return recent deals from in-memory log."""
        return list(reversed(self._deals[-limit:]))

    # ── SNAPSHOT ───────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return sales agent stats for the SPA."""
        rev = self._get_revenue()
        return {
            "pipeline_total": sum(s["count"] for s in self.pipeline().get("stages", [])),
            "quotes_generated": len(self._quotes),
            "mrr_projected": rev.get("mrr_projected", 0),
            "revenue_24h": rev.get("total_24h", 0),
            "active_buyers": rev.get("active_buyers", 0),
            "modified": datetime.now(timezone.utc).isoformat(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────────

def register_sales_routes(app, require_auth=None):
    """Register Sales Agent endpoints on a FastAPI app."""
    sales = SalesAgent()

    if require_auth:

        @app.get("/api/sales/pipeline")
        async def _pipeline(auth=Depends(require_auth)):
            return sales.pipeline()

        @app.get("/api/sales/quote")
        async def _quote(lead_name: str = "", tier: str = "", mrr: float = 0.0, auth=Depends(require_auth)):
            return sales.generate_quote(lead_name=lead_name, tier=tier, mrr=mrr)

        @app.get("/api/sales/forecast")
        async def _forecast(days: int = 30, auth=Depends(require_auth)):
            return sales.forecast(days=max(1, min(days, 365)))

        @app.get("/api/sales/territories")
        async def _territories(auth=Depends(require_auth)):
            return sales.territories()

        @app.get("/api/sales/deals")
        async def _deals(limit: int = 20, auth=Depends(require_auth)):
            return sales.deals_log(limit=max(1, min(limit, 100)))

    else:

        @app.get("/api/sales/pipeline")
        async def _pipeline():
            return sales.pipeline()

        @app.get("/api/sales/quote")
        async def _quote(lead_name: str = "", tier: str = "", mrr: float = 0.0):
            return sales.generate_quote(lead_name=lead_name, tier=tier, mrr=mrr)

        @app.get("/api/sales/forecast")
        async def _forecast(days: int = 30):
            return sales.forecast(days=max(1, min(days, 365)))

        @app.get("/api/sales/territories")
        async def _territories():
            return sales.territories()

        @app.get("/api/sales/deals")
        async def _deals(limit: int = 20):
            return sales.deals_log(limit=max(1, min(limit, 100)))

    log.info("[sales_agent] Routes registered · /api/sales/*")


from fastapi import Depends  # noqa: E402
