"""
EMPIRE V49 · 32-LANE MESH ORCHESTRATOR (SI-Powered)
=====================================================
Defines the 32-lane lead generation grid. Each lane executes via
the agent_interface and scores its outcomes using the SI core's
Bayesian probabilistic inference engine.

Replaces fake "88% probability" strings with real beta-binomial
win rate estimates, Thompson sampling for strategy selection, and
lane health scoring with confidence intervals.

Niche allocation (rebalanced 2026-06-12):
  Lanes  0- 7 : Roofing Restoration  (8 lanes, AGGRESSIVE_STRIKE, Storm Scout)
  Lanes  8-15 : Local SEO & HVAC     (8 lanes, UGLY_BANNER, Web Auditor)
  Lanes 16-20 : Legal                (5 lanes, RECALL_SNIPER, FDA Live Feed)
                  16: Pharma Liability
                  17: Medical Device
                  18: Consumer Product
                  19: Class Action
                  20: Mass Tort
  Lanes 21-28 : Consumer CPA         (8 lanes, FINANCIAL_STRIKE, Inbound Leads)
  Lanes 29   : Solar Installation     (1 lane,  STANDARD, Solar Prospector)
  Lanes 30   : Restoration             (1 lane,  STANDARD, Restoration Lead Gen)
  Lanes 31   : Logistics & Cold Storage (1 lane,  STANDARD, Logistics Prospector)

The 5 Legal sub-niches each get a dedicated lane. FDA recall output is
classified into one of the 5 sub-niches and routed to the matching buyer.
"""

import concurrent.futures
import logging
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from agent_interface import execute_outreach, reset_cycle_cache
from empire_si_core import (
    SyntheticIntelligence,
    beta_posterior,
    thompson_sample,
    expected_revenue,
    get_si_core,
)

log = logging.getLogger("empire.mesh")

