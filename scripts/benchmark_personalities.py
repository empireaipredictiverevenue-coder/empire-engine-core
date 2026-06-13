#!/usr/bin/env python3
"""
Benchmark: 10 decisions per personality via BrainDecider + Ollama.
Collects GO/NO_GO rates, average confidence, and reasoning samples.
"""
import os, sys, json, asyncio, logging, time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

logging.basicConfig(level=logging.WARNING)

from empire_brain_personality import BrainPersonality, PERSONALITY_PROFILES, VALID_PERSONAS
from empire_brain_decide import BrainDecider
from empire_ai_router import AIRouter

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    def get_db():
        return db
else:
    class MockTable:
        def select(self, *c): return self
        def eq(self, c, v): return self
        def order(self, c, **kw): return self
        def limit(self, n): return self
        def execute(self): return type("obj",(object,),{"data":[]})()
    class MockDb:
        def table(self, n): return MockTable()
    def get_db():
        return MockDb()

# ── Test targets with varying parameters to get diverse results ──
TEST_TARGETS = [
    {
        "name": "Dallas Logistics Hub",
        "address": "4500 Logistics Dr, Dallas, TX",
        "phone": "+12145551234",
        "email": "ops@dallaslogistics.com",
        "website": "dallaslogistics.com",
        "city": "Dallas", "state": "TX",
        "raw_tags": {"types": ["warehouse", "distribution"], "niche": "Warehouse & Distribution"},
    },
    {
        "name": "Small Auto Repair Shop",
        "address": "1200 Main St, Austin, TX",
        "phone": "+15125552345",
        "website": "",
        "city": "Austin", "state": "TX",
        "raw_tags": {"types": ["auto", "retail"], "niche": "Automotive Services"},
    },
    {
        "name": "Abandoned Warehouse",
        "address": "8900 Industrial Blvd, Houston, TX",
        "phone": "",
        "email": "",
        "website": "",
        "city": "Houston", "state": "TX",
        "raw_tags": {"types": ["warehouse", "vacant"], "niche": "Warehouse & Distribution"},
    },
    {
        "name": "Highrise Office Tower",
        "address": "100 Commerce St, Dallas, TX",
        "phone": "+12145559876",
        "email": "leasing@tower.com",
        "website": "towertx.com",
        "city": "Dallas", "state": "TX",
        "raw_tags": {"types": ["office", "commercial"], "niche": "Commercial Real Estate"},
    },
    {
        "name": "Residential Home",
        "address": "42 Elm St, Austin, TX",
        "phone": "+15125559876",
        "email": "homeowner@email.com",
        "city": "Austin", "state": "TX",
        "raw_tags": {"types": ["residential", "single-family"], "niche": "Residential Property"},
    },
    {
        "name": "Shopping Mall",
        "address": "1 Mall Way, San Antonio, TX",
        "phone": "+12105553456",
        "website": "mallofsa.com",
        "city": "San Antonio", "state": "TX",
        "raw_tags": {"types": ["retail", "commercial"], "niche": "Retail & Hospitality"},
    },
    {
        "name": "Manufacturing Plant",
        "address": "500 Factory Rd, Fort Worth, TX",
        "phone": "+18175556789",
        "email": "ops@plant.com",
        "city": "Fort Worth", "state": "TX",
        "raw_tags": {"types": ["manufacturing", "industrial"], "niche": "Manufacturing"},
    },
    {
        "name": "Apartment Complex",
        "address": "2000 Oak Ave, Houston, TX",
        "phone": "+17135554567",
        "website": "oakapartments.com",
        "city": "Houston", "state": "TX",
        "raw_tags": {"types": ["residential", "multi-family"], "niche": "Multi-Family Housing"},
    },
    {
        "name": "Construction Site Trailer",
        "address": "3000 Development Dr, Austin, TX",
        "phone": "+15125552345",
        "city": "Austin", "state": "TX",
        "raw_tags": {"types": ["construction", "temporary"], "niche": "Construction & Development"},
    },
    {
        "name": "Data Center",
        "address": "8000 Tech Park, Plano, TX",
        "phone": "+19725553456",
        "email": "ops@datacenter.com",
        "website": "datacenterplano.com",
        "city": "Plano", "state": "TX",
        "raw_tags": {"types": ["data-center", "commercial"], "niche": "Technology Infrastructure"},
    },
]

