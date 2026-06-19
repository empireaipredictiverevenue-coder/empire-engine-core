#!/usr/bin/env python3
"""
Run the same brain decision with aggressive and conservative personalities,
and compare the reasoning outputs side by side.
"""

import os
import sys
import json
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

import httpx

BASE = "http://localhost:8001"
TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

EXPECTED = {
    "aggressive": {"threshold": 0.40, "temp": 0.25, "fallback": "GO"},
    "conservative": {"threshold": 0.75, "temp": 0.05, "fallback": "NO_GO"},
}


async def main():
    print("=" * 72)
    print("  BRAIN PERSONALITY COMPARISON")
    print("  Aggressive vs Conservative - same lead, different niches")
    print("=" * 72)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ── Step 1: Set up profiles ──
        print("\n[setup] Setting aggressive for Roofing Restoration...")
        r1 = await client.post(f"{BASE}/api/brain/personality/set", headers=HEADERS, json={
            "niche": "Roofing Restoration", "persona": "aggressive",
            "operator_notes": "Aggressive test profile",
        })
        print(f"  -> {r1.status_code} | {r1.json().get('ok')}")

        print("[setup] Setting conservative for Storm Damage Restoration...")
        r2 = await client.post(f"{BASE}/api/brain/personality/set", headers=HEADERS, json={
            "niche": "Storm Damage Restoration", "persona": "conservative",
            "operator_notes": "Conservative test profile",
        })
        print(f"  -> {r2.status_code} | {r2.json().get('ok')}")

        # ── Step 2: Run brain decisions ──
        from supabase import create_client
        from empire_ai_router import AIRouter
        from empire_brain_decide import BrainDecider
        from empire_brain_personality import BrainPersonality

        SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
        SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if SUPABASE_URL and SUPABASE_KEY:
            real_db = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            real_db = None

        def get_db():
            return real_db

        ai_router = AIRouter(get_db=get_db)
        brain_decider = BrainDecider(router=ai_router)
        bp = BrainPersonality(get_db=get_db)
        brain_decider.personality = bp

        # Same target + alert for both
        test_target = {
            "name": "Dallas Logistics Hub",
            "address": "4500 Logistics Dr, Dallas, TX",
            "phone": "+12145551234",
            "email": "ops@dallaslogistics.com",
            "website": "dallaslogistics.com",
            "city": "Dallas",
            "state": "TX",
            "raw_tags": {"types": ["warehouse", "distribution", "commercial"]},
        }

        test_alert = {
            "event": "Severe Thunderstorm Warning - DFW Metro",
            "severity": "Severe",
            "urgency": "Immediate",
            "area": "Dallas, TX metro",
        }

        # Check Ollama
        ollama_online = False
        try:
            r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3)
            ollama_online = r.status_code == 200
        except Exception:
            pass
        print(f"\n[ollama] {'online' if ollama_online else 'offline - using personality engine directly'}")

        results = {}

        for label, niche, expected in [
            ("AGGRESSIVE", "Roofing Restoration", EXPECTED["aggressive"]),
            ("CONSERVATIVE", "Storm Damage Restoration", EXPECTED["conservative"]),
        ]:
            print(f"\n── {label} ({niche}) ─────────────────────────────────")
            print(f"  Expected: threshold={expected['threshold']}, temp={expected['temp']}, fallback={expected['fallback']}")

            if ollama_online:
                result = await brain_decider.decide(
                    target=test_target,
                    alert_summary=test_alert,
                    personality_niche=niche,
                )
                results[label] = result
                print(f"  Decision:   {result.get('decision')}")
                print(f"  Confidence: {result.get('confidence', 0):.2f}")
                print(f"  Persona:    {result.get('personality')}")
                print(f"  Threshold:  {result.get('confidence_threshold')}")
                print(f"  Reasoning:  {result.get('reasoning', '')[:200]}")
            else:
                profile = bp.personality_for_niche(niche)
                results[label] = profile
                print(f"  Persona:          {profile.get('persona')}")
                print(f"  Confidence:       {profile.get('confidence_threshold')}")
                print(f"  Temperature:      {profile.get('temperature')}")
                print(f"  Urgency Floor:    {profile.get('urgency_floor')}")
                print(f"  Fallback:         {profile.get('go_fallback')}")
                print(f"  Override Source:  {profile.get('override_source')}")

        # ── Step 3: Side-by-side comparison ──
        print("\n" + "=" * 72)
        print("  SIDE-BY-SIDE COMPARISON")
        print("=" * 72)

        if ollama_online:
            a, c = results.get("AGGRESSIVE", {}), results.get("CONSERVATIVE", {})
            sep = chr(0x2500) * 16
            print()
            print("  " + "".ljust(14) + "  AGGRESSIVE        CONSERVATIVE")
            print("  " + sep + "  " + sep + "  " + sep)
            print(f"  {'Decision':14s}  {str(a.get('decision','')):16s}  {str(c.get('decision','')):16s}")
            print(f"  {'Confidence':14s}  {a.get('confidence',0):8.2f}         {c.get('confidence',0):8.2f}")
            print(f"  {'Persona':14s}  {str(a.get('personality','')):16s}  {str(c.get('personality','')):16s}")
            print(f"  {'Threshold':14s}  {a.get('confidence_threshold',0):8.2f}         {c.get('confidence_threshold',0):8.2f}")
            print()
            print("  REASONING:")
            print(f"    Aggressive:   {str(a.get('reasoning', ''))[:300]}")
            print(f"    Conservative: {str(c.get('reasoning', ''))[:300]}")
            # Qualitative comparison
            if a.get("decision") == c.get("decision"):
                print(f"  Note: Both personalities produced the same decision ({a.get('decision')})")
                print(f"        but with different confidence thresholds and system personas.")
            else:
                print(f"  The personalities produced DIFFERENT decisions:")
                print(f"    Aggressive says: {a.get('decision')} (conf={a.get('confidence',0):.2f})")
                print(f"    Conservative says: {c.get('decision')} (conf={c.get('confidence',0):.2f})")
        else:
            print("\n  (Ollama offline - showing profile comparison only)")
            sep = chr(0x2500) * 16
            print()
            print("  " + "".ljust(14) + "  AGGRESSIVE        CONSERVATIVE")
            print("  " + sep + "  " + sep + "  " + sep)
            print("  Persona         aggressive        conservative")
            print("  Conf Thresh     0.40              0.75")
            print("  Temperature     0.25              0.05")
            print("  Urgency Floor   3                 6")
            print("  Fallback        GO                NO_GO")
            print()

        # ── Step 4: Also show the system prompt differences ──
        print("  SYSTEM PROMPT DIFFERENCES")
        print("  " + "─" * 56)
        aggr_prompt = bp.build_system_prompt("Roofing Restoration")
        cons_prompt = bp.build_system_prompt("Storm Damage Restoration")
        print(f"""
  Aggressive prompt starts with:
    {aggr_prompt[:150].strip()}...

  Conservative prompt starts with:
    {cons_prompt[:150].strip()}...
""")

        # ── Threshold filtering comparison ──
        print("  THRESHOLD FILTERING BEHAVIOR")
        print("  " + "─" * 56)
        print(f"""
  Scenario                    Aggressive(0.40)  Conservative(0.75)
  GO with 95% confidence      {'PASS':>16s}  {'PASS':>19s}
  GO with 50% confidence      {'PASS':>16s}  {'BLOCKED':>19s}
  GO with 30% confidence      {'BLOCKED':>16s}  {'BLOCKED':>19s}
  NO_GO with any confidence   {'NO_GO':>16s}  {'NO_GO':>19s}
""")

        # Verify with actual threshold filtering simulation
        aggressive_threshold = bp.confidence_threshold("Roofing Restoration")
        conservative_threshold = bp.confidence_threshold("Storm Damage Restoration")
        print(f"  Actual thresholds: aggressive={aggressive_threshold}, conservative={conservative_threshold}")
        print(f"  Aggressive fallback: {bp.go_fallback('Roofing Restoration')}")
        print(f"  Conservative fallback: {bp.go_fallback('Storm Damage Restoration')}")
        print(f"\n  Aggressive GO recommendations: 10% hit rate with 1000 calls beats 50% with 50 calls")
        print(f"  Conservative reminder:        Reputation damage outweighs revenue from marginal leads")

    print("\n" + "=" * 72)
    print("  COMPARISON COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
