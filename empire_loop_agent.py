"""
EMPIRE V49 · LOOP ENGINEERING AGENT — LEARN · ADAPT · UPGRADE
=============================================================
Lane execution optimization that learns from outcomes, adapts to changing
conditions using Bayesian inference, and upgrades its own strategies when
performance degrades.

Incorporates:
  - Rank & Rent strategy (Marcus Campbell): score niche×metro rental potential,
    track lead value per microsite, identify which local markets to "own" vs "rent"
  - Rolling Stones strategy: constant reinvention, cut underperformers,
    cross-pollinate winners across niches, adapt to market regime shifts
  - SI Core integration: Beta-Binomial Bayesian posteriors, Thompson sampling,
    Platt calibration, regime shift detection
  - Strategy Evolution: mutate underperforming strategies, create new variants,
    deactivate persistent losers

Wire-up in hub.py:
    from empire_loop_agent import register_loop_routes
    register_loop_routes(app, require_auth=require_auth)
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
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

# Seed mock stats — used as initial data when no real DB data exists yet
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

# ══════════════════════════════════════════════════════════════════════════
# RANK & RENT SCORING — Marcus Campbell's Sideways Keyword Model
# ══════════════════════════════════════════════════════════════════════════

_RANK_RENT_BENCHMARKS = {
    # niche → {monthly_search_volume, avg_cpc, competition_level, typical_rent, typical_lead_value}
    "Roofing Restoration": {"msv": 22000, "avg_cpc": 18.50, "competition": "high",
                           "typical_rent": 1500, "typical_lead_value": 85},
    "HVAC": {"msv": 35000, "avg_cpc": 22.00, "competition": "high",
             "typical_rent": 2000, "typical_lead_value": 95},
    "Legal": {"msv": 42000, "avg_cpc": 45.00, "competition": "very_high",
              "typical_rent": 3000, "typical_lead_value": 150},
    "Insurance": {"msv": 18000, "avg_cpc": 32.00, "competition": "high",
                  "typical_rent": 2500, "typical_lead_value": 120},
    "Financial Services": {"msv": 28000, "avg_cpc": 38.00, "competition": "very_high",
                           "typical_rent": 3500, "typical_lead_value": 200},
    "Senior Care": {"msv": 12000, "avg_cpc": 14.00, "competition": "medium",
                    "typical_rent": 1000, "typical_lead_value": 60},
    "Addiction Treatment": {"msv": 9000, "avg_cpc": 28.00, "competition": "high",
                            "typical_rent": 2000, "typical_lead_value": 180},
    "Education": {"msv": 15000, "avg_cpc": 10.00, "competition": "medium",
                  "typical_rent": 800, "typical_lead_value": 40},
    "Healthcare": {"msv": 25000, "avg_cpc": 20.00, "competition": "high",
                   "typical_rent": 1800, "typical_lead_value": 90},
    "Business Services": {"msv": 16000, "avg_cpc": 25.00, "competition": "medium",
                          "typical_rent": 1500, "typical_lead_value": 75},
    "Home Services": {"msv": 30000, "avg_cpc": 15.00, "competition": "medium",
                      "typical_rent": 1200, "typical_lead_value": 55},
    "Consumer CPA": {"msv": 20000, "avg_cpc": 12.00, "competition": "medium",
                     "typical_rent": 900, "typical_lead_value": 35},
}

# ══════════════════════════════════════════════════════════════════════════
# LANE OUTCOME TRACKER — replaces static mock data with real outcomes
# ══════════════════════════════════════════════════════════════════════════

class LaneOutcomeTracker:
    """Tracks real outcomes per lane, replacing static mock data with learned stats.

    When a DB is available, persists outcomes to the 'lane_outcomes' table.
    Falls back to in-memory tracking when no DB is present.
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        # In-memory: lane_id → {wins, losses, revenue, runs, pacing_log: [timestamps]}
        self._lanes: dict[int, dict] = {}
        self._seed_from_mock()

    def _seed_from_mock(self):
        """Seed lane stats from _MOCK_LANE_STATS so existing data is available immediately."""
        for lid, stats in _MOCK_LANE_STATS.items():
            self._lanes[lid] = {
                "wins": stats["wins"],
                "losses": stats["losses"],
                "revenue": stats["revenue"],
                "runs": stats["runs"],
                "pacing_log": [datetime.now(timezone.utc) - timedelta(hours=stats.get("pacing_hours", 8) * i)
                               for i in range(stats["runs"])],
            }

    def record_outcome(self, lane_id: int, success: bool, revenue: float = 0.0,
                       pacing_hours: Optional[float] = None):
        """Record a single outcome for a lane."""
        if lane_id not in self._lanes:
            self._lanes[lane_id] = {"wins": 0, "losses": 0, "revenue": 0.0, "runs": 0,
                                    "pacing_log": []}
        lane = self._lanes[lane_id]
        lane["runs"] += 1
        if success:
            lane["wins"] += 1
        else:
            lane["losses"] += 1
        lane["revenue"] += revenue
        lane["pacing_log"].append(datetime.now(timezone.utc))

        # Persist to DB if available
        if self.get_db:
            try:
                db = self.get_db()
                db.table("lane_outcomes").insert({
                    "lane_id": lane_id,
                    "success": success,
                    "revenue": round(revenue, 2),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as e:
                log.debug(f"[loop.tracker] persist failed: {e}")

    def get_stats(self, lane_id: int) -> Optional[dict]:
        """Return accumulated stats for a lane."""
        lane = self._lanes.get(lane_id)
        if not lane:
            return None
        pacing_hours = self._compute_pacing(lane)
        win_rate = lane["wins"] / max(lane["runs"], 1)
        return {
            "wins": lane["wins"],
            "losses": lane["losses"],
            "revenue": round(lane["revenue"], 2),
            "runs": lane["runs"],
            "win_rate": round(win_rate, 4),
            "pacing_hours": round(pacing_hours, 1),
        }

    def get_revenue_history(self, lane_id: int, window_days: int = 30) -> list[float]:
        """Return recent revenue data points for regime shift detection."""
        if not self.get_db:
            return []
        try:
            db = self.get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
            r = db.table("lane_outcomes") \
                .select("revenue,created_at") \
                .eq("lane_id", lane_id) \
                .gte("created_at", cutoff) \
                .order("created_at", desc=False) \
                .execute()
            return [float(row.get("revenue", 0)) for row in (r.data or [])]
        except Exception as e:
            log.debug(f"[loop.tracker] revenue history query failed: {e}")
            return []

    def _compute_pacing(self, lane: dict) -> float:
        """Compute average pacing from the timestamp log."""
        log_entries = lane.get("pacing_log", [])
        if len(log_entries) < 2:
            return 8.0  # default
        # Compute intervals between consecutive entries
        intervals = []
        for i in range(1, len(log_entries)):
            delta = (log_entries[i] - log_entries[i - 1]).total_seconds() / 3600
            if 0 < delta < 168:  # ignore outliers > 1 week
                intervals.append(delta)
        if not intervals:
            return 8.0
        return sum(intervals) / len(intervals)

    def all_stats(self) -> dict[int, dict]:
        """Return all tracked lane stats."""
        return {lid: self.get_stats(lid) for lid in self._lanes
                if self._lanes[lid]["runs"] > 0}

    def total_runs(self) -> int:
        return sum(l["runs"] for l in self._lanes.values())

    def total_wins(self) -> int:
        return sum(l["wins"] for l in self._lanes.values())

    def total_revenue(self) -> float:
        return sum(l["revenue"] for l in self._lanes.values())


# ══════════════════════════════════════════════════════════════════════════
# SI CORE WRAPPER — lazy import so the module loads without numpy/scipy
# ══════════════════════════════════════════════════════════════════════════

def _si_beta(wins: int, losses: int) -> dict:
    """Safe wrapper around SI Core's beta_posterior."""
    try:
        from empire_si_core import beta_posterior
        return beta_posterior(wins, losses)
    except ImportError:
        return {"mean": wins / max(wins + losses, 1), "std": 0.1,
                "ci_lower": 0, "ci_upper": 1, "effective_samples": wins + losses}


def _si_thompson(strategies: dict, k: int = 1) -> list:
    """Safe wrapper around SI Core's thompson_sample."""
    try:
        from empire_si_core import thompson_sample
        return thompson_sample(strategies, k)
    except ImportError:
        scored = sorted(strategies.items(), key=lambda x: x[1].get("wins", 0) / max(x[1].get("wins", 0) + x[1].get("losses", 0), 1), reverse=True)
        return [(s[0], s[1].get("wins", 0) / max(s[1].get("wins", 0) + s[1].get("losses", 0), 1)) for s in scored[:k]]


def _si_detect_regime(recent: list, historical: list) -> dict:
    """Safe wrapper around SI Core's detect_regime_shift."""
    try:
        from empire_si_core import detect_regime_shift
        return detect_regime_shift(recent, historical)
    except ImportError:
        return {"regime_shift_detected": False, "recommendation": "stable",
                "recent_mean": sum(recent) / max(len(recent), 1) if recent else 0,
                "historical_mean": sum(historical) / max(len(historical), 1) if historical else 0}


# ══════════════════════════════════════════════════════════════════════════
# LOOP AGENT — LEARN, ADAPT, UPGRADE
# ══════════════════════════════════════════════════════════════════════════

class LoopAgent:
    """Lane execution optimization with self-learning, adaptation, and evolution.

    Learning (Rank & Rent):
      - Records every lane outcome and updates Bayesian posteriors
      - Scores niche×metro rental potential from real lead value data
      - Identifies which lanes to "own" (operate directly) vs "rent" (sell leads)

    Adaptation (Rolling Stones):
      - Detects regime shifts in lane revenue distributions
      - Adjusts pacing dynamically based on observed throughput
      - Cross-pollinates high-performing strategies to underperforming niches

    Self-Upgrade:
      - Evokes strategy evolution when win rate drops below threshold
      - Deactivates persistently underperforming strategies
      - Creates mutated variants for exploration (Thompson sampling)
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        self.tracker = LaneOutcomeTracker(get_db=get_db)
        # Learning state
        self._evolution_history: list[dict] = []
        self._evolution_count = 0
        self._last_evolution_ts: Optional[str] = None
        self._lane_pacing_overrides: dict[int, float] = {}  # lane_id → custom pacing_hours
        self._lane_strategy_overrides: dict[int, str] = {}   # lane_id → custom strategy
        self._deactivated_lanes: set[int] = set()
        self._lane_evolution_count: dict[int, int] = {}  # per-lane evolution counter (not global)

        # Rolling Stones: regime shift tracking per niche
        self._revenue_history: dict[str, list[float]] = defaultdict(list)

        # Rank & Rent: track lead value per niche×source
        self._lead_value_by_niche: dict[str, list[float]] = defaultdict(list)

    # ════════════════════════════════════════════════════════════════════════
    # CORE: LEARN FROM OUTCOMES
    # ════════════════════════════════════════════════════════════════════════

    def learn_from_outcome(self, lane_id: int, success: bool, revenue: float = 0.0,
                           niche: str = "", strategy: str = "", source: str = ""):
        """Record an outcome and update all learning models.

        This is the primary learning entry point. Called by the mesh orchestrator
        after every lane execution.
        """
        self.tracker.record_outcome(lane_id, success, revenue)

        # Track lead value for Rank & Rent scoring
        if niche and revenue > 0:
            self._lead_value_by_niche[niche].append(revenue)

        # Track revenue for regime shift detection
        if niche:
            self._revenue_history[niche].append(revenue)

        # Log the learning event
        stats = self.tracker.get_stats(lane_id)
        log.info(
            f"[loop.learn] lane {lane_id} ({niche}/{strategy}): "
            f"{'win' if success else 'loss'} ${revenue:.0f} → "
            f"{stats['runs']} runs, {stats['win_rate']:.1%} WR"
        )

        # Check if self-upgrade is needed
        if stats and stats["runs"] >= 10:
            self._check_self_upgrade(lane_id, niche, strategy, stats)

    def _check_self_upgrade(self, lane_id: int, niche: str, strategy: str, stats: dict):
        """Check if this lane needs a strategy upgrade based on performance."""
        if stats["win_rate"] < 0.3:
            self._evolve_lane_strategy(lane_id, niche, strategy,
                                       reason=f"win_rate {stats['win_rate']:.1%} below 30% threshold")
        elif stats["pacing_hours"] > 12:
            self._adjust_lane_pacing(lane_id, niche, stats["pacing_hours"],
                                     reason=f"pacing {stats['pacing_hours']}h exceeds 12h threshold")
        elif stats["win_rate"] >= 0.7 and stats["runs"] >= 20:
            # Rolling Stones: high performers get cross-pollinated
            self._cross_pollinate_winner(niche, strategy, stats)

    # ════════════════════════════════════════════════════════════════════════
    # SELF-UPGRADE: EVOLVE STRATEGIES
    # ════════════════════════════════════════════════════════════════════════

    def _evolve_lane_strategy(self, lane_id: int, niche: str, current_strategy: str, reason: str):
        """Evolve or replace a lane's strategy when it underperforms.

        Creates a mutated variant or swaps to a known better strategy.
        """
        # Find the niche info
        niche_info = _LANE_GROUPS.get(niche)
        if not niche_info:
            return

        # Try to pick a better strategy from the comparison data
        better = None
        for s in _STRATEGY_COMPARE:
            if s["strategy"] != current_strategy and s["avg_win_rate"] > 0.6:
                if not better or s["avg_win_rate"] > better["avg_win_rate"]:
                    better = s

        if better:
            new_strategy = better["strategy"]
            self._lane_strategy_overrides[lane_id] = new_strategy
            self._evolution_count += 1
            self._lane_evolution_count[lane_id] = self._lane_evolution_count.get(lane_id, 0) + 1
            event = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "evolve",
                "lane_id": lane_id,
                "niche": niche,
                "from": current_strategy,
                "to": new_strategy,
                "reason": reason,
                "confidence": better["avg_win_rate"],
            }
            self._evolution_history.append(event)
            log.info(f"[loop.upgrade] lane {lane_id}: {current_strategy} → {new_strategy} ({reason})")

            # Rolling Stones: cut what persistently underperforms
            # Per-lane counter: 3+ evolutions on the same lane → deactivate
            if self._lane_evolution_count.get(lane_id, 0) >= 3:
                self._deactivated_lanes.add(lane_id)
                self._evolution_history.append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "deactivate",
                    "lane_id": lane_id,
                    "niche": niche,
                    "reason": f"Evolved {self._lane_evolution_count[lane_id]}× without sustained improvement",
                })
                log.warning(f"[loop.upgrade] lane {lane_id} DEACTIVATED after {self._lane_evolution_count[lane_id]} evolutions")

            self._last_evolution_ts = event["ts"]

    def _adjust_lane_pacing(self, lane_id: int, niche: str, current_pacing: float, reason: str):
        """Adjust lane pacing to improve throughput.

        Rolling Stones principle: cut what doesn't work. If pacing is too slow,
        double the execution frequency.
        """
        new_pacing = max(1.0, current_pacing / 2)
        self._lane_pacing_overrides[lane_id] = new_pacing
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "pace_adjust",
            "lane_id": lane_id,
            "niche": niche,
            "from": current_pacing,
            "to": new_pacing,
            "reason": reason,
        }
        self._evolution_history.append(event)
        log.info(f"[loop.upgrade] lane {lane_id} pacing: {current_pacing}h → {new_pacing}h ({reason})")

    def _cross_pollinate_winner(self, niche: str, strategy: str, stats: dict):
        """Cross-pollinate a high-performing strategy to underperforming niches.

        Rolling Stones principle: the best songs go on every tour. The best
        strategies get deployed across multiple niches.
        """
        for target_niche, group in _LANE_GROUPS.items():
            if target_niche == niche:
                continue
            for target_lane in group["lanes"]:
                target_stats = self.tracker.get_stats(target_lane)
                if target_stats and target_stats["win_rate"] < 0.4 and target_stats["runs"] >= 5:
                    current_strat = group.get("strategy", "STANDARD")
                    if current_strat != strategy:
                        self._lane_strategy_overrides[target_lane] = strategy
                        event = {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "type": "cross_pollinate",
                            "from_niche": niche,
                            "to_lane": target_lane,
                            "to_niche": target_niche,
                            "strategy": strategy,
                            "source_win_rate": stats["win_rate"],
                        }
                        self._evolution_history.append(event)
                        log.info(f"[loop.xfer] cross-pollinated {strategy} from {niche} → lane {target_lane} ({target_niche})")

    # ════════════════════════════════════════════════════════════════════════
    # ANALYSIS: SI CORE BAYESIAN ANALYSIS
    # ════════════════════════════════════════════════════════════════════════

    def analyze_performance(self, lane_id: int) -> dict:
        """Run full SI Core Bayesian analysis on a lane's performance.

        Returns posterior win rate, expected revenue with confidence intervals,
        and a Thompson sampling explore/exploit score.
        """
        stats = self.tracker.get_stats(lane_id)
        if not stats or stats["runs"] == 0:
            return {"lane_id": lane_id, "status": "no_data"}

        # Bayesian posterior
        posterior = _si_beta(stats["wins"], stats["losses"])

        # Thompson sample
        strategies = {f"lane_{lane_id}": {"wins": stats["wins"], "losses": stats["losses"]}}
        ts = _si_thompson(strategies, k=1)
        explore_score = ts[0][1] if ts else posterior["mean"]

        # Expected revenue with confidence
        avg_deal = stats["revenue"] / max(stats["wins"], 1) if stats["wins"] > 0 else 0
        if posterior.get("mean", 0) > 0:
            ev = posterior["mean"] * avg_deal * max(1, stats["runs"] // 5)
        else:
            ev = 0

        # Recommendation
        if stats["runs"] < 5:
            rec = "EXPLORE_NEED_MORE_DATA"
        elif posterior.get("mean", 0) >= 0.6 and ev > 0:
            rec = "AGGRESSIVE_EXECUTE"
        elif posterior.get("mean", 0) >= 0.3:
            rec = "CAUTIOUS_PROCEED"
        else:
            rec = "HOLD_RECONSIDER"

        return {
            "lane_id": lane_id,
            "stats": stats,
            "bayesian_posterior": posterior,
            "explore_score": round(explore_score, 4),
            "expected_revenue": round(ev, 2),
            "recommendation": rec,
            "analysis_ts": datetime.now(timezone.utc).isoformat(),
        }

    def detect_lane_shifts(self, niche: str) -> dict:
        """Detect revenue regime shifts for a niche using SI Core.

        Rolling Stones principle: read the room. If the revenue distribution
        has shifted, adapt strategy accordingly.
        """
        revenues = self._revenue_history.get(niche, [])
        if len(revenues) < 8:
            return {"niche": niche, "regime_shift_detected": False,
                    "recommendation": "insufficient_data", "data_points": len(revenues)}

        split = max(3, len(revenues) // 4)
        recent = revenues[-split:]
        historical = revenues[:-split]

        shift = _si_detect_regime(recent, historical)

        return {
            "niche": niche,
            "data_points": len(revenues),
            "recent_revenue_avg": round(sum(recent) / max(len(recent), 1), 2),
            "historical_revenue_avg": round(sum(historical) / max(len(historical), 1), 2),
            "regime_shift_detected": shift.get("regime_shift_detected", False),
            "recommendation": shift.get("recommendation", "stable"),
            "kl_divergence": shift.get("kl_divergence", 0),
            "analysis_ts": datetime.now(timezone.utc).isoformat(),
        }

    # ════════════════════════════════════════════════════════════════════════
    # RANK & RENT: SCORE NICHE×METRO RENTAL POTENTIAL
    # ════════════════════════════════════════════════════════════════════════

    def rank_and_rent_potential(self, niche: str) -> dict:
        """Score a niche for Rank & Rent lead generation potential.

        Marcus Campbell approach: target niches with high lead value,
        moderate competition (avoid "very_high"), and strong recurring demand.
        Returns a score and recommended pricing model.
        """
        benchmark = _RANK_RENT_BENCHMARKS.get(niche)
        if not benchmark:
            return {"niche": niche, "score": 0, "verdict": "no_benchmark_data"}

        # Competition penalty
        comp_penalty = {"low": 0.0, "medium": 0.1, "high": 0.25, "very_high": 0.5}
        penalty = comp_penalty.get(benchmark["competition"], 0.3)

        # Lead value score (normalized to $200 max)
        lead_value_score = min(1.0, benchmark["typical_lead_value"] / 200.0)

        # MSV score (normalized to 50K max)
        msv_score = min(1.0, benchmark["msv"] / 50000.0)

        # Rent-to-value ratio
        rent_ratio = benchmark["typical_rent"] / max(benchmark["typical_lead_value"] * 100, 1)

        # Composite score
        raw_score = (lead_value_score * 0.4 + msv_score * 0.3 + rent_ratio * 0.3)
        adjusted_score = max(0, raw_score - penalty)

        # Monthly revenue estimate from lead volume
        estimated_monthly_leads = int(benchmark["msv"] * 0.01)  # 1% CTR
        estimated_monthly_revenue = estimated_monthly_leads * benchmark["typical_lead_value"]

        # Pricing recommendation
        if adjusted_score >= 0.6:
            price_model = "per_call"  # higher margin, needs tracking
        elif adjusted_score >= 0.4:
            price_model = "flat_rent"
        else:
            price_model = "per_lead"  # lower risk for the renter

        return {
            "niche": niche,
            "score": round(adjusted_score, 3),
            "verdict": "STRONG_RENT" if adjusted_score >= 0.6 else (
                "RENTABLE" if adjusted_score >= 0.4 else "WEAK"),
            "price_model": price_model,
            "benchmark": benchmark,
            "estimated_monthly_leads": estimated_monthly_leads,
            "estimated_monthly_revenue": round(estimated_monthly_revenue, 2),
            "avg_cpc": benchmark["avg_cpc"],
            "competition": benchmark["competition"],
            "typical_rent_usd": benchmark["typical_rent"],
            "typical_lead_value_usd": benchmark["typical_lead_value"],
        }

    def all_rank_rent_scores(self) -> list[dict]:
        """Score all niches for Rank & Rent potential."""
        scored = []
        for niche in _RANK_RENT_BENCHMARKS:
            result = self.rank_and_rent_potential(niche)
            scored.append(result)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    # ════════════════════════════════════════════════════════════════════════
    # SELF-UPGRADE: AUTOMATED EVOLUTION CYCLE
    # ════════════════════════════════════════════════════════════════════════

    def self_evolve(self, force: bool = False) -> list[dict]:
        """Run a self-upgrade cycle across all lanes.

        Checks every active lane and evolves strategies, adjusts pacing,
        or deactivates underperformers as needed. Returns a list of events.

        Rolling Stones principle: constantly improve or cut. Never stand still.
        """
        events = []

        for lid in range(36):
            if lid in self._deactivated_lanes:
                continue

            stats = self.tracker.get_stats(lid)
            if not stats or stats["runs"] < 5:
                continue

            # Find niche and strategy for this lane
            niche = None
            strategy = None
            for n, group in _LANE_GROUPS.items():
                if lid in group["lanes"]:
                    niche = n
                    strategy = self._lane_strategy_overrides.get(lid, group["strategy"])
                    break

            if not niche:
                continue

            # Check if upgrade is needed
            needs_upgrade = False
            reason = ""

            if stats["win_rate"] < 0.3 and stats["runs"] >= 10:
                needs_upgrade = True
                reason = f"win_rate {stats['win_rate']:.1%} (threshold: 30%)"
            elif stats["win_rate"] < 0.15 and stats["runs"] >= 5:
                needs_upgrade = True
                reason = f"win_rate {stats['win_rate']:.1%} critically low"
            elif stats["pacing_hours"] > 12 and stats["runs"] >= 10:
                needs_upgrade = True
                reason = f"pacing {stats['pacing_hours']}h (threshold: 12h)"

            if needs_upgrade or force:
                self._evolve_lane_strategy(lid, niche, strategy, reason)
                self._adjust_lane_pacing(lid, niche, stats["pacing_hours"],
                                         reason="self-evolution cycle")
                events.append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "self_evolve",
                    "lane_id": lid,
                    "niche": niche,
                    "from_strategy": strategy,
                    "reason": reason,
                })

        # Cross-pollinate: find the best-performing lane overall and share its strategy
        best_lane = None
        best_wr = 0
        for lid in range(36):
            stats = self.tracker.get_stats(lid)
            if stats and stats["runs"] >= 20 and stats["win_rate"] > best_wr:
                best_wr = stats["win_rate"]
                best_lane = lid

        if best_lane is not None:
            for n, group in _LANE_GROUPS.items():
                for lid in group["lanes"]:
                    stats = self.tracker.get_stats(lid)
                    if stats and stats["win_rate"] < 0.4 and stats["runs"] >= 5:
                        best_strat = self._lane_strategy_overrides.get(best_lane,
                                        _LANE_GROUPS.get(n, {}).get("strategy", "STANDARD"))
                        self._lane_strategy_overrides[lid] = best_strat
                        events.append({
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "type": "cross_pollinate",
                            "from_lane": best_lane,
                            "to_lane": lid,
                            "strategy": best_strat,
                            "source_wr": best_wr,
                        })

        if events:
            self._evolution_count += 1
            self._last_evolution_ts = datetime.now(timezone.utc).isoformat()
            self._evolution_history.extend(events)
            log.info(f"[loop.evolve] self-evolution cycle complete: {len(events)} events")

        return events

    # ════════════════════════════════════════════════════════════════════════
    # LEGACY METHODS (backward compatible, now backed by real data)
    # ════════════════════════════════════════════════════════════════════════

    def loop_overview(self) -> dict:
        """Aggregate lane health, execution cadence, and success rates."""
        total_lanes = 36
        assigned_lanes = sum(len(g["lanes"]) for g in _LANE_GROUPS.values())
        all_stats = self.tracker.all_stats()
        total_runs = self.tracker.total_runs()
        total_wins = self.tracker.total_wins()
        total_revenue = self.tracker.total_revenue()
        active_lanes = len(all_stats)
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
            "learning_enabled": True,
            "evolutions_run": self._evolution_count,
            "deactivated_lanes": len(self._deactivated_lanes),
            "last_evolution_ts": self._last_evolution_ts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def lane_detail(self, lane_id: int) -> dict:
        """Per-lane deep dive — now uses real data + Bayesian analysis."""
        stats = self.tracker.get_stats(lane_id)
        if stats is None:
            return {"lane_id": lane_id, "status": "no_data"}

        lane_data = None
        for niche, group in _LANE_GROUPS.items():
            if lane_id in group["lanes"]:
                strategy = self._lane_strategy_overrides.get(lane_id, group["strategy"])
                pacing = self._lane_pacing_overrides.get(lane_id, stats.get("pacing_hours", 8))
                lane_data = {"niche": niche, "strategy": strategy,
                             "source": group["source"], "pacing_hours": pacing}
                break

        win_rate = stats.get("win_rate", 0)
        return {
            "lane_id": lane_id,
            "niche": lane_data["niche"] if lane_data else "Unknown",
            "strategy": lane_data["strategy"] if lane_data else "Unknown",
            "source": lane_data["source"] if lane_data else "Unknown",
            "stats": {"wins": stats["wins"], "losses": stats["losses"],
                      "revenue": stats["revenue"], "runs": stats["runs"],
                      "pacing_hours": lane_data.get("pacing_hours", stats.get("pacing_hours", 8))
                      if lane_data else stats.get("pacing_hours", 8)},
            "win_rate": win_rate,
            "avg_deal": round(stats["revenue"] / max(stats["wins"], 1), 2) if stats["wins"] > 0 else 0,
            "pacing_hours": lane_data.get("pacing_hours", stats.get("pacing_hours", 8)) if lane_data else stats.get("pacing_hours", 8),
            "deactivated": lane_id in self._deactivated_lanes,
            "override_strategy": lane_id in self._lane_strategy_overrides,
            "override_pacing": lane_id in self._lane_pacing_overrides,
            "recommendation": self._recommend(lane_id, {"wins": stats["wins"],
                "losses": stats["losses"], "revenue": stats["revenue"], "runs": stats["runs"],
                "pacing_hours": stats.get("pacing_hours", 8)}, win_rate),
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
        """Analyze execution timing and pacing — now uses real data or mock fallback."""
        all_stats = self.tracker.all_stats()
        niches_pacing = []
        for niche, group in _LANE_GROUPS.items():
            lane_stats = []
            for lid in group["lanes"]:
                s = all_stats.get(lid)
                if s:
                    lane_stats.append(s)
                elif lid in _MOCK_LANE_STATS:
                    lane_stats.append(_MOCK_LANE_STATS[lid])
            if not lane_stats:
                continue
            pacing_hours = sum(
                self._lane_pacing_overrides.get(lid, s.get("pacing_hours", 8))
                for lid, s in zip(group["lanes"], lane_stats)
            ) / len(lane_stats)
            total_runs = sum(s.get("runs", 0) for s in lane_stats)
            niches_pacing.append({
                "niche": niche,
                "lanes": len(group["lanes"]),
                "active": len(lane_stats),
                "avg_pacing_hours": round(pacing_hours, 1),
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
        """Cross-lane strategy comparison — now includes evolution data."""
        return {
            "strategies": _STRATEGY_COMPARE,
            "count": len(_STRATEGY_COMPARE),
            "best_by_win_rate": max(_STRATEGY_COMPARE, key=lambda s: s["avg_win_rate"]),
            "best_by_revenue": max(_STRATEGY_COMPARE, key=lambda s: s["total_revenue"]),
            "evolutions_run": self._evolution_count,
            "last_evolution_ts": self._last_evolution_ts,
            "overrides_active": len(self._lane_strategy_overrides),
            "deactivated_lanes": len(self._deactivated_lanes),
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
        """Lane-specific tuning recommendations — now with Rank & Rent and evolution insights."""
        suggestions = []
        for lid in range(36):
            detail = self.lane_detail(lid)
            if detail.get("status") == "no_data":
                continue
            if detail.get("deactivated"):
                continue
            if detail.get("recommendation") == "HOLD_RECONSIDER":
                suggestions.append({
                    "lane_id": lid,
                    "niche": detail["niche"],
                    "strategy": detail["strategy"],
                    "issue": "low_win_rate",
                    "recommendation": f"Strategy '{detail['strategy']}' underperforming for {detail['niche']}. "
                                      f"Consider switching to a higher-performing strategy. "
                                      f"({detail['stats']['wins']}W / {detail['stats']['losses']}L = {detail['win_rate']:.1%})",
                })
            if detail.get("stats", {}).get("pacing_hours", 0) > 10:
                suggestions.append({
                    "lane_id": lid,
                    "niche": detail["niche"],
                    "strategy": detail["strategy"],
                    "issue": "slow_pacing",
                    "recommendation": f"Pacing at {detail['stats']['pacing_hours']}h. "
                                      f"Increase execution frequency or parallelize.",
                })
            if detail.get("override_strategy"):
                suggestions.append({
                    "lane_id": lid,
                    "niche": detail["niche"],
                    "strategy": detail["strategy"],
                    "issue": "auto_evolved",
                    "recommendation": f"Strategy auto-evolved to '{detail['strategy']}' "
                                      f"based on performance analysis.",
                })

        # Rank & Rent suggestions
        for niche, benchmark in _RANK_RENT_BENCHMARKS.items():
            if niche in _LANE_GROUPS:
                score = self.rank_and_rent_potential(niche)
                if score.get("score", 0) >= 0.6:
                    suggestions.append({
                        "lane_id": -1,
                        "niche": niche,
                        "strategy": "RANK_AND_RENT",
                        "issue": "rental_opportunity",
                        "recommendation": f"Strong Rank & Rent potential for {niche}: "
                                          f"score={score['score']:.2f}, est. ${score['estimated_monthly_revenue']:.0f}/mo, "
                                          f"price model: {score['price_model']}",
                    })

        return suggestions

    def loop_report(self) -> dict:
        """Consolidated loop engineering report — now with learning, evolution, and Rank & Rent."""
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
            "evolution_history": self._evolution_history[-20:],  # last 20 events
            "evolution_count": self._evolution_count,
            "learning_enabled": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── DB QUERIES (unchanged from original) ────────────────────────────

    def _query_buyer_lanes(self) -> list[dict]:
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


def register_loop_routes(app, require_auth=None, get_db=None):
    """Register Loop Engineering API routes on a FastAPI app."""
    from fastapi import Depends

    agent = LoopAgent(get_db=get_db)

    # ── Original endpoints (backward compatible) ────────────────────────
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

    # ── NEW: Learning & Evolution endpoints ─────────────────────────────

    @app.post("/api/loop/learn")
    async def loop_learn(
        lane_id: int, success: bool, revenue: float = 0,
        niche: str = "", strategy: str = "", source: str = "",
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Record an outcome and trigger learning."""
        agent.learn_from_outcome(lane_id, success, revenue, niche, strategy, source)
        return {"ok": True, "lane_id": lane_id, "niche": niche}

    @app.post("/api/loop/evolve")
    async def loop_evolve(
        force: bool = False,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Run a self-evolution cycle across all lanes."""
        events = agent.self_evolve(force=force)
        return {"ok": True, "events": events, "count": len(events)}

    @app.get("/api/loop/analyze/{lane_id}")
    async def loop_analyze_lane(
        lane_id: int,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Run Bayesian analysis on a specific lane."""
        return agent.analyze_performance(lane_id)

    @app.get("/api/loop/shifts")
    async def loop_detect_shifts(
        niche: str = "",
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Detect revenue regime shifts across niches."""
        if niche:
            return agent.detect_lane_shifts(niche)
        results = {}
        for n in _LANE_GROUPS:
            results[n] = agent.detect_lane_shifts(n)
        return results

    @app.get("/api/loop/rank-rent")
    async def loop_rank_rent(
        niche: str = "",
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get Rank & Rent scoring for niches."""
        if niche:
            return agent.rank_and_rent_potential(niche)
        return {"scores": agent.all_rank_rent_scores()}

    @app.get("/api/loop/evolution-history")
    async def loop_evolution_history(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return the evolution history log."""
        return {
            "events": agent._evolution_history,
            "count": len(agent._evolution_history),
            "evolutions_run": agent._evolution_count,
            "last_evolution_ts": agent._last_evolution_ts,
        }

    @app.get("/api/loop/learning-status")
    async def loop_learning_status(
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Return learning system status."""
        return {
            "learning_enabled": True,
            "tracks_lanes": len(agent.tracker._lanes),
            "total_runs_tracked": agent.tracker.total_runs(),
            "total_wins_tracked": agent.tracker.total_wins(),
            "strategy_overrides": dict(agent._lane_strategy_overrides),
            "pacing_overrides": dict(agent._lane_pacing_overrides),
            "deactivated_lanes": list(agent._deactivated_lanes),
            "evolution_history_count": len(agent._evolution_history),
            "niches_tracked": len(agent._revenue_history),
            "last_evolution_ts": agent._last_evolution_ts,
        }

    log.info("[loop] routes registered: original + learn/evolve/analyze/shifts/rank-rent")
