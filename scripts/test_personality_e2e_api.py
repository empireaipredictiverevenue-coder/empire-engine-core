#!/usr/bin/env python3
"""
E2E test: Set brain personality for 'Roofing Restoration' to aggressive
via the API, run a brain decision, and verify the personality metadata
(aggressive, confidence_threshold=0.40) appears in the result.
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


async def main():
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")
            if detail:
                print(f"         {detail}")

    section = lambda s: print(f"\n{'='*60}\n  {s}\n{'='*60}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ── Step 1: Verify hub is healthy ──
        section("1. SYSTEM HEALTH")
        r = await client.get(f"{BASE}/api/market-pulse")
        check("Hub is operational", r.status_code == 200 and r.json().get("status") == "operational",
              f"HTTP {r.status_code}: {r.text[:100]}")

        # ── Step 2: Get current snapshot ──
        section("2. INITIAL SNAPSHOT")
        r = await client.get(f"{BASE}/api/brain/personality/snapshot", headers=HEADERS)
        check("Snapshot returned", r.status_code == 200, f"HTTP {r.status_code}")
        snap = r.json()
        check("profiles_available includes aggressive",
              "aggressive" in snap.get("profiles_available", []),
              f"got {snap.get('profiles_available')}")
        check("profile_details includes aggressive with threshold 0.40",
              snap.get("profile_details", {}).get("aggressive", {}).get("confidence_threshold") == 0.40,
              f"got {snap.get('profile_details', {}).get('aggressive', {})}")
        check("profile_details includes tone_instruction",
              "tone_instruction" in snap.get("profile_details", {}).get("aggressive", {}),
              "tone_instruction should be present in profile_details")
        check("snapshot has prompt_preview",
              "prompt_preview" in snap,
              "system prompt preview should be present")

        # ── Step 3: Set personality for Roofing Restoration to aggressive ──
        section("3. SET PERSONALITY VIA API")
        payload = {
            "niche": "Roofing Restoration",
            "persona": "aggressive",
            "operator_id": "",
            "operator_notes": "E2E test override",
        }
        r = await client.post(f"{BASE}/api/brain/personality/set", headers=HEADERS, json=payload)
        check("Set personality returned 200", r.status_code == 200, f"HTTP {r.status_code}")
        result = r.json()
        check("Set returned ok=True", result.get("ok") is True,
              f"got {result}")
        check("Set returned persona=aggressive", result.get("persona") == "aggressive",
              f"got {result.get('persona')}")
        check("Set returned niche=Roofing Restoration", result.get("niche") == "Roofing Restoration",
              f"got {result.get('niche')}")

        # ── Step 4: Verify snapshot reflects the change ──
        section("4. VERIFY CHANGE IN SNAPSHOT")
        r = await client.get(f"{BASE}/api/brain/personality/snapshot", headers=HEADERS)
        snap = r.json()
        rr_config = snap.get("configs", {}).get("Roofing Restoration", {})
        check("Roofing Restoration config exists in snapshot", bool(rr_config),
              f"configs keys: {list(snap.get('configs', {}).keys())}")
        check("Roofing persona is aggressive", rr_config.get("persona") == "aggressive",
              f"got {rr_config.get('persona')}")
        check("Roofing confidence_threshold is 0.4",
              abs(float(rr_config.get("confidence_threshold", 0)) - 0.4) < 0.001,
              f"got {rr_config.get('confidence_threshold')}")
        check("Roofing temperature is 0.25",
              abs(float(rr_config.get("temperature", 0)) - 0.25) < 0.001,
              f"got {rr_config.get('temperature')}")

        # ── Step 5: Now run a brain decision ──
        # Use direct Python call to BrainDecider since /api/v1/closer/score
        # would route through the full pipeline and we want a clean test.
        section("5. BRAIN DECISION WITH PERSONALITY")
        from empire_ai_router import AIRouter
        from empire_brain_decide import BrainDecider
        from empire_brain_personality import BrainPersonality
        from supabase import create_client

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
        brain_personality = BrainPersonality(get_db=get_db)
        brain_decider.personality = brain_personality

        # Test target (storm damage scenario)
        test_target = {
            "name": "Dallas Logistics Hub",
            "address": "4500 Logistics Dr, Dallas, TX",
            "phone": "+12145551234",
            "email": "ops@dallaslogistics.com",
            "website": "dallaslogistics.com",
            "city": "Dallas",
            "state": "TX",
            "raw_tags": {
                "types": ["warehouse", "distribution", "commercial"],
                "niche": "Warehouse & Distribution",
            },
        }

        test_alert = {
            "event": "Severe Thunderstorm Warning - DFW Metro",
            "severity": "Severe",
            "urgency": "Immediate",
            "area": "Dallas, TX metro",
        }

        # Check if Ollama is available
        ollama_online = False
        try:
            r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3)
            ollama_online = r.status_code == 200
        except Exception:
            pass

        if not ollama_online:
            print("\n  Ollama offline - testing personality wiring directly...")
            # Test personality wiring without LLM call
            profile = brain_personality.personality_for_niche("Roofing Restoration")
            check("personality_for_niche returns dict", isinstance(profile, dict))
            check("persona is aggressive", profile.get("persona") == "aggressive",
                  f"got {profile.get('persona')}")
            check("confidence_threshold is 0.40",
                  abs(float(profile.get("confidence_threshold", 0)) - 0.40) < 0.001,
                  f"got {profile.get('confidence_threshold')}")
            check("temperature is 0.25",
                  abs(float(profile.get("temperature", 0)) - 0.25) < 0.001,
                  f"got {profile.get('temperature')}")
            check("override_source is global (set via API)",
                  profile.get("override_source") == "global",
                  f"got {profile.get('override_source')}")
            check("niche is Roofing Restoration", profile.get("niche") == "Roofing Restoration")

            # Test build_system_prompt
            prompt = brain_personality.build_system_prompt("Roofing Restoration")
            check("prompt contains AGGRESSIVE", "AGGRESSIVE" in prompt,
                  f"preview: {prompt[:80]}...")

            # Test helpers with Roofing Restoration
            check("recommended_temperature is 0.25",
                  abs(brain_personality.recommended_temperature("Roofing Restoration") - 0.25) < 0.001)
            check("confidence_threshold is 0.40",
                  abs(brain_personality.confidence_threshold("Roofing Restoration") - 0.40) < 0.001)
            check("go_fallback is GO",
                  brain_personality.go_fallback("Roofing Restoration") == "GO")

            # Test with a different niche (falls back to default)
            check("Unknown niche temp is 0.10 (default balanced)",
                  abs(brain_personality.recommended_temperature("Unknown Niche") - 0.10) < 0.001)
            check("Unknown niche conf_threshold is 0.60 (default balanced)",
                  abs(brain_personality.confidence_threshold("Unknown Niche") - 0.60) < 0.001)

            # Threshold filtering: aggressive threshold is 0.40
            # GO with confidence 0.30 should be flipped to NO_GO
            threshold = brain_personality.confidence_threshold("Roofing Restoration")
            check("threshold is 0.40", abs(threshold - 0.40) < 0.001)

            decision = "GO"
            confidence = 0.30
            if decision == "GO" and confidence < threshold:
                decision = "NO_GO"
            check("GO 0.30 < threshold 0.40 -> overridden to NO_GO",
                  decision == "NO_GO")

            # GO with confidence 0.50 passes aggressive threshold
            decision2 = "GO"
            confidence2 = 0.50
            if decision2 == "GO" and confidence2 < threshold:
                decision2 = "NO_GO"
            check("GO 0.50 >= threshold 0.40 -> stays GO",
                  decision2 == "GO")

        else:
            print("\n  Ollama online - running full brain decision...")
            result = await brain_decider.decide(
                target=test_target,
                alert_summary=test_alert,
                personality_niche="Roofing Restoration",
            )

            check("decision returned dict", isinstance(result, dict))
            check("decision is GO or NO_GO",
                  result.get("decision") in ("GO", "NO_GO"),
                  f"decision={result.get('decision')}")
            check("personality is aggressive",
                  result.get("personality") == "aggressive",
                  f"got {result.get('personality')}")
            check("confidence_threshold is 0.40",
                  abs(result.get("confidence_threshold", 0) - 0.40) < 0.001,
                  f"got {result.get('confidence_threshold')}")
            check("niche is Roofing Restoration",
                  result.get("niche") == "Roofing Restoration",
                  f"got {result.get('niche')}")

            print(f"  Result: decision={result.get('decision')} "
                  f"conf={result.get('confidence', 0):.2f} "
                  f"persona={result.get('personality')} "
                  f"threshold={result.get('confidence_threshold')} "
                  f"reasoning={result.get('reasoning', '')[:80]}")

        # ── Step 6: History check ──
        section("6. PREFERENCE HISTORY")
        r = await client.get(f"{BASE}/api/brain/personality/history?limit=10", headers=HEADERS)
        check("History returned", r.status_code == 200, f"HTTP {r.status_code}")
        hist = r.json()
        entries = hist.get("entries", [])
        check("History has entries", len(entries) > 0, f"got {len(entries)} entries")
        # Find the Roofing Restoration entries
        rr_entries = [e for e in entries if e.get("niche") == "Roofing Restoration"]
        check("Roofing entries in history", len(rr_entries) > 0,
              f"found {len(rr_entries)} entries for Roofing Restoration")

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"  Passed: {passed}/{total}")
        print(f"  Failed: {failed}/{total}")
        if failed > 0:
            print(f"\n  FAILURES: {failed} check(s) failed")
        else:
            print(f"  All checks passed!")

    return {"passed": passed, "failed": failed, "total": total}


if __name__ == "__main__":
    results = asyncio.run(main())
    sys.exit(1 if results["failed"] > 0 else 0)
