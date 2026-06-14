"""
EMPIRE V49 · LOOP ENGINEERING AGENT
====================================
Lane execution optimization — throughput pacing, strategy A/B testing,
cycle tuning, and performance analytics on top of the mesh orchestrator.

Wire-up in hub.py:
    from empire_loop_agent import register_loop_routes
    register_loop_routes(app, require_auth=require_auth)
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Callable

log = logging.getLogger("empire.loop")

# ── LANE CONFIG (mirrors mesh_orchestrator.py) ──────────────────────
_LANE_GROUPS = {
    "Roofing Restoration": {"lanes": [0, 1, 2, 3, 4], "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    "HVAC": {"lanes": [5, 6], "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    "SEO": {"lanes": [7, 8, 9], "strategy": "STANDARD", "source": "SEO Optimizer"},
    "Legal": {"lanes": [10, 11, 12, 13, 14], "strategy": "RECALL_SNIPER", "source": "FDA Live Feed"},
    "Insurance": {"lanes": [15, 16, 17], "strategy": "INSURANCE_STRIKE", "source": "Insurance Lead Gen"},
    "Financial Services": {"lanes": [18, 19, 32, 33], "strategy": "FINANCIAL_STRIKE", "source": "Financial Lead Gen"},
    "Consumer CPA": {"lanes": [20, 21], "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    "Senior Care": {"lanes": [22, 23], "strategy": "SENIOR_STRIKE", "source": "Senior Lead Gen"},
    "Addiction Treatment": {"lanes": [24], "strategy": "HEALTH_STRIKE", "source": "Healthcare Lead Gen"},
    "Education": {"lanes": [25, 26], "strategy": "STANDARD", "source": "Edu Lead Gen"},
    "Healthcare": {"lanes": [27, 28], "strategy": "HEALTH_STRIKE", "source": "Healthcare Lead Gen"},
    "Business Services": {"lanes": [29, 30, 31], "strategy": "BIZ_STRIKE", "source": "B2B Lead Gen"},
    "Home Services": {"lanes": [34, 35], "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
}

_MOCK_LANE_STATS = {
    0: {"wins": 45, "losses": 15, "revenue": 270000, "runs": 60, "pacing_hours": 4},
    1: {"wins": 38, "losses": 12, "revenue": 228000, "runs": 50, "pacing_hours": 6},
    2: {"wins": 12, "losses": 8, "revenue": 72000, "runs": 20, "pacing_hours": 8},
    3: {"wins": 3, "losses": 1, "revenue": 37500, "runs": 4, "pacing_hours": 12},
    4: {"wins": 82, "losses": 18, "revenue": 520000, "runs": 100, "pacing_hours": 2},
    5: {"wins": 20, "losses": 12, "revenue": 96000, "runs": 32, "pacing_hours": 6},
    6: {"wins": 8, "losses": 18, "revenue": 24000, "runs": 26, "pacing_hours": 10},
    10: {"wins": 80, "losses": 20, "revenue": 480000, "runs": 100, "pacing_hours": 3},
    15: {"wins": 30, "losses": 10, "revenue": 150000, "runs": 40, "pacing_hours": 5},
    18: {"wins": 25, "losses": 15, "revenue": 125000, "runs": 40, "pacing_hours": 6},
    24: {"wins": 15, "losses": 5, "revenue": 120000, "runs": 20, "pacing_hours": 8},
    34: {"wins": 5, "losses": 2, "revenue": 45000, "runs": 7, "pacing_hours": 12},
    35: {"wins": 10, "losses": 5, "revenue": 30000, "runs": 15, "pacing_hours": 10},
}

_STRATEGY_COMPARE = [
    {"strategy": "AGGRESSIVE_STRIKE", "active_lanes": 7, "total_runs": 247, "total_wins": 185,
     "total_revenue": 1392500, "avg_win_rate": 0.749, "best_niche": "Roofing Restoration"},
    {"strategy": "RECALL_SNIPER", "active_lanes": 5, "total_runs": 220, "total_wins": 172,
     "total_revenue": 1150000, "avg_win_rate": 0.782, "best_niche": "Legal"},
    {"strategy": "STANDARD", "active_lanes": 5, "total_runs": 90, "total_wins": 52,
     "total_revenue": 320000, "avg_win_rate": 0.578, "best_niche": "Education"},
    {"strategy": "UGLY_BANNER", "active_lanes": 4, "total_runs": 73, "total_wins": 38,
     "total_revenue": 150000, "avg_win_rate": 0.520, "best_niche": "HVAC"},
    {"strategy": "FINANCIAL_STRIKE", "active_lanes": 4, "total_runs": 80, "total_wins": 50,
     "total_revenue": 375000, "avg_win_rate": 0.625, "best_niche": "Financial Services"},
    {"strategy": "INSURANCE_STRIKE", "active_lanes": 3, "total_runs": 60, "total_wins": 40,
     "total_revenue": 350000, "avg_win_rate": 0.667, "best_niche": "Insurance"},
    {"strategy": "SENIOR_STRIKE", "active_lanes": 2, "total_runs": 35, "total_wins": 20,
     "total_revenue": 180000, "avg_win_rate": 0.571, "best_niche": "Senior Care"},
    {"strategy": "HEALTH_STRIKE", "active_lanes": 3, "total_runs": 55, "total_wins": 35,
     "total_revenue": 280000, "avg_win_rate": 0.636, "best_niche": "Healthcare"},
    {"strategy": "BIZ_STRIKE", "active_lanes": 3, "total_runs": 45, "total_wins": 28,
     "total_revenue": 210000, "avg_win_rate": 0.622, "best_niche": "Business Services"},
]


class LoopAgent:
    """Lane execution optimization and engineering intelligence."""

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db

    def loop_overview(self) -> dict:
        """Aggregate lane health, execution cadence, and success rates."""
        total_lanes = 36
        assigned_lanes = sum(len(g["lanes"]) for g in _LANE_GROUPS.values())
        total_runs = sum(s.get("runs", 0) for s in _MOCK_LANE_STATS.values())
        total_wins = sum(s.get("wins", 0) for s in _MOCK_LANE_STATS.values())
        total_revenue = sum(s.get("revenue", 0) for s in _MOCK_LANE_STATS.values())
        active_lanes = len(_MOCK_LANE_STATS)
        return {
            "total_lanes": total_lanes,
            "assigned_lanes": assigned_lanes,
            "active_lanes": active_lanes,
            "idle_lanes": assigned_lanes - active_lanes,
            "unassigned_lanes": total_lanes - assigned_lanes,
            "total_runs": total_runs,
            "total_wins": total_wins,
            "total_revenue": round(total_revenue, 2),
            "overall_win_rate": round(total_wins / max(total_runs, 1), 4),
            "niches": {n: len(g["lanes"]) for n, g in _LANE_GROUPS.items()},
            "buyer_lanes": self._query_buyer_lanes(),
            "contractor_activity": self._query_contractor_activity(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _query_buyer_lanes(self) -> list[dict]:
        """Query buyers table and map each buyer to a lane-like record."""
        if not self.get_db:
            return []
        try:
            db = self.get_db()
            r = db.table("buyers").select("*").limit(200).execute()
            rows = r.data or []
        except Exception as e:
            log.warning(f"[loop] buyers query failed: {e}")
            return []
        lanes = []
        for row in rows:
            niche = row.get("niche", "") or "General"
            payout = float(row.get("base_payout", 0) or 0)
            calls_offered = int(row.get("calls_offered", 0) or 0)
            calls_accepted = int(row.get("calls_accepted", 0) or 0)
            is_active = row.get("is_active", False)
            retainer = float(row.get("monthly_retainer", 0) or 0)
            lanes.append({
                "lane_id": abs(hash(row.get("id", ""))) % 1000,
                "niche": niche,
                "strategy": "BUYER_MATCH",
                "source": "Buyers Table",
                "wins": calls_accepted,
                "losses": max(0, calls_offered - calls_accepted),
                "revenue": payout * calls_accepted + retainer,
                "runs": calls_offered,
                "pacing_hours": 8,
                "status": "active" if is_active else "inactive",
                "buyer_name": row.get("buyer_name", ""),
            })
        return lanes

    def _query_contractor_activity(self) -> dict:
        """Query contractors table for network activity metrics."""
        if not self.get_db:
            return {"total": 0, "active": 0, "completed_jobs": 0}
        try:
            db = self.get_db()
            r = db.table("contractors").select("active,completed_jobs", limit=500).execute()
            rows = r.data or []
            return {
                "total": len(rows),
                "active": sum(1 for row in rows if row.get("active")),
                "completed_jobs": sum(int(row.get("completed_jobs", 0) or 0) for row in rows),
            }
        except Exception as e:
            log.warning(f"[loop] contractors query failed: {e}")
            return {"total": 0, "active": 0, "completed_jobs": 0}

    def lane_detail(self, lane_id: int) -> dict:
        """Per-lane deep dive."""
        stats = _MOCK_LANE_STATS.get(lane_id)
        if stats is None:
            return {"lane_id": lane_id, "status": "no_data"}
        lane_data = None
        for niche, group in _LANE_GROUPS.items():
            if lane_id in group["lanes"]:
                lane_data = {"niche": niche, "strategy": group["strategy"], "source": group["source"]}
                break
        win_rate = round(stats["wins"] / max(stats["runs"], 1), 4)
        return {
            "lane_id": lane_id,
            "niche": lane_data["niche"] if lane_data else "Unknown",
            "strategy": lane_data["strategy"] if lane_data else "Unknown",
            "source": lane_data["source"] if lane_data else "Unknown",
            "stats": stats,
            "win_rate": win_rate,
            "avg_deal": round(stats["revenue"] / max(stats["wins"], 1), 2),
            "pacing_hours": stats.get("pacing_hours", 0),
            "recommendation": self._recommend(lane_id, stats, win_rate),
        }

    def _recommend(self, lane_id: int, stats: dict, win_rate: float) -> str:
        if stats["runs"] < 5:
            return "EXPLORE_NEED_MORE_DATA"
        if win_rate >= 0.6 and stats["revenue"] > 0:
            return "AGGRESSIVE_EXECUTE"
        if win_rate >= 0.3:
            return "CAUTIOUS_PROCEED"
        return "HOLD_RECONSIDER"

    def all_lanes(self) -> list[dict]:
        """Return data for all lanes."""
        all_lane_ids = {lid for g in _LANE_GROUPS.values() for lid in g["lanes"]}
        return [self.lane_detail(lid) for lid in sorted(all_lane_ids)]

    def pacing_analysis(self) -> dict:
        """Analyze execution timing and pacing."""
        niches_pacing = []
        for niche, group in _LANE_GROUPS.items():
            lane_stats = [_MOCK_LANE_STATS.get(lid) for lid in group["lanes"] if lid in _MOCK_LANE_STATS]
            if not lane_stats:
                continue
            avg_pacing = sum(s.get("pacing_hours", 0) for s in lane_stats) / len(lane_stats)
            total_runs = sum(s.get("runs", 0) for s in lane_stats)
            niches_pacing.append({
                "niche": niche,
                "lanes": len(group["lanes"]),
                "active": len(lane_stats),
                "avg_pacing_hours": round(avg_pacing, 1),
                "total_runs": total_runs,
                "runs_per_day": round(total_runs / 30, 1),
            })
        niches_pacing.sort(key=lambda n: n["avg_pacing_hours"])
        return {
            "niches": niches_pacing,
            "fastest": niches_pacing[0]["niche"] if niches_pacing else None,
            "slowest": niches_pacing[-1]["niche"] if niches_pacing else None,
            "overall_avg_pacing": round(
                sum(n["avg_pacing_hours"] for n in niches_pacing) / max(len(niches_pacing), 1), 1
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def strategy_performance(self) -> dict:
        """Cross-lane strategy comparison."""
        return {
            "strategies": _STRATEGY_COMPARE,
            "count": len(_STRATEGY_COMPARE),
            "best_by_win_rate": max(_STRATEGY_COMPARE, key=lambda s: s["avg_win_rate"]),
            "best_by_revenue": max(_STRATEGY_COMPARE, key=lambda s: s["total_revenue"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def throughput_forecast(self) -> dict:
        """Forecast execution capacity based on historical pacing."""
        pacing = self.pacing_analysis()
        total_runs = sum(n["total_runs"] for n in pacing["niches"])
        daily_capacity = round(total_runs / 30, 1)
        weekly_capacity = round(daily_capacity * 7, 1)
        monthly_capacity = round(daily_capacity * 30, 1)
        return {
            "daily_capacity": daily_capacity,
            "weekly_capacity": weekly_capacity,
            "monthly_capacity": monthly_capacity,
            "current_monthly_runs": total_runs,
            "utilization_pct": round(total_runs / max(monthly_capacity, 1) * 100, 1),
            "bottleneck_niches": [
                n for n in pacing["niches"] if n["avg_pacing_hours"] > 10
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def optimization_suggestions(self) -> list[dict]:
        """Lane-specific tuning recommendations."""
        suggestions = []
        for lid in range(36):
            if lid not in _LANE_GROUPS and lid not in _MOCK_LANE_STATS:
                continue
            detail = self.lane_detail(lid)
            if detail.get("status") == "no_data":
                continue
            if detail.get("recommendation") == "HOLD_RECONSIDER":
                suggestions.append({
                    "lane_id": lid,
                    "niche": detail["niche"],
                    "strategy": detail["strategy"],
                    "issue": "low_win_rate",
                    "recommendation": f"Strategy '{detail['strategy']}' underperforming for {detail['niche']}. Consider switching to a higher-performing strategy."
                })
            if detail.get("stats", {}).get("pacing_hours", 0) > 10:
                suggestions.append({
                    "lane_id": lid,
                    "niche": detail["niche"],
                    "strategy": detail["strategy"],
                    "issue": "slow_pacing",
                    "recommendation": f"Pacing at {detail['stats']['pacing_hours']}h. Increase execution frequency or parallelize."
                })
        return suggestions

    def loop_report(self) -> dict:
        """Consolidated loop engineering report."""
        overview = self.loop_overview()
        pacing = self.pacing_analysis()
        strategies = self.strategy_performance()
        forecast = self.throughput_forecast()
        suggestions = self.optimization_suggestions()
        return {
            "overview": overview,
            "pacing": pacing,
            "strategies": strategies,
            "forecast": forecast,
            "optimizations": suggestions,
            "optimization_count": len(suggestions),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def register_loop_routes(app, require_auth=None, get_db=None):
    """Register Loop Engineering API routes on a FastAPI app."""
    from fastapi import Depends

    agent = LoopAgent(get_db=get_db)

    @app.get("/api/loop/overview")
    async def loop_overview(auth=Depends(require_auth) if require_auth else None):
        return agent.loop_overview()

    @app.get("/api/loop/lanes")
    async def loop_lanes(auth=Depends(require_auth) if require_auth else None):
        return {"lanes": agent.all_lanes()}

    @app.get("/api/loop/lane/{lane_id}")
    async def loop_lane_detail(lane_id: int, auth=Depends(require_auth) if require_auth else None):
        return agent.lane_detail(lane_id)

    @app.get("/api/loop/pacing")
    async def loop_pacing(auth=Depends(require_auth) if require_auth else None):
        return agent.pacing_analysis()

    @app.get("/api/loop/strategies")
    async def loop_strategies(auth=Depends(require_auth) if require_auth else None):
        return agent.strategy_performance()

    @app.get("/api/loop/forecast")
    async def loop_forecast(auth=Depends(require_auth) if require_auth else None):
        return agent.throughput_forecast()

    @app.get("/api/loop/report")
    async def loop_report(auth=Depends(require_auth) if require_auth else None):
        return agent.loop_report()

    log.info("[loop] routes registered: /api/loop/{overview,lanes,lane/{id},pacing,strategies,forecast,report}")
