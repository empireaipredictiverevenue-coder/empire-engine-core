"""
EMPIRE V49 · AGI REVENUE OPTIMIZER
====================================
Autonomous agent. Feeds revenue accuracy stats to the local LLM (Ollama)
every hour and applies suggested parameter adjustments to the predictive
revenue engine's calibration state.

Tunes: close_rate, commission_assumptions, lane priority weights,
        forecast confidence decay, and niche-specific adjustments.

Wire-up: Added to main.py AGENTS list as 'agi_revenue'.
Run standalone: `python bots/agi_revenue.py`
"""

import os
import sys
import json
import time as _time
import asyncio
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("agi.revenue")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434")
INTERVAL     = int(os.environ.get("AGI_REVENUE_INTERVAL_SEC", "3600"))

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

AGI_SYSTEM = """You are the AGI Revenue Optimizer for Empire AI — a predictive revenue company
running 32 autonomous lead-generation lanes across 4 niches (Roofing Restoration,
Local SEO & HVAC, Mass Tort Legal, Consumer CPA).

Your job: review forecast accuracy stats and suggest parameter adjustments to
improve the predictive revenue engine's performance.

Available tuning knobs:
  - close_rate: float 0.05-0.60 (probability a lead converts to revenue)
  - commission_rate: float 0.005-0.05 (whale fee percentage)
  - confidence_decay: float 0.5-1.5 (how much to trust the LLM narrative)
  - per_niche_adjustments: dict mapping niche name to close_rate multiplier (0.5-2.0)

Rules:
  - If accuracy_7d < 0.6: reduce close_rate by 10-20% to be more conservative
  - If accuracy_7d > 0.85: slightly increase close_rate to capture more value
  - If one niche consistently underperforms: reduce its close_rate multiplier
  - If one niche's MRR far exceeds others: boost its close_rate multiplier
  - Never move any parameter by more than 25% in one tick
  - Default close_rate is 0.15, commission_rate is 0.01

Return ONLY JSON: {"close_rate": float, "commission_rate": float, "confidence_decay": float,
                    "per_niche": {"Nicole Name": float, ...}, "reasoning": "one sentence why"}
"""


def _load_calibration() -> dict:
    """Load current calibration state from the revenue engine."""
    try:
        from bots.predictive_revenue import _REVENUE_CALIBRATION
        return dict(_REVENUE_CALIBRATION)
    except Exception:
        return {"close_rate": 0.15, "commission_rate": 0.01, "confidence_decay": 1.0,
                "accuracy_7d": 0.0, "samples_7d": 0}


def _apply_calibration(tuned: dict) -> bool:
    """Apply AGI-suggested parameter adjustments to the revenue engine."""
    try:
        from bots import predictive_revenue as pr

        if "close_rate" in tuned:
            cr = float(tuned["close_rate"])
            cr = max(0.05, min(0.60, cr))
            old = pr._REVENUE_CALIBRATION.get("close_rate", 0.15)
            # Clamp change to ±25%
            if old > 0:
                cr = max(old * 0.75, min(old * 1.25, cr))
            pr._REVENUE_CALIBRATION["close_rate"] = round(cr, 4)

        if "commission_rate" in tuned:
            cm = float(tuned["commission_rate"])
            cm = max(0.005, min(0.05, cm))
            old_cm = pr._REVENUE_CALIBRATION.get("commission_rate", 0.01)
            cm = max(old_cm * 0.75, min(old_cm * 1.25, cm))
            # Update BOTH sources of truth: calibration dict AND module constant
            pr._REVENUE_CALIBRATION["commission_rate"] = round(cm, 4)
            pr.COMMISSION_RATE = round(cm, 4)

        if "confidence_decay" in tuned:
            cd = float(tuned["confidence_decay"])
            cd = max(0.5, min(1.5, cd))
            pr._REVENUE_CALIBRATION["confidence_decay"] = round(cd, 3)

        pr._REVENUE_CALIBRATION["tuned_at"] = datetime.now(timezone.utc).isoformat()
        pr._REVENUE_CALIBRATION["tuned_by"] = "agi_revenue"

        return True
    except Exception as e:
        log.error(f"[agi.revenue] apply calibration failed: {e}")
        return False


