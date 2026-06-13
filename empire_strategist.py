"""
EMPIRE V49 · STRATEGIST AGENT
===============================
Dedicated strategic intelligence agent that:
- Analyzes strategy evolution data from StrategyEvolution
- Generates per-niche strategic recommendations
- Tracks performance trends over time
- Produces actionable narratives about what's working
- Identifies emerging opportunities and risks

Routes (registered via hub.py):
  GET  /api/strategist/overview        — High-level strategic snapshot
  GET  /api/strategist/niche/{niche}   — Deep-dive analysis for one niche
  GET  /api/strategist/recommendations — Actionable strategic recommendations
  GET  /api/strategist/trends          — Performance trend data (time series)
  GET  /api/strategist/narrative       — LLM-generated strategic narrative
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.strategist")


class StrategistAgent:
    """
    Strategic intelligence agent. Reads live data from StrategyEvolution,
    the SI adaptive engine, revenue tracker, and BrainDecider to produce
    actionable strategic analysis and recommendations.
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        self._recommendation_cache: dict = {}
        self._trend_cache: dict = {}
        self._last_trend_ts: Optional[str] = None

    # ── HELPERS ────────────────────────────────────────────────────────────

    def _get_si_strategy(self) -> Optional[dict]:
        """Fetch live StrategyEvolution snapshot."""
        try:
            from empire_si_strategy import StrategyEvolution
            inst = StrategyEvolution.get_shared_instance()
            if inst and hasattr(inst, "snapshot"):
                return inst.snapshot()
        except Exception as e:
            log.debug(f"[strategist] si_strategy fetch failed: {e}")
        return None

    def _get_adaptive(self) -> Optional[dict]:
        """Fetch AdaptiveEngine snapshot."""
        try:
            from empire_si_adaptive import AdaptiveEngine
            # Use module-level singleton or fallback
            inst = AdaptiveEngine.__module__
            # Try to get the instance from hub's wiring
            import sys
            for mod_name, mod in sys.modules.items():
                if hasattr(mod, "adaptive_engine") and hasattr(getattr(mod, "adaptive_engine"), "snapshot"):
                    return getattr(mod, "adaptive_engine").snapshot()
        except Exception:
            pass
        return None

    def _get_revenue(self) -> dict:
        """Fetch revenue snapshot from predictive_revenue bot."""
        out = {"total_24h": 0, "mrr_projected": 0, "calls_24h": 0, "lanes_active": 0}
        try:
            from bots import predictive_revenue
            pl = predictive_revenue.per_lane_forecast() or {}
            totals = pl.get("totals", {}) or {}
            out["total_24h"] = totals.get("revenue_24h", 0)
            out["mrr_projected"] = totals.get("mrr_projected", 0)
            out["calls_24h"] = totals.get("calls_24h", 0)
            out["lanes_active"] = totals.get("lanes_active", 0)
        except Exception:
            pass
        return out

    # ── OVERVIEW ────────────────────────────────────────────────────────────

    def overview(self) -> dict:
        """
        High-level strategic snapshot combining SI strategy, adaptive engine,
        and revenue intelligence into a single view.
        """
        si = self._get_si_strategy() or {}
        rev = self._get_revenue()

        by_niche = si.get("by_niche", {}) or {}
        best_per = si.get("best_per_niche", {}) or {}
        strategies = si.get("strategies", []) or si.get("active_strategies", 0)

        # Build niche summary cards
        niches = []
        for niche_name, data in sorted(by_niche.items()):
            if niche_name == "__base__":
                continue
            s_list = data if isinstance(data, list) else []
            total_score = sum(s.get("score", 0) for s in s_list)
            total_runs = sum(s.get("runs", 0) for s in s_list)
            best = best_per.get(niche_name, {})
            niches.append({
                "niche": niche_name,
                "strategies": len(s_list),
                "total_score": round(total_score, 3),
                "total_runs": total_runs,
                "best_strategy": best.get("name"),
                "best_score": round(best.get("score", 0), 3),
            })

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "active_strategies": len(strategies) if isinstance(strategies, list) else strategies,
            "evolution_runs": si.get("evolution_runs", 0),
            "generation": si.get("generation", 0),
            "fitness_avg": si.get("fitness_avg", 0),
            "niches": niches,
            "revenue": rev,
            "last_evolution_ts": si.get("last_evolution_ts"),
        }

    # ── NICHE DEEP DIVE ─────────────────────────────────────────────────────

    def niche_analysis(self, niche: str) -> dict:
        """
        Deep-dive analysis for a single niche. Returns strategy breakdown,
        win rates, genome comparison, and actionable intel.
        """
        si = self._get_si_strategy() or {}
        by_niche = si.get("by_niche", {}) or {}
        data = by_niche.get(niche, [])
        if isinstance(data, dict):
            data = data.get("strategies", data.get("items", []))
        if not isinstance(data, list):
            data = []

        # Rank strategies by score
        ranked = sorted(data, key=lambda s: s.get("score", 0), reverse=True)
        best = ranked[0] if ranked else None

        # Genome comparison: show how strategies differ
        genome_compare = []
        if len(ranked) >= 2:
            top2 = ranked[:2]
            traits = ["aggressiveness", "risk_tolerance", "outreach_intensity",
                      "price_premium", "narrow_focus"]
            for t in traits:
                v1 = (top2[0].get("genome") or {}).get(t, 0)
                v2 = (top2[1].get("genome") or {}).get(t, 0)
                genome_compare.append({
                    "trait": t,
                    "best": round(v1, 3),
                    "runner_up": round(v2, 3),
                    "delta": round(v1 - v2, 3),
                })

        # Win rate distribution
        win_rates = [s.get("win_rate", 0) for s in ranked if s.get("runs", 0) > 0]
        avg_win_rate = round(sum(win_rates) / len(win_rates), 3) if win_rates else 0

        # Best genome as actionable profile
        profile_key = None
        if best:
            g = best.get("genome", {})
            if g.get("aggressiveness", 0) > 0.65:
                profile_key = "aggressive_strike"
            elif g.get("risk_tolerance", 0) > 0.5 and g.get("narrow_focus", 0) > 0.6:
                profile_key = "recall_sniper"
            elif g.get("aggressiveness", 0) < 0.5:
                profile_key = "conservative_ugly_banner"
            else:
                profile_key = "balanced_standard"

        return {
            "niche": niche,
            "strategy_count": len(ranked),
            "active_strategies": len([s for s in ranked if s.get("is_active", True)]),
            "best_strategy": best.get("name") if best else None,
            "best_score": round(best.get("score", 0), 3) if best else 0,
            "best_genome": best.get("genome") if best else {},
            "profile_key": profile_key,
            "avg_win_rate": avg_win_rate,
            "total_runs": sum(s.get("runs", 0) for s in ranked),
            "genome_comparison": genome_compare,
            "strategies": ranked[:10],  # top 10
        }

    # ── RECOMMENDATIONS ─────────────────────────────────────────────────────

    def recommendations(self) -> list[dict]:
        """
        Generate actionable strategic recommendations.
        Analyzes underperforming niches, genome gaps, and revenue opportunities.
        """
        si = self._get_si_strategy() or {}
        rev = self._get_revenue()
        by_niche = si.get("by_niche", {}) or {}
        best_per = si.get("best_per_niche", {}) or {}

        recs = []

        for niche_name, data in sorted(by_niche.items()):
            if niche_name == "__base__":
                continue
            s_list = data if isinstance(data, list) else []
            best = best_per.get(niche_name, {})

            active = [s for s in s_list if s.get("is_active", True)]
            inactive = [s for s in s_list if not s.get("is_active", True)]
            low_performers = [s for s in active if s.get("score", 0) < 0.1 and s.get("runs", 0) > 5]

            # Recommendation: deactivate true underperformers
            if low_performers and len(active) > 2:
                recs.append({
                    "type": "deactivate",
                    "niche": niche_name,
                    "priority": "medium",
                    "message": f"Consider deactivating {len(low_performers)} underperforming strategies in {niche_name} (score < 0.1)",
                    "detail": [s["name"] for s in low_performers],
                })

            # Recommendation: need more exploration
            if len(active) < 3:
                recs.append({
                    "type": "explore",
                    "niche": niche_name,
                    "priority": "high",
                    "message": f"Only {len(active)} active strategies for {niche_name} — run evolution to generate more variants",
                    "detail": [],
                })

            # Recommendation: low sample count
            total_runs = sum(s.get("runs", 0) for s in s_list)
            if total_runs < 20 and total_runs > 0:
                recs.append({
                    "type": "gather_data",
                    "niche": niche_name,
                    "priority": "medium",
                    "message": f"Only {total_runs} outcomes for {niche_name} — need more data for confident evolution",
                    "detail": [],
                })

            # Recommendation: stale niche (no best strategy)
            if not best.get("name") and total_runs > 5:
                recs.append({
                    "type": "stale",
                    "niche": niche_name,
                    "priority": "high",
                    "message": f"No clear winning strategy for {niche_name} — run evolution cycle",
                    "detail": [],
                })

        # Revenue-based recommendations
        if rev.get("mrr_projected", 0) < 1000:
            recs.append({
                "type": "revenue_gap",
                "niche": "__system__",
                "priority": "critical",
                "message": f"Projected MRR (${rev.get('mrr_projected', 0)}) is below $1K threshold — consider aggressive outreach strategies",
                "detail": [],
            })

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recs.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 99))

        return recs

    # ── TRENDS ──────────────────────────────────────────────────────────────

    def trends(self, days: int = 14) -> dict:
        """
        Build trend data for the dashboard. Returns per-niche time series
        of scores, win rates, and activity levels over the last N days.
        Uses synthetic quarterly buckets from available evolution events.
        """
        si = self._get_si_strategy() or {}
        by_niche = si.get("by_niche", {}) or {}
        events = si.get("evolution_events", []) or []

        # Build per-niche trend lines from evolution events
        niches = {}
        for niche_name, data in sorted(by_niche.items()):
            if niche_name == "__base__":
                continue
            s_list = data if isinstance(data, list) else []

            # Aggregate stats
            scores = [s.get("score", 0) for s in s_list if s.get("score", 0) > 0]
            win_rates = [s.get("win_rate", 0) for s in s_list if s.get("runs", 0) > 0]
            runs = [s.get("runs", 0) for s in s_list]

            # Build synthetic trend line from evolution event timestamps
            niche_events = [e for e in events if e.get("niche") == niche_name]
            # Group by day
            day_buckets = {}
            for ev in niche_events:
                ts = ev.get("ts", "")
                day = ts[:10] if ts else "unknown"
                bucket = day_buckets.setdefault(day, {"evolves": 0, "deactivates": 0})
                if ev.get("type") == "evolve":
                    bucket["evolves"] += 1
                elif ev.get("type") == "deactivate":
                    bucket["deactivates"] += 1

            # Sort days
            sorted_days = sorted(day_buckets.keys())

            niches[niche_name] = {
                "total_score": round(sum(scores), 3),
                "avg_score": round(sum(scores) / len(scores), 3) if scores else 0,
                "avg_win_rate": round(sum(win_rates) / len(win_rates), 3) if win_rates else 0,
                "total_runs": sum(runs),
                "strategy_count": len(s_list),
                "trend_days": [
                    {"day": d, **day_buckets[d]}
                    for d in sorted_days[-days:]
                ],
            }

        # Overall system trend
        total_evolutions = sum(
            niches[n]["trend_days"] for n in niches
        ) if niches else []

        return {
            "niches": niches,
            "total_strategies": sum(n["strategy_count"] for n in niches.values()),
            "total_active": sum(n["strategy_count"] for n in niches.values()),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # ── NARRATIVE ───────────────────────────────────────────────────────────

    def generate_narrative(self) -> dict:
        """
        Generate an LLM-powered strategic narrative using local Ollama.
        Falls back to a template-based narrative if Ollama is unavailable.
        """
        overview = self.overview()
        recs = self.recommendations()
        rev = self._get_revenue()

        # Try LLM narrative first
        try:
            import httpx
            niches_text = json.dumps([n["niche"] for n in overview.get("niches", [])], indent=2)
            recs_text = json.dumps(recs[:5], indent=2)

            prompt = f"""You are a strategic analyst for an AI-powered lead generation system. 
Write a concise strategic narrative (3-4 paragraphs) based on:

Active strategies: {overview.get('active_strategies', 0)}
Total niches: {len(overview.get('niches', []))}
Evolution cycles: {overview.get('evolution_runs', 0)}
Total fitness: {overview.get('fitness_avg', 0)}
Revenue 24h: ${rev.get('total_24h', 0)}
Projected MRR: ${rev.get('mrr_projected', 0)}

Niches: {niches_text}

Top recommendations: {recs_text}

Focus on: what's working, what needs attention, and the most actionable next step."""

            r = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.1:latest",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.6, "num_predict": 512},
                },
                timeout=30.0,
            )
            if r.status_code == 200:
                data = r.json()
                narrative = data.get("response", "").strip()
                if narrative:
                    return {
                        "narrative": narrative,
                        "source": "llm",
                        "model": "llama3.1:latest",
                    }
        except Exception as e:
            log.debug(f"[strategist] LLM narrative failed: {e}")

        # Fallback template narrative
        active = overview.get("active_strategies", 0)
        niche_count = len(overview.get("niches", []))
        revenue_24h = rev.get("total_24h", 0)
        mrr = rev.get("mrr_projected", 0)

        narrative_parts = [
            f"The system is currently running {active} active strategies across {niche_count} niches.",
        ]

        if revenue_24h > 0:
            narrative_parts.append(
                f"Revenue in the last 24 hours is ${revenue_24h}, with a projected MRR of ${mrr}."
            )

        critical = [r for r in recs if r.get("priority") == "critical"]
        high = [r for r in recs if r.get("priority") == "high"]

        if critical:
            narrative_parts.append(
                f"Critical attention needed: {critical[0]['message']}"
            )
        if high:
            narrative_parts.append(
                f"High-priority items: {len(high)} recommendations require attention."
            )
        if not critical and not high:
            narrative_parts.append(
                "All niches have healthy strategy activity. Continue monitoring and running evolution cycles."
            )

        return {
            "narrative": " ".join(narrative_parts),
            "source": "template",
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────────

def register_strategist_routes(app, require_auth=None):
    """
    Register Strategist Agent endpoints on a FastAPI app.
    """
    strategist = StrategistAgent()

    if require_auth:

        @app.get("/api/strategist/overview")
        async def _overview(auth=Depends(require_auth)):
            return strategist.overview()

        @app.get("/api/strategist/niche/{niche}")
        async def _niche(niche: str, auth=Depends(require_auth)):
            return strategist.niche_analysis(niche)

        @app.get("/api/strategist/recommendations")
        async def _recommendations(auth=Depends(require_auth)):
            return strategist.recommendations()

        @app.get("/api/strategist/trends")
        async def _trends(auth=Depends(require_auth)):
            return strategist.trends()

        @app.get("/api/strategist/narrative")
        async def _narrative(auth=Depends(require_auth)):
            return strategist.generate_narrative()

    else:

        @app.get("/api/strategist/overview")
        async def _overview():
            return strategist.overview()

        @app.get("/api/strategist/niche/{niche}")
        async def _niche(niche: str):
            return strategist.niche_analysis(niche)

        @app.get("/api/strategist/recommendations")
        async def _recommendations():
            return strategist.recommendations()

        @app.get("/api/strategist/trends")
        async def _trends():
            return strategist.trends()

        @app.get("/api/strategist/narrative")
        async def _narrative():
            return strategist.generate_narrative()

    log.info("[strategist] Routes registered · /api/strategist/*")


# Lazy import for FastAPI Depends
from fastapi import Depends  # noqa: E402