# ── Alerts with varying severity ──
TEST_ALERTS = [
    {"event": "Severe Thunderstorm Warning — DFW Metro", "severity": "Severe", "urgency": "Immediate", "area": "Dallas, TX metro"},
    {"event": "Tornado Watch — Austin area", "severity": "Moderate", "urgency": "Expected", "area": "Austin, TX"},
    {"event": "Minor Hail — San Antonio", "severity": "Minor", "urgency": "Past", "area": "San Antonio, TX"},
    {"event": "Extreme Hurricane — Gulf Coast", "severity": "Extreme", "urgency": "Immediate", "area": "Houston/Galveston"},
    {"event": "Flash Flood Warning — Fort Worth", "severity": "Severe", "urgency": "Immediate", "area": "Fort Worth, TX"},
    {"event": "Winter Storm — North Texas", "severity": "Moderate", "urgency": "Expected", "area": "Plano/Frisco, TX"},
    {"event": "Heat Advisory — statewide", "severity": "Minor", "urgency": "Past", "area": "All Texas"},
    {"event": "Damaging Winds — DFW", "severity": "Severe", "urgency": "Immediate", "area": "Dallas/Fort Worth"},
    {"event": "Derecho — I-35 corridor", "severity": "Extreme", "urgency": "Immediate", "area": "Austin to Dallas"},
    {"event": "Lightning Storm — Central TX", "severity": "Moderate", "urgency": "Expected", "area": "Central Texas"},
]

# Map personalities to niches for override resolution
PERSONA_NICHE_MAP = {
    "aggressive": "Roofing Restoration",
    "conservative": "Storm Damage Restoration",
    "balanced": "Warehouse & Distribution",
}


async def run_personality_batch(bp: BrainPersonality, brain_decider: BrainDecider,
                                 persona: str, niche: str, num_runs: int = 10) -> dict:
    """Run N decisions with a given personality and collect stats."""
    decisions = []
    reasoning_samples = []
    times = []

    print(f"\n  ── Running {num_runs} decisions as {persona.upper()} ──")

    for i in range(num_runs):
        target = TEST_TARGETS[i % len(TEST_TARGETS)]
        alert = TEST_ALERTS[i % len(TEST_ALERTS)]

        t0 = time.time()
        try:
            result = await brain_decider.decide(
                target=target,
                alert_summary=alert,
                personality_niche=niche,
            )
            elapsed = time.time() - t0
            times.append(elapsed)

            decision = result.get("decision", "NO_GO")
            confidence = result.get("confidence", 0.0)
            reasoning = result.get("reasoning", "")
            personality = result.get("personality", persona)

            decisions.append({"decision": decision, "confidence": confidence})
            if len(reasoning_samples) < 3 and reasoning:
                reasoning_samples.append({
                    "run": i + 1,
                    "target": target["name"],
                    "alert": alert["event"],
                    "decision": decision,
                    "confidence": round(confidence, 3),
                    "reasoning": reasoning[:120],
                    "personality": personality,
                    "elapsed": round(elapsed, 2),
                })

            print(f"    Run {i+1:2d}: {decision:5s}  conf={confidence:.3f}  "
                  f"({target['name'][:25]:25s} | {alert['severity']:8s})  "
                  f"[{elapsed:.1f}s]")

        except Exception as e:
            print(f"    Run {i+1:2d}: ERROR — {e}")
            decisions.append({"decision": "ERROR", "confidence": 0.0})

    # Stats
    go_count = sum(1 for d in decisions if d["decision"] == "GO")
    no_go_count = sum(1 for d in decisions if d["decision"] == "NO_GO")
    error_count = sum(1 for d in decisions if d["decision"] == "ERROR")
    confidences = [d["confidence"] for d in decisions if d["confidence"] > 0]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    avg_time = sum(times) / len(times) if times else 0.0

    return {
        "persona": persona,
        "niche": niche,
        "total": num_runs,
        "go": go_count,
        "no_go": no_go_count,
        "errors": error_count,
        "go_rate": round(go_count / num_runs * 100, 1),
        "avg_confidence": round(avg_conf, 3),
        "avg_time": round(avg_time, 2),
        "threshold": PERSONALITY_PROFILES[persona]["confidence_threshold"],
        "go_fallback": PERSONALITY_PROFILES[persona]["go_fallback"],
        "samples": reasoning_samples,
    }


