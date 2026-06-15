"""
EMPIRE V49 · 36-LANE MESH ORCHESTRATOR (SI-Powered)
=====================================================
Defines the 36-lane lead generation grid (expanded from 32). Each lane executes via
the agent_interface and scores its outcomes using the SI core's
Bayesian probabilistic inference engine.

Replaces fake "88% probability" strings with real beta-binomial
win rate estimates, Thompson sampling for strategy selection, and
lane health scoring with confidence intervals.

Niche allocation (expanded to 36 — 2026-06-14):
  Lanes  0- 4 : Roofing Restoration  (5 lanes, AGGRESSIVE_STRIKE, Storm Scout)
  Lanes  5- 6 : HVAC                 (2 lanes, UGLY_BANNER, Web Auditor)
  Lanes  7- 9 : SEO                  (3 lanes, STANDARD, SEO Optimizer)
                  7: Local SEO  |  8: E-commerce SEO  |  9: Technical SEO
  Lanes 10-14 : Legal                (5 lanes, RECALL_SNIPER, FDA Live Feed)
  Lanes 15-17 : Insurance            (3 lanes, INSURANCE_STRIKE, Insurance Lead Gen)
  Lanes 18-19 : Financial Services   (2 lanes, FINANCIAL_STRIKE, Financial Lead Gen)
  Lanes 20-21 : Consumer CPA         (2 lanes, FINANCIAL_STRIKE, Inbound Leads)
  Lanes 22-23 : Senior Care          (2 lanes, SENIOR_STRIKE, Senior Lead Gen)
  Lanes 24    : Addiction Treatment  (1 lane,  HEALTH_STRIKE, Healthcare Lead Gen)
  Lanes 25-26 : Education            (2 lanes, STANDARD, Edu Lead Gen)
  Lanes 27-28 : Healthcare           (2 lanes, HEALTH_STRIKE, Healthcare Lead Gen)
  Lanes 29-31 : Business Services    (3 lanes, BIZ_STRIKE, B2B Lead Gen)
  Lanes 32    : Financial Services   (1 lane,  FINANCIAL_STRIKE, Financial Lead Gen)  ← NEW — Mortgage Refinance
  Lanes 33    : Financial Services   (1 lane,  FINANCIAL_STRIKE, Financial Lead Gen)  ← NEW — Debt Settlement
  Lanes 34    : Home Services        (1 lane,  AGGRESSIVE_STRIKE, Storm Scout)        ← NEW — Solar Installation
  Lanes 35    : Home Services        (1 lane,  UGLY_BANNER, Web Auditor)             ← NEW — Plumbing
  Lanes 36    : Commercial Roofing    (1 lane,  AGGRESSIVE_STRIKE, Storm Scout)        ← NEW — Commercial Roofing
  Lanes 37    : Commercial Solar      (1 lane,  AGGRESSIVE_STRIKE, Storm Scout)        ← NEW — Commercial Solar
  Lanes 38    : Debt Relief           (1 lane,  FINANCIAL_STRIKE, Financial Lead Gen)  ← NEW — Debt Relief
  Lanes 32-35 added 2026-06-14 based on CPL benchmark analysis: these 4 sub-niches
  were the highest-value uncovered verticals (Mortgage Refinance $250-600, Debt
  Settlement $100-300, Solar Installation $100-300, Plumbing $57-183).
  Lanes 36-38 added 2026-06-15: Commercial Roofing, Commercial Solar, Debt Relief.
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
    0:  {"niche": "Roofing Restoration", "sub_niche": None,              "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    1:  {"niche": "Roofing Restoration", "sub_niche": None,              "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    2:  {"niche": "Roofing Restoration", "sub_niche": None,              "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    3:  {"niche": "Roofing Restoration", "sub_niche": None,              "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    4:  {"niche": "Roofing Restoration", "sub_niche": None,              "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    5:  {"niche": "HVAC",                "sub_niche": None,              "strategy": "UGLY_BANNER",      "source": "Web Auditor"},
    6:  {"niche": "HVAC",                "sub_niche": None,              "strategy": "UGLY_BANNER",      "source": "Web Auditor"},
    7:  {"niche": "SEO",                 "sub_niche": "Local SEO",       "strategy": "STANDARD",         "source": "SEO Optimizer"},
    8:  {"niche": "SEO",                 "sub_niche": "E-commerce SEO",  "strategy": "STANDARD",         "source": "SEO Optimizer"},
    9:  {"niche": "SEO",                 "sub_niche": "Technical SEO",   "strategy": "STANDARD",         "source": "SEO Optimizer"},
    10: {"niche": "Legal",               "sub_niche": "Pharma Liability","strategy": "RECALL_SNIPER",   "source": "FDA Live Feed"},
    11: {"niche": "Legal",               "sub_niche": "Medical Device",  "strategy": "RECALL_SNIPER",   "source": "FDA Live Feed"},
    12: {"niche": "Legal",               "sub_niche": "Consumer Product","strategy": "RECALL_SNIPER",   "source": "FDA Live Feed"},
    13: {"niche": "Legal",               "sub_niche": "Class Action",    "strategy": "RECALL_SNIPER",   "source": "FDA Live Feed"},
    14: {"niche": "Legal",               "sub_niche": "Mass Tort",       "strategy": "RECALL_SNIPER",   "source": "FDA Live Feed"},
    15: {"niche": "Insurance",           "sub_niche": "Medicare",        "strategy": "INSURANCE_STRIKE","source": "Insurance Lead Gen"},
    16: {"niche": "Insurance",           "sub_niche": "Life Insurance",  "strategy": "INSURANCE_STRIKE","source": "Insurance Lead Gen"},
    17: {"niche": "Insurance",           "sub_niche": "Final Expense",   "strategy": "INSURANCE_STRIKE","source": "Insurance Lead Gen"},
    18: {"niche": "Financial Services",  "sub_niche": "Debt Consolidation","strategy": "FINANCIAL_STRIKE","source": "Financial Lead Gen"},
    19: {"niche": "Financial Services",  "sub_niche": "Mortgage",        "strategy": "FINANCIAL_STRIKE","source": "Financial Lead Gen"},
    20: {"niche": "Consumer CPA",        "sub_niche": None,              "strategy": "FINANCIAL_STRIKE","source": "Inbound Leads"},
    21: {"niche": "Consumer CPA",        "sub_niche": None,              "strategy": "FINANCIAL_STRIKE","source": "Inbound Leads"},
    22: {"niche": "Senior Care",         "sub_niche": "Assisted Living", "strategy": "SENIOR_STRIKE",   "source": "Senior Lead Gen"},
    23: {"niche": "Senior Care",         "sub_niche": "Home Health",     "strategy": "SENIOR_STRIKE",   "source": "Senior Lead Gen"},
    24: {"niche": "Addiction Treatment",  "sub_niche": None,              "strategy": "HEALTH_STRIKE",   "source": "Healthcare Lead Gen"},
    25: {"niche": "Education",           "sub_niche": "CDL/Trade School","strategy": "STANDARD",         "source": "Edu Lead Gen"},
    26: {"niche": "Education",           "sub_niche": "Nursing",         "strategy": "STANDARD",         "source": "Edu Lead Gen"},
    27: {"niche": "Healthcare",          "sub_niche": "Medical Alert Systems","strategy": "HEALTH_STRIKE","source": "Healthcare Lead Gen"},
    28: {"niche": "Healthcare",          "sub_niche": "Mental Health",   "strategy": "HEALTH_STRIKE",   "source": "Healthcare Lead Gen"},
    29: {"niche": "Business Services",   "sub_niche": "Managed IT","strategy": "BIZ_STRIKE","source": "B2B Lead Gen"},
    30: {"niche": "Business Services",   "sub_niche": "Merchant Services","strategy": "BIZ_STRIKE","source": "B2B Lead Gen"},
    31: {"niche": "Business Services",   "sub_niche": "HR & Staffing",  "strategy": "BIZ_STRIKE",      "source": "B2B Lead Gen"},
    32: {"niche": "Financial Services",  "sub_niche": "Mortgage Refinance","strategy": "FINANCIAL_STRIKE","source": "Financial Lead Gen"},
    33: {"niche": "Financial Services",  "sub_niche": "Debt Settlement",   "strategy": "FINANCIAL_STRIKE","source": "Financial Lead Gen"},
    34: {"niche": "Home Services",       "sub_niche": "Solar Installation","strategy": "AGGRESSIVE_STRIKE","source": "Storm Scout"},
    35: {"niche": "Home Services",       "sub_niche": "Plumbing",          "strategy": "UGLY_BANNER",      "source": "Web Auditor"},
    36: {"niche": "Commercial Roofing",    "sub_niche": "Commercial Roofing", "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    37: {"niche": "Commercial Solar",      "sub_niche": "Commercial Solar",   "strategy": "AGGRESSIVE_STRIKE", "source": "Storm Scout"},
    38: {"niche": "Debt Relief",           "sub_niche": "Debt Relief",        "strategy": "FINANCIAL_STRIKE",  "source": "Financial Lead Gen"},
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
        lane_id: Lane identifier (0-35).

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
    Execute all 36 lanes in parallel via ThreadPoolExecutor.
    Returns a dict with per-lane results and aggregate summary.
    """
    summary = lane_summary()
    log.info(f"[LANE GRID] Starting execution: {', '.join(f'{n}={c}' for n, c in sorted(summary.items()))}")

    # Reset per-cycle recall cache before any lane runs
    reset_cycle_cache()

    with concurrent.futures.ThreadPoolExecutor(max_workers=39) as executor:
        results = list(executor.map(run_lane, range(39)))

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

    for lane_id in range(39):
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