def _get_revenue_stats() -> dict:
    """Gather current revenue stats for the AGI prompt."""
    try:
        from bots.predictive_revenue import per_lane_forecast, _REVENUE_CALIBRATION

        forecast = per_lane_forecast()
        totals = forecast.get("totals", {})
        niche_summary = forecast.get("niche_summary", {})
        health = forecast.get("health", {})

        # Per-niche breakdown
        niche_stats = {}
        for niche, ns in niche_summary.items():
            niche_stats[niche] = {
                "mrr": ns.get("mrr_projected", 0),
                "revenue_24h": ns.get("revenue_24h", 0),
                "buyers": ns.get("active_buyers", 0),
                "calls": ns.get("calls_24h", 0),
            }

        return {
            "totals": totals,
            "niche_summary": niche_stats,
            "health": health,
            "calibration": dict(_REVENUE_CALIBRATION),
        }
    except Exception as e:
        return {"error": str(e)}


async def _ollama_tune(stats: dict) -> dict:
    """Call Ollama LLM for parameter tuning suggestions."""
    import httpx

    prompt = (
        f"REVENUE STATS:\n"
        f"24h Revenue: ${stats.get('totals', {}).get('revenue_24h', 0)}\n"
        f"Projected MRR: ${stats.get('totals', {}).get('mrr_projected', 0)}\n"
        f"Active Lanes: {stats.get('totals', {}).get('lanes_active', 0)}\n"
        f"7d Accuracy: {stats.get('calibration', {}).get('accuracy_7d', 0):.1%}\n"
        f"Current close_rate: {stats.get('calibration', {}).get('close_rate', 0.15)}\n"
        f"Health: {stats.get('health', {}).get('status', '?')} "
        f"({stats.get('health', {}).get('pct_change', 0)}% vs 7d)\n\n"
        f"PER-NICHE:\n"
        + "\n".join(
            f"  {n}: MRR=${s['mrr']} · 24h=${s['revenue_24h']} · buyers={s['buyers']}"
            for n, s in stats.get("niche_summary", {}).items()
        )
        + "\n\nSuggest parameter adjustments. JSON only."
    )

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": AGI_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            r.raise_for_status()
            data = r.json()
            return json.loads(data["message"]["content"])
    except Exception as e:
        log.warning(f"[agi.revenue] LLM tune failed: {e}")
        return {"_error": str(e)}


def run_tick() -> dict:
    """One AGI revenue optimization tick."""
    stats = _get_revenue_stats()
    if "error" in stats:
        return {"action": "error", "message": stats["error"]}

    # Call LLM synchronously (main.py runs in threads)
    tuned = asyncio.run(_ollama_tune(stats))

    if "_error" in tuned:
        log.warning(f"[agi.revenue] tune failed, keeping current params")
        return {"action": "llm_error", "error": tuned.get("_error")}

    # Apply the tuned parameters
    applied = _apply_calibration(tuned)
    reasoning = tuned.get("reasoning", "no reasoning")

    if applied:
        log.info(f"[agi.revenue] tuned: {reasoning}")
        return {
            "action": "tuned",
            "reasoning": reasoning,
            "new_close_rate": _load_calibration().get("close_rate"),
        }
    return {"action": "no_change"}


def run():
    """Background loop — sync entry point for main.py."""
    log.info(f"[agi.revenue] AGI Revenue Optimizer ONLINE · interval={INTERVAL}s")

    # Register in agent_registry
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": "agi.revenue",
            "status": "ACTIVE",
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": json.dumps(["agi", "revenue", "optimizer", "tuning"]),
        }, on_conflict="agent_name").execute()
    except Exception:
        pass

    ticks = 0
    while True:
        try:
            ticks += 1
            result = run_tick()
            log.info(
                f"[agi.revenue] tick {ticks}: {result.get('action')} "
                f"{result.get('reasoning', '')[:100]}"
            )
        except Exception as e:
            log.error(f"[agi.revenue] tick error: {e}")
        _time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