async def main():
    print("=" * 72)
    print("  BRAIN PERSONALITY BENCHMARK — 10 decisions per persona")
    print("=" * 72)
    print(f"  Ollama model: llama3.2:3b")
    print(f"  Targets: {len(TEST_TARGETS)} unique · Alerts: {len(TEST_ALERTS)} unique")
    print()

    # Setup
    bp = BrainPersonality(get_db=get_db, default_persona="balanced")
    ai_router = AIRouter(get_db=get_db)
    brain_decider = BrainDecider(router=ai_router)
    brain_decider.personality = bp

    # Run all three personas
    results = {}
    for persona in ["aggressive", "conservative", "balanced"]:
        niche = PERSONA_NICHE_MAP[persona]
        results[persona] = await run_personality_batch(
            bp, brain_decider, persona, niche, num_runs=10
        )
        print()

    # ── Summary Table ──
    print("=" * 72)
    print("  RESULTS SUMMARY")
    print("=" * 72)
    print(f"  {'Persona':<16} {'GO':>4} {'NO_GO':>6} {'Err':>4} "
          f"{'GO%':>6} {'Avg Conf':>9} {'Threshold':>10} {'Fallback':>9} {'Avg T':>6}")
    print(f"  {'─'*16} {'─'*4} {'─'*6} {'─'*4} {'─'*6} {'─'*9} {'─'*10} {'─'*9} {'─'*6}")
    for persona in ["aggressive", "conservative", "balanced"]:
        r = results[persona]
        print(f"  {r['persona']:<16} {r['go']:>4} {r['no_go']:>6} {r['errors']:>4} "
              f"{r['go_rate']:>5.1f}% {r['avg_confidence']:>8.3f} "
              f"{r['threshold']:>9.2f}  {r['go_fallback']:>8} {r['avg_time']:>5.1f}s")

    # ── Side-by-side reasoning samples ──
    print()
    print("=" * 72)
    print("  SAMPLE REASONING (first 3 runs per personality)")
    print("=" * 72)
    for i in range(3):
        print(f"\n  ── Run {i+1} ──")
        for persona in ["aggressive", "conservative", "balanced"]:
            r = results[persona]
            if i < len(r["samples"]):
                s = r["samples"][i]
                print(f"  [{persona:<14}] {s['decision']:5s} conf={s['confidence']:.3f}  "
                      f"({s['target'][:20]:20s})")
                print(f"                   {s['reasoning'][:120]}")
            else:
                print(f"  [{persona:<14}] (no sample)")

    # ── Key insights ──
    print()
    print("=" * 72)
    print("  KEY INSIGHTS")
    print("=" * 72)

    agg = results["aggressive"]
    cons = results["conservative"]
    bal = results["balanced"]

    print(f"  • Aggressive GO rate:   {agg['go_rate']}%  vs  Conservative GO rate: {cons['go_rate']}%")
    print(f"  • Aggressive avg conf:  {agg['avg_confidence']}  vs  Conservative avg conf: {cons['avg_confidence']}")
    print(f"  • Balanced GO rate:     {bal['go_rate']}%  (baseline)")
    print(f"  • Aggressive threshold: {agg['threshold']}  vs  Conservative threshold: {cons['threshold']}")
    print(f"  • Personality differentiation: {'✅ CONFIRMED' if agg['go_rate'] != cons['go_rate'] else '⚠️ Same rate'}")

    # Statistical significant difference?
    go_diff = abs(agg["go_rate"] - cons["go_rate"])
    conf_diff = abs(agg["avg_confidence"] - cons["avg_confidence"])
    if go_diff >= 10:
        print(f"  • GO rate delta: {go_diff}% — meaningful personality effect")
    elif go_diff > 0:
        print(f"  • GO rate delta: {go_diff}% — modest personality effect")
    else:
        print(f"  • GO rate delta: 0% — no difference (more runs needed)")

    print()
    print("  Done! ✅")

    return results


if __name__ == "__main__":
    results = asyncio.run(main())
    # Save to JSON for later analysis
    with open("/tmp/personality_benchmark.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull results saved to /tmp/personality_benchmark.json")
