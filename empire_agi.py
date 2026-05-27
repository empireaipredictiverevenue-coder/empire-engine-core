"""
EMPIRE V49 · AGI OPTIMIZER (REAL LLM)
======================================
Calls Llama 3.2 3b via empire_ai_router to suggest
weight adjustments based on real system metrics.
"""
import os
import sys
import logging

sys.path.insert(0, "/root/empire-v49")
log = logging.getLogger("empire.agi")

from supabase import create_client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
_db = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

from empire_ai_router import AIRouter

AGI_SYSTEM = """You are the AGI optimizer for an autonomous storm-driven lead-gen system.

Given current system stats, decide a new weight value between 0.5 and 2.0 that the
storm-target scorer should use.

Rules:
- HIGH revenue_pulse (>0.7) + HIGH conversion_rate (>0.03) -> increase weight slightly
- LOW proxy_health (<0.85) -> brake hard, weight to 0.5
- LOW lead_velocity (<5/hr) -> increase weight to encourage discovery
- Default weight is 1.25

Return ONLY JSON: {"new_weight": float, "reasoning": "one sentence why"}
"""


async def agi_optimize_priorities(current_stats: dict) -> dict:
    """
    Real LLM-driven weight optimization.
    Replaces the old hardcoded 1.25 return.
    """
    router = AIRouter(get_db=(lambda: _db) if _db else None)

    prompt = f"""Current system stats:
{current_stats}

Decide a new weight for the storm-target scoring engine.
Return JSON only."""

    result = await router.generate_json(
        prompt=prompt,
        task="agi.optimize",
        system=AGI_SYSTEM,
        temperature=0.2,
        max_tokens=150,
        context=current_stats,
    )

    if "_error" in result:
        log.warning(f"[agi] LLM failed: {result.get('_error')}")
        return {"new_weight": 1.25, "reasoning": "fallback (LLM unavailable)"}

    try:
        weight = float(result.get("new_weight", 1.25))
        weight = max(0.5, min(2.0, weight))
    except (TypeError, ValueError):
        weight = 1.25

    return {
        "new_weight": weight,
        "reasoning": result.get("reasoning", "no reasoning provided"),
    }
