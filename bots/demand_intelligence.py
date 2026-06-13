"""
EMPIRE V49 - DEMAND INTELLIGENCE AGENT
======================================
Lane-agnostic predictive demand engine. Predicts WHERE and WHEN demand
concentrates per lane, so traffic can be aimed at it (homeowners find US,
legal + consented). Proven on Wichita roofing (lane 1), built for 32 lanes.

Flow: trigger signal (per lane) -> score geographies -> timing model ->
llama3.2:3b reasons -> ranked "deploy traffic HERE NOW" targets.
"""
import os, sys, asyncio, logging
from datetime import datetime, timezone
sys.path.insert(0, "/root/empire-v49")
from dotenv import load_dotenv
load_dotenv("/root/.env")
log = logging.getLogger("empire.demand")

# ---- LANE CONFIG: the thing that makes this scale to 32 lanes ----
# Each lane = a config. Add lanes 2..32 by adding entries, not rewriting code.
LANES = {
    "roofing": {
        "lane_id": 1,
        "niche": "roofing",
        "trigger": "storm",          # what creates demand
        "timing_hours": (24, 72),    # demand-anxiety peaks 24-72h post-trigger
        "demand_keywords": ["roof repair", "storm damage roof", "roof leak", "hail damage"],
        "min_risk_rank": 4,          # Slight or higher
    },
    # lane 2..32 go here later, same shape, different trigger/keywords
}

def get_trigger_signal(lane):
    """Pull the demand trigger for this lane. Roofing -> storm_predictor."""
    if lane["trigger"] == "storm":
        from bots import storm_predictor
        forecasts = storm_predictor.assess()
        # keep only metros at/above this lane threshold
        return [f for f in forecasts if f.get("risk_rank",0) >= lane["min_risk_rank"]]
    log.warning(f"No trigger source wired for: {lane['trigger']}")
    return []

def score_geographies(lane, signals):
    """Score each triggered geography by demand concentration."""
    scored = []
    for s in signals:
        # demand score = storm risk rank (higher rank = more damage = more demand)
        # later: multiply by property density, population, etc.
        score = s.get("risk_rank", 0) * 20  # 0-100ish
        scored.append({
            "metro": s["metro"], "lat": s["lat"], "lon": s["lon"],
            "risk_level": s.get("risk_level"), "day": s.get("day"),
            "demand_score": min(score, 100),
        })
    scored.sort(key=lambda x: x["demand_score"], reverse=True)
    return scored

async def brain_rank(lane, scored):
    """llama3.2:3b reasons over scored geographies -> deploy recommendation."""
    if not scored:
        return {"deploy": [], "reasoning": "no triggered demand right now"}
    try:
        from empire_ai_router import AIRouter
        from supabase import create_client
        db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
        router = AIRouter(get_db=lambda: db)
        system = (
            "You are the Demand Intelligence brain for the Empire AI autonomous revenue "
            "engine. Given scored geographies where demand was triggered, decide "
            "where to deploy paid + organic traffic and when. Consider: higher demand_score "
            "= deploy harder; demand peaks 24-72h after the trigger. "
            "Return ONLY JSON: {\"deploy\": [list of metro names ranked], "
            "\"reasoning\": \"one sentence\", \"confidence\": float 0-1}"
        )
        prompt = f"Lane: {lane['niche']}. Timing peak: {lane['timing_hours']}h post-trigger.\nScored geographies:\n{scored}\nDecide deployment. JSON only."
        result = await router.generate_json(prompt=prompt, task="demand.rank", system=system, temperature=0.2, max_tokens=200, context={"scored": scored})
        if "_error" in result:
            return {"deploy": [g["metro"] for g in scored], "reasoning": "fallback: brain unavailable, using raw score order", "confidence": 0.5}
        return result
    except Exception as e:
        log.error(f"[demand] brain error: {e}")
        return {"deploy": [g["metro"] for g in scored], "reasoning": f"fallback ({str(e)[:50]})", "confidence": 0.5}

async def run_lane(lane_key="roofing"):
    """Run the demand intelligence cycle for one lane."""
    lane = LANES.get(lane_key)
    if not lane:
        print(f"No lane config: {lane_key}"); return None
    print(f"=== DEMAND INTELLIGENCE: {lane_key} (lane {lane['lane_id']}) ===")
    signals = get_trigger_signal(lane)
    print(f"Trigger signals: {len(signals)} geographies triggered")
    scored = score_geographies(lane, signals)
    for s in scored:
        print(f"  {s['metro']}: demand {s['demand_score']} ({s['risk_level']}, day {s['day']})")
    decision = await brain_rank(lane, scored)
    print(f"\nDEPLOY: {decision.get('deploy')}")
    print(f"WHY: {decision.get('reasoning')}")
    print(f"CONFIDENCE: {decision.get('confidence', 'n/a')}")
    return {"lane": lane_key, "scored": scored, "decision": decision}

if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "roofing"
    asyncio.run(run_lane(key))