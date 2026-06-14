"""
EMPIRE V49 · AGENT INTERFACE (lane -> outreach execution)
=========================================================
Maps a 32-lane id to the live agent outreach for that lane. Called
from mesh_orchestrator.py.

For lanes 16-20 (Legal sub-niches), the per-lane device is determined
by the recall_classifier: each sub_niche gets the recall that matches
its product_type. Lanes 0-15, 21-28 use the standard bot_manager
campaign (the legacy path). Lanes 29-31 are assigned to Solar Installation, Restoration, and Logistics &
Cold Storage respectively.

Patched 2026-06-12 (step 3 + 4 of mass-tort lane-sort plan):
  - Use recall_classifier (drugs/devices/food) instead of single
    device/enforcement endpoint.
  - Match each legal lane to the recall that maps to its sub_niche,
    so the orchestrator log shows the right device per lane (e.g.
    lane 16/Pharma Liability sees the drugs recall, not the device
    recall).
  - Cache the per-cycle classified recalls in a module-level dict so
    each lane run is consistent within one orchestrator cycle.
  - Cap cache to 1 cycle to avoid stale data across re-runs.
"""

import sys

# bot_manager lives in bots/, mass_tort_scout and recall_classifier
# live in bots/ too. Add the bots/ dir to sys.path BEFORE the
# classifier import so bot_manager resolves first.
sys.path.append('/root/empire-v49/bots')

from bot_manager import BotManager

# Lazy import so a missing classifier doesn't kill agent_interface.
try:
    from bots.recall_classifier import fetch_one_per_sub_niche
except ImportError:
    sys.path.insert(0, "/root/empire-v49")
    from bots.recall_classifier import fetch_one_per_sub_niche


# ── LEGAL LANE MAPPING ──────────────────────────────────────────────────
# Lane id -> sub_niche label. Mirrors mesh_orchestrator.LANES but
# kept in a flat dict for fast lookup here.
LEGAL_LANE_TO_SUB_NICHE = {
    16: "Pharma Liability",
    17: "Medical Device",
    18: "Consumer Product",
    19: "Class Action",
    20: "Mass Tort",
}


# ── RECALL CACHE (per cycle) ────────────────────────────────────────────
_cycle_cache = {}


def _get_recall_for_sub_niche(sub_niche: str) -> dict | None:
    """
    Return the recall that the classifier mapped to this sub_niche.
    Cached for the lifetime of one process so 5 lane runs in the
    same cycle all see the same FDA snapshot.
    """
    if not _cycle_cache:
        for r in fetch_one_per_sub_niche():
            _cycle_cache[r["sub_niche"]] = r
    return _cycle_cache.get(sub_niche)


def reset_cycle_cache():
    """Clear the per-cycle recall cache. Call at the top of a new cycle."""
    _cycle_cache.clear()


# ── MAIN ENTRY POINT ────────────────────────────────────────────────────
def execute_outreach(lane_id, strategy, niche_name):
    """
    Execute outreach for one lane.

    lane_id: int (0-31)
    strategy: str (e.g. "RECALL_SNIPER")
    niche_name: str (e.g. "Roofing Restoration" or "Legal/Pharma Liability")
    """
    manager = BotManager("LI-SNIPER-01")

    # ── Legal sub-niche lanes (16-20) ───────────────────────────────────
    if lane_id in LEGAL_LANE_TO_SUB_NICHE:
        expected_sub_niche = LEGAL_LANE_TO_SUB_NICHE[lane_id]
        recall = _get_recall_for_sub_niche(expected_sub_niche)

        if recall is None:
            # No recall mapped to this sub_niche this cycle. The bridge
            # will also have nothing to dial. Log honestly.
            print(f"[LANE {lane_id}] LEGAL/{expected_sub_niche} | "
                  f"Strategy: {strategy} | "
                  f"No recall matched this sub_niche this cycle.")
            return f"No recall for {expected_sub_niche} this cycle."

        device = recall.get("product_description", "Unknown device")
        reason = recall.get("reason_for_recall", "Product Defect")
        product_type = recall.get("product_type", "Unknown")
        classification = recall.get("classification", "Unknown")

        print(f"[LANE {lane_id}] {niche_name} | Strategy: {strategy}")
        print(f"[TARGET] {product_type} {classification} - {device}")
        print(f"[TRIGGER] {reason[:120]}")
        return f"{niche_name} campaign live for {device[:80]}."

    # ── Unassigned lanes (29-31) ────────────────────────────────────────
    if niche_name == "unassigned":
        return "Lane slot reserved (no outreach)."

    # ── All other lanes (0-15, 21-28) ───────────────────────────────────
    print(f"[LANE {lane_id}] Running standard campaign for: {niche_name} | "
          f"Strategy: {strategy}")
    return "Standard campaign active."


if __name__ == "__main__":
    # Quick internal sanity check
    execute_outreach(16, "RECALL_SNIPER", "Legal/Pharma Liability")
