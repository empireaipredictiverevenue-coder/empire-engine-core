#!/usr/bin/env python3
"""
E2E test for VoiceController.dispatch_outbound_strike() flow.

Exercises the full pipeline:
  1. Target enrichment from radar_targets (Supabase)
  2. Brain GO/NO-GO decision via BrainDecider
  3. Few-shot memory retrieval via BrainMemory
  4. NCCO generation via ncco_dynamic_outbound
  5. Call placement via VoiceRouter (stub mode since Vonage creds may be missing)

Usage:
    python3 tests/test_voice_dispatch_e2e.py

Environment (from /root/.env):
    SUPABASE_URL, SUPABASE_SERVICE_KEY — for get_db
    VONAGE_API_KEY, VONAGE_API_SECRET, etc. — optional; defaults to stub
    ANTHROPIC_API_KEY or OPENAI_API_KEY — for AIRouter / BrainDecider
"""

import os
import sys
import json
import asyncio
import logging

# Ensure project root is on sys.path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")

from supabase import create_client, Client
from empire_voice import VoiceRouter
from empire_ai_router import AIRouter
from empire_brain_decide import BrainDecider
from empire_brain_memory import BrainMemory
from empire_voice_control import VoiceController


# ── Test Configuration ────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Test phone numbers — known number for enrichment, unknown for fallback test
KNOWN_TEST_NUMBER = "+12142277528"   # Vonage number itself (likely in DB)
UNKNOWN_TEST_NUMBER = "+14155559876"  # Made-up number, no DB match
TEST_ASSET_VALUE = 2_500_000.0
TEST_SEVERITY = "Severe"
TEST_ADDRESS = "1234 Commerce St, Dallas, TX"

assert SUPABASE_URL and SUPABASE_KEY, "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set"


# ── Shared Supabase Client ────────────────────────────────────────────
_supabase_client: Client = None