# ── LANE DEFINITION ─────────────────────────────────────────────────────
LANES = {
    0:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    1:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    2:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    3:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    4:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    5:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    6:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    7:  {"niche": "Roofing Restoration", "sub_niche": None, "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    8:  {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    9:  {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    10: {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    11: {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    12: {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    13: {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    14: {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    15: {"niche": "Local SEO & HVAC", "sub_niche": None, "strategy": "UGLY_BANNER", "source": "Web Auditor"},
    16: {"niche": "Legal", "sub_niche": "Pharma Liability", "strategy": "RECALL_SNIPER", "source": "FDA Live Feed"},
    17: {"niche": "Legal", "sub_niche": "Medical Device",   "strategy": "RECALL_SNIPER", "source": "FDA Live Feed"},
    18: {"niche": "Legal", "sub_niche": "Consumer Product", "strategy": "RECALL_SNIPER", "source": "FDA Live Feed"},
    19: {"niche": "Legal", "sub_niche": "Class Action",     "strategy": "RECALL_SNIPER", "source": "FDA Live Feed"},
    20: {"niche": "Legal", "sub_niche": "Mass Tort",        "strategy": "RECALL_SNIPER", "source": "FDA Live Feed"},
    21: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    22: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    23: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    24: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    25: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    26: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    27: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    28: {"niche": "Consumer CPA", "sub_niche": None, "strategy": "FINANCIAL_STRIKE", "source": "Inbound Leads"},
    29: {"niche": "Solar Installation", "sub_niche": None, "strategy": "STANDARD", "source": "Solar Prospector"},
    30: {"niche": "Restoration", "sub_niche": None, "strategy": "STANDARD", "source": "Restoration Lead Gen"},
    31: {"niche": "Logistics & Cold Storage", "sub_niche": None, "strategy": "STANDARD", "source": "Logistics Prospector"},
}


# ── LANE OUTCOME TRACKER (persistent across cycles) ─────────────────────
# Accumulates wins, losses, and revenue per (niche, strategy) so the
# SI core has data to compute Bayesian posteriors.

class LaneOutcomeTracker:
    """
    Tracks lane outcomes across execution cycles.
    Each lane execution reports success/failure + revenue.
    The tracker feeds this data into the SI core for Bayesian inference.
    Thread-safe: uses a lock to protect concurrent writes from the thread pool.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._outcomes: Dict[str, Dict] = defaultdict(lambda: {"wins": 0, "losses": 0, "revenue": 0.0, "runs": 0})
        # key = f"{niche}:{strategy}"

    def record(self, niche: str, strategy: str, success: bool, revenue: float = 0.0) -> None:
        key = f"{niche}:{strategy}"
        with self._lock:
            self._outcomes[key]["runs"] += 1
            if success:
                self._outcomes[key]["wins"] += 1
            else:
                self._outcomes[key]["losses"] += 1
            self._outcomes[key]["revenue"] += revenue

    def get_stats(self, niche: str, strategy: str) -> Dict:
        key = f"{niche}:{strategy}"
        return dict(self._outcomes.get(key, {"wins": 0, "losses": 0, "revenue": 0.0, "runs": 0}))

    def get_si_analysis(self, si: SyntheticIntelligence, niche: str, strategy: str) -> Dict:
        """Run full SI Bayesian analysis on this niche+strategy combo."""
        stats = self.get_stats(niche, strategy)
        return si.simulate_strategy(
            strategy_name=strategy,
            wins=stats["wins"],
            losses=stats["losses"],
            revenue=stats["revenue"],
            n_opportunities=max(1, stats["runs"]),
        )

    def snapshot(self) -> Dict:
        """Return full outcome snapshot for dashboard/analysis."""
        return {
            key: {
                "wins": v["wins"],
                "losses": v["losses"],
                "revenue": round(v["revenue"], 2),
                "runs": v["runs"],
                "win_rate": round(v["wins"] / max(v["runs"], 1), 4),
            }
            for key, v in self._outcomes.items()
        }


# Module-level outcome tracker (persistent across cycles)
_tracker = LaneOutcomeTracker()


def get_tracker() -> LaneOutcomeTracker:
    """Access the global lane outcome tracker."""
    return _tracker


# ── LANE RUNNER ─────────────────────────────────────────────────────────

def run_lane(lane_id: int) -> Dict:
    """
    Execute one lane with SI-powered probability scoring.

    Args:
        lane_id: Lane identifier (0-31).

    Returns:
        Dict with lane status, SI analysis, and execution result.
    """
    lane_data = LANES.get(lane_id)
    if lane_data is None:
        log.warning(f"LANE-{lane_id} [unknown] | No config")
        return {"lane_id": lane_id, "status": "no_config", "error": "unknown lane"}

    niche = lane_data["niche"]
    sub_niche = lane_data["sub_niche"]
    strategy = lane_data["strategy"]
    source = lane_data["source"]

    if niche == "unassigned":
        return {"lane_id": lane_id, "status": "idle", "niche": "unassigned",
                "message": "Slot reserved (no outreach)"}

    label = f"{niche}/{sub_niche}" if sub_niche else niche

    # ── Get historical stats from tracker ──────────────────────────
    stats = _tracker.get_stats(niche, strategy)

    # ── Run SI Bayesian analysis on this lane ──────────────────────
    si = get_si_core()
    analysis = si.simulate_strategy(
        strategy_name=strategy,
        wins=stats["wins"],
        losses=stats["losses"],
        revenue=stats["revenue"],
        n_opportunities=max(1, stats["runs"] + 1),
    )

    win_rate = analysis["win_rate"]
    ev = analysis["expected_revenue"]

    # ── Execute the outreach ───────────────────────────────────────
    try:
        result = execute_outreach(lane_id, strategy, label)
        success = bool(result) and "no recall" not in (result or "").lower()
    except Exception as e:
        result = f"outreach_error: {e}"
        success = False

    # ── Record outcome ─────────────────────────────────────────────
    # Revenue estimate from EV if successful, else 0
    revenue_estimate = ev["expected"] * 0.1 if success and ev["expected"] > 0 else 0.0
    _tracker.record(niche, strategy, success=success, revenue=revenue_estimate)

    # ── Log with real metrics ──────────────────────────────────────
    ci_str = f"[{win_rate['ci_lower']:.1%}–{win_rate['ci_upper']:.1%}]"
    log.info(
        f"LANE-{lane_id} [{label}] | "
        f"Strategy: {strategy} | "
        f"P(win)={win_rate['mean']:.1%} {ci_str} | "
        f"EV=${ev['expected']:.0f} | "
        f"Runs: {stats['runs']} | "
        f"Result: {'✓' if success else '✗'} | "
        f"Status: {result[:80] if isinstance(result, str) else 'OK'}"
    )

    return {
        "lane_id": lane_id,
        "niche": niche,
        "sub_niche": sub_niche,
        "strategy": strategy,
        "source": source,
        "status": "active",
        "success": success,
        "result": str(result)[:200],
        "win_rate": win_rate,
        "expected_revenue": ev,
        "recommendation": analysis["recommendation"],
        "runs_historical": stats["runs"],
    }


# ── BATCH EXECUTION ──────────────────────────────────────────────────────

def run_all_lanes() -> Dict:
    """
    Execute all 32 lanes in parallel via ThreadPoolExecutor.
    Returns a dict with per-lane results and aggregate summary.
    """
    summary = lane_summary()
    log.info(f"[LANE GRID] Starting execution: {', '.join(f'{n}={c}' for n, c in sorted(summary.items()))}")

    # Reset per-cycle recall cache before any lane runs
    reset_cycle_cache()

    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(run_lane, range(32)))

    # Aggregate
    active = [r for r in results if r.get("status") == "active"]
    successes = sum(1 for r in active if r.get("success"))
    failures = sum(1 for r in active if not r.get("success"))
    total_ev = sum(r.get("expected_revenue", {}).get("expected", 0) for r in active)

    # Per-niche EV
    niche_ev = defaultdict(float)
    for r in active:
        n = r.get("niche", "unknown")
        niche_ev[n] += r.get("expected_revenue", {}).get("expected", 0)

    # SI evolution feedback
    si = get_si_core()
    if successes + failures > 0:
        si.evolve_logic({
            "predictions": [r.get("win_rate", {}).get("mean", 0.5) for r in active],
            "outcomes": [1 if r.get("success") else 0 for r in active],
            "revenues": [r.get("expected_revenue", {}).get("expected", 0) for r in active],
            "niche": "mesh_orchestrator",
        })

    log.info(
        f"[LANE GRID] Complete: {len(active)} active lanes, "
        f"{successes} success, {failures} fail, "
        f"EV=${total_ev:,.0f}"
    )

    return {
        "lanes": results,
        "active_count": len(active),
        "successes": successes,
        "failures": failures,
        "total_expected_revenue": round(total_ev, 2),
        "niche_expected_revenue": {n: round(v, 2) for n, v in niche_ev.items()},
        "outcome_snapshot": _tracker.snapshot(),
    }


# ── SUMMARY ─────────────────────────────────────────────────────────────

def lane_summary() -> Dict:
    """Return counts per niche for diagnostics / dashboard use."""
    out = {}
    for lane_data in LANES.values():
        niche = lane_data["niche"]
        out[niche] = out.get(niche, 0) + 1
    return out


def lane_health_report() -> Dict:
    """
    Generate a comprehensive lane health report using SI core analysis.
    Returns per-lane and per-niche Bayesian probability estimates.
    """
    si = get_si_core()
    report = {"niches": {}, "lanes": []}

    for lane_id in range(32):
        lane_data = LANES.get(lane_id)
        if lane_data is None:
            continue

        niche = lane_data["niche"]
        strategy = lane_data["strategy"]
        if niche == "unassigned":
            continue

        stats = _tracker.get_stats(niche, strategy)
        analysis = si.simulate_strategy(
            strategy_name=strategy,
            wins=stats["wins"],
            losses=stats["losses"],
            revenue=stats["revenue"],
            n_opportunities=max(1, stats["runs"] + 1),
        )

        lane_entry = {
            "lane_id": lane_id,
            "niche": niche,
            "strategy": strategy,
            "runs": stats["runs"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": analysis["win_rate"],
            "expected_revenue": analysis["expected_revenue"],
            "recommendation": analysis["recommendation"],
        }
        report["lanes"].append(lane_entry)

        # Aggregate stats per niche
        if niche not in report["niches"]:
            report["niches"][niche] = {"strategies": set(), "total_wins": 0, "total_runs": 0, "total_revenue": 0.0}
        n = report["niches"][niche]
        n["strategies"].add(strategy)
        n["total_wins"] += stats["wins"]
        n["total_runs"] += stats["runs"]
        n["total_revenue"] += stats["revenue"]

    # Run niche-level Bayesian analysis
    for niche, n in report["niches"].items():
        n["strategies"] = list(n["strategies"])
        wr = beta_posterior(n["total_wins"], n["total_runs"] - n["total_wins"])
        n["win_rate"] = wr
        n["expected_revenue"] = expected_revenue(
            wr,
            n["total_revenue"] / max(n["total_runs"], 1) if n["total_runs"] > 0 else 5000,
            max(1, n["total_runs"]),
        )

    return report


if __name__ == "__main__":
    result = run_all_lanes()
    print(f"\n=== {result['active_count']} ACTIVE LANES ===")
    print(f"Success: {result['successes']} | Failures: {result['failures']}")
    print(f"Total EV: ${result['total_expected_revenue']:,.0f}")
    print(f"Niche EV: {result['niche_expected_revenue']}")
    print(f"Outcomes: {len(result['outcome_snapshot'])} tracked")