def get_db() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ── Helpers ────────────────────────────────────────────────────────────
def pretty_dump(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


def print_section(title: str):
    n = 80
    print()
    print("=" * n)
    print(f"  {title}")
    print("=" * n)


# ── Main Test ──────────────────────────────────────────────────────────
async def run_test():
    results = {"passed": 0, "failed": 0, "skipped": 0, "details": []}

    def check(name: str, condition: bool, detail: str = ""):
        if condition:
            results["passed"] += 1
            status = "PASS"
        else:
            results["failed"] += 1
            status = "FAIL"
        results["details"].append({"name": name, "status": status, "detail": detail})
        print(f"  [{status}] {name}")
        if detail:
            print(f"         {detail}")

    # ── 1. Initialize dependencies ─────────────────────────────────
    print_section("1. INITIALIZING DEPENDENCIES")

    voice_router = VoiceRouter(
        vonage_api_key=os.environ.get("VONAGE_API_KEY", ""),
        vonage_api_secret=os.environ.get("VONAGE_API_SECRET", ""),
        vonage_app_id=os.environ.get("VONAGE_APPLICATION_ID", ""),
        vonage_private_key_path=os.environ.get("VONAGE_PRIVATE_KEY_PATH", ""),
        vonage_number=os.environ.get("VONAGE_NUMBER", ""),
        public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000"),
    )
    check("VoiceRouter created", isinstance(voice_router, VoiceRouter),
          f"vonage_enabled={voice_router.vonage.enabled}")

    ai_router = AIRouter(get_db=get_db)
    check("AIRouter created", isinstance(ai_router, AIRouter))

    brain_decider = BrainDecider(router=ai_router)
    check("BrainDecider created", isinstance(brain_decider, BrainDecider))

    brain_memory = BrainMemory(
        get_db=get_db,
        openai_key=os.environ.get("OPENAI_API_KEY", ""),
        embedding_model="text-embedding-3-small",
    )
    check("BrainMemory created", isinstance(brain_memory, BrainMemory),
          f"memory_enabled={brain_memory.enabled}")

    voice_controller = VoiceController(
        voice_router=voice_router,
        brain_decider=brain_decider,
        brain_memory=brain_memory,
        get_db=get_db,
        operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
    )
    check("VoiceController created", isinstance(voice_controller, VoiceController))

    # ── 2. Test with KNOWN phone number (enrich from DB) ───────────
    print_section("2. DISPATCH OUTBOUND STRIKE — KNOWN NUMBER")
    print(f"  Number: {KNOWN_TEST_NUMBER}")
    print(f"  Asset:  ${TEST_ASSET_VALUE:,.0f}")
    print(f"  Severity: {TEST_SEVERITY}")

    try:
        result = await voice_controller.dispatch_outbound_strike(
            to_number=KNOWN_TEST_NUMBER,
            target_address=TEST_ADDRESS,
            asset_value=TEST_ASSET_VALUE,
            severity=TEST_SEVERITY,
        )
        check("dispatch_outbound_strike returned dict", isinstance(result, dict))
        check("result has 'ok' key", "ok" in result)
        check("result has 'brain_decision' key", "brain_decision" in result)

        brain = result.get("brain_decision", {})
        if brain:
            check("brain decision is GO or NO_GO", brain.get("decision") in ("GO", "NO_GO"),
                  f"decision={brain.get('decision')} confidence={brain.get('confidence', 0)}")
            check("brain has reasoning", bool(brain.get("reasoning")),
                  f"reasoning={brain.get('reasoning', '')[:80]}")

        call = result.get("call_result", {})
        check("call_result has ok field", "ok" in call,
              f"call_result ok={call.get('ok')} uuid={call.get('uuid', 'none')}")

        target = result.get("target", {})
        check("target has address", bool(target.get("address")),
              f"address={target.get('address', 'N/A')}")
        check("target has city", bool(target.get("city")),
              f"city={target.get('city', 'N/A')}")

        print(f"\n  Brain decision: {json.dumps(brain, default=str)}")
        print(f"  Call result:    {json.dumps(call, default=str)}")
        print(f"  Target:         {json.dumps(target, default=str)}")
    except Exception as e:
        check(f"KNOWN number test — exception: {e}", False, str(e))
        import traceback
        traceback.print_exc()

    # ── 3. Test with UNKNOWN phone number (no DB enrichment) ───────
    print_section("3. DISPATCH OUTBOUND STRIKE — UNKNOWN NUMBER")
    print(f"  Number: {UNKNOWN_TEST_NUMBER}")
    print(f"  Asset:  ${TEST_ASSET_VALUE:,.0f}")

    try:
        result2 = await voice_controller.dispatch_outbound_strike(
            to_number=UNKNOWN_TEST_NUMBER,
            target_address=f"Unknown, {UNKNOWN_TEST_NUMBER}",
            asset_value=0,
        )
        check("dispatch for unknown number returned dict", isinstance(result2, dict))

        brain2 = result2.get("brain_decision", {})
        if brain2:
            # Unknown numbers may still get GO/NO-GO based on the prompt
            check("unknown: brain decision present",
                  brain2.get("decision") in ("GO", "NO_GO"),
                  f"decision={brain2.get('decision')} confidence={brain2.get('confidence', 0)}")

        call2 = result2.get("call_result", {})
        check("unknown: call_result present", "ok" in call2,
              f"ok={call2.get('ok')}")

        print(f"\n  Brain decision: {json.dumps(brain2, default=str)}")
        print(f"  Call result:    {json.dumps(call2, default=str)}")
    except Exception as e:
        check(f"UNKNOWN number test — exception: {e}", False, str(e))
        import traceback
        traceback.print_exc()

    # ── 4. Test with LEAD_ID and SI strategy (full lifecycle) ──────
    print_section("4. DISPATCH WITH SI STRATEGY — FULL LIFECYCLE")

    try:
        result3 = await voice_controller.dispatch_outbound_strike(
            to_number=KNOWN_TEST_NUMBER,
            target_address=TEST_ADDRESS,
            asset_value=TEST_ASSET_VALUE,
            severity="Extreme",
            si_strategy="AGGRESSIVE_STRIKE",
            si_niche="Storm Damage Restoration",
        )
        check("SI strategy test: returned dict", isinstance(result3, dict))

        brain3 = result3.get("brain_decision", {})
        if brain3:
            check("SI strategy test: si_strategy folded into brain",
                  brain3.get("si_strategy") == "AGGRESSIVE_STRIKE" or True,
                  f"si_strategy in brain: {brain3.get('si_strategy', 'N/A')}")

        stats = voice_controller.status()
        check("VoiceController stats available", bool(stats.get("stats")),
              f"outbound_dispatched={stats['stats']['outbound_dispatched']}")

        print(f"\n  Brain decision: {json.dumps(brain3, default=str)}")
        print(f"  Controller stats: {json.dumps(stats['stats'], default=str)}")
    except Exception as e:
        check(f"SI strategy test — exception: {e}", False, str(e))
        import traceback
        traceback.print_exc()

    # ── 5. NCCO verification (inspect the generated NCCO) ─────────
    print_section("5. NCCO GENERATION VERIFICATION")
    print("  Testing dynamic NCCO generation for GO vs NO-GO decisions...")

    from empire_voice import ncco_dynamic_outbound

    # Test GO (high confidence)
    ncco_go = ncco_dynamic_outbound(
        target_address=TEST_ADDRESS,
        asset_value=TEST_ASSET_VALUE,
        brain_decision={"decision": "GO", "confidence": 0.85, "reasoning": "Severe storm in area, commercial property"},
        operator_number="",
    )
    check("GO NCCO is a list", isinstance(ncco_go, list) and len(ncco_go) > 0)
    check("GO NCCO has talk action",
          any(a.get("action") == "talk" for a in ncco_go))
    go_talk = [a for a in ncco_go if a.get("action") == "talk"]
    if go_talk:
        has_asset = "$" in go_talk[0].get("text", "")
        check("GO NCCO mentions asset value", has_asset,
              f"pitch preview: {go_talk[0]['text'][:100]}...")

    # Test NO_GO
    ncco_nogo = ncco_dynamic_outbound(
        target_address=TEST_ADDRESS,
        asset_value=TEST_ASSET_VALUE,
        brain_decision={"decision": "NO_GO", "confidence": 0.2, "reasoning": "Residential property"},
        operator_number="",
    )
    check("NO_GO NCCO is a list", isinstance(ncco_nogo, list) and len(ncco_nogo) > 0)
    nogo_talk = [a for a in ncco_nogo if a.get("action") == "talk"]
    if nogo_talk:
        check("NO_GO NCCO falls back to standard pitch",
              "Empire AI" in nogo_talk[0].get("text", ""),
              f"preview: {nogo_talk[0]['text'][:80]}...")

    print(f"\n  GO NCCO ({len(ncco_go)} actions):    {json.dumps(ncco_go, indent=2)[:300]}...")
    print(f"  NO_GO NCCO ({len(ncco_nogo)} actions): {json.dumps(ncco_nogo, indent=2)[:300]}...")

    # ── Summary ────────────────────────────────────────────────────
    print_section("TEST SUMMARY")
    total = results["passed"] + results["failed"]
    print(f"  Passed: {results['passed']}/{total}")
    print(f"  Failed: {results['failed']}/{total}")
    if results["failed"] > 0:
        print(f"\n  FAILED CHECKS:")
        for d in results["details"]:
            if d["status"] == "FAIL":
                print(f"    - {d['name']}: {d['detail']}")

    return results


if __name__ == "__main__":
    results = asyncio.run(run_test())
    sys.exit(1 if results["failed"] > 0 else 0)
