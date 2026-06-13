#!/usr/bin/env python3
"""
Test per-operator personality override precedence:
1. Set global aggressive for Roofing Restoration (already done in previous step)
2. Set operator override to conservative for Roofing Restoration
3. Verify operator override takes precedence (query with operator_id)
4. Verify global still applies without operator_id
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

BASE = "http://localhost:8000"
TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Operator ID from Supabase
OPERATOR_ID = "2dc46865-d997-4ed3-b321-92b3c952e8bd"


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
        # ── Step 1: Verify global aggressive is active ──
        section("1. VERIFY GLOBAL AGGRESSIVE IS ACTIVE (precondition)")
        r = await client.get(f"{BASE}/api/brain/personality/snapshot", headers=HEADERS)
        snap = r.json()
        rr_global = snap.get("configs", {}).get("Roofing Restoration", {})
        check("Global Roofing persona is aggressive",
              rr_global.get("persona") == "aggressive",
              f"got {rr_global.get('persona')}")
        check("Global Roofing confidence_threshold is 0.40",
              abs(float(rr_global.get("confidence_threshold", 0)) - 0.40) < 0.001,
              f"got {rr_global.get('confidence_threshold')}")

        # ── Step 2: Verify operator has no override yet ──
        section("2. VERIFY OPERATOR HAS NO OVERRIDE YET")
        r = await client.get(f"{BASE}/api/brain/personality/operator/{OPERATOR_ID}", headers=HEADERS)
        op_snap = r.json()
        op_overrides = op_snap.get("overrides", {})
        check("Operator has no overrides initially",
              len(op_overrides) == 0,
              f"got {len(op_overrides)} overrides: {list(op_overrides.keys())}")

        # ── Step 3: Set operator override to conservative for Roofing Restoration ──
        section("3. SET OPERATOR OVERRIDE TO CONSERVATIVE")
        payload = {
            "operator_id": OPERATOR_ID,
            "niche": "Roofing Restoration",
            "persona": "conservative",
            "confidence_threshold": 0.75,
            "temperature": 0.05,
        }
        r = await client.post(f"{BASE}/api/brain/personality/operator/set",
                               headers=HEADERS, json=payload)
        check("Operator set returned 200", r.status_code == 200,
              f"HTTP {r.status_code}")
        result = r.json()
        check("Operator set returned ok=True", result.get("ok") is True,
              f"got {result}")
        check("Operator set returned persona=conservative",
              result.get("persona") == "conservative",
              f"got {result.get('persona')}")
        check("Operator set returned niche=Roofing Restoration",
              result.get("niche") == "Roofing Restoration",
              f"got {result.get('niche')}")

        # ── Step 4: Verify operator override is saved ──
        section("4. VERIFY OPERATOR OVERRIDE IS SAVED")
        r = await client.get(f"{BASE}/api/brain/personality/operator/{OPERATOR_ID}", headers=HEADERS)
        op_snap = r.json()
        op_overrides = op_snap.get("overrides", {})
        check("Operator has overrides now",
              len(op_overrides) > 0,
              f"got {len(op_overrides)} overrides")
        rr_op = op_overrides.get("Roofing Restoration", {})
        check("Operator Roofing override exists",
              bool(rr_op),
              f"keys: {list(op_overrides.keys())}")
        check("Operator Roofing persona is conservative",
              rr_op.get("persona") == "conservative",
              f"got {rr_op.get('persona')}")
        check("Operator Roofing confidence_threshold is 0.75",
              abs(float(rr_op.get("confidence_threshold", 0)) - 0.75) < 0.001,
              f"got {rr_op.get('confidence_threshold')}")
        check("Operator Roofing temperature is 0.05",
              abs(float(rr_op.get("temperature", 0)) - 0.05) < 0.001,
              f"got {rr_op.get('temperature')}")

        # ── Step 5: Verify operator override takes precedence ──
        # Use direct Python call with BrainPersonality to test the override resolution
        section("5. VERIFY OPERATOR OVERRIDE PRECEDENCE")
        from supabase import create_client
        from empire_brain_personality import BrainPersonality

        SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
        SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if SUPABASE_URL and SUPABASE_KEY:
            real_db = create_client(SUPABASE_URL, SUPABASE_KEY)
        else:
            real_db = None

        def get_db():
            return real_db

        bp = BrainPersonality(get_db=get_db)

        # With operator_id → should return conservative (operator override)
        profile_with_op = bp.personality_for_niche(
            "Roofing Restoration", operator_id=OPERATOR_ID
        )
        check("With operator: persona is conservative",
              profile_with_op.get("persona") == "conservative",
              f"got {profile_with_op.get('persona')}")
        check("With operator: override_source is operator",
              profile_with_op.get("override_source") == "operator",
              f"got {profile_with_op.get('override_source')}")
        check("With operator: confidence_threshold is 0.75",
              abs(float(profile_with_op.get("confidence_threshold", 0)) - 0.75) < 0.001,
              f"got {profile_with_op.get('confidence_threshold')}")
        check("With operator: temperature is 0.05",
              abs(float(profile_with_op.get("temperature", 0)) - 0.05) < 0.001,
              f"got {profile_with_op.get('temperature')}")
        check("With operator: go_fallback is NO_GO (conservative)",
              profile_with_op.get("go_fallback") == "NO_GO",
              f"got {profile_with_op.get('go_fallback')}")

        # Without operator_id → should still return global aggressive
        profile_no_op = bp.personality_for_niche("Roofing Restoration")
        check("Without operator: persona is aggressive (global)",
              profile_no_op.get("persona") == "aggressive",
              f"got {profile_no_op.get('persona')}")
        check("Without operator: override_source is global",
              profile_no_op.get("override_source") == "global",
              f"got {profile_no_op.get('override_source')}")
        check("Without operator: confidence_threshold is 0.40",
              abs(float(profile_no_op.get("confidence_threshold", 0)) - 0.40) < 0.001,
              f"got {profile_no_op.get('confidence_threshold')}")
        check("Without operator: temperature is 0.25 (aggressive)",
              abs(float(profile_no_op.get("temperature", 0)) - 0.25) < 0.001,
              f"got {profile_no_op.get('temperature')}")

        # The two profiles MUST differ
        check("With vs without operator: different personas",
              profile_with_op.get("persona") != profile_no_op.get("persona"),
              f"both returned {profile_with_op.get('persona')}")
        check("With vs without operator: different thresholds",
              profile_with_op.get("confidence_threshold") != profile_no_op.get("confidence_threshold"),
              f"both returned {profile_with_op.get('confidence_threshold')}")

        # ── Step 6: Also test helper methods with operator_id ──
        section("6. HELPER METHODS WITH OPERATOR ID")
        check("recommended_temperature with operator is 0.05",
              abs(bp.recommended_temperature("Roofing Restoration", operator_id=OPERATOR_ID) - 0.05) < 0.001)
        check("recommended_temperature without operator is 0.25",
              abs(bp.recommended_temperature("Roofing Restoration") - 0.25) < 0.001)
        check("confidence_threshold with operator is 0.75",
              abs(bp.confidence_threshold("Roofing Restoration", operator_id=OPERATOR_ID) - 0.75) < 0.001)
        check("confidence_threshold without operator is 0.40",
              abs(bp.confidence_threshold("Roofing Restoration") - 0.40) < 0.001)
        check("go_fallback with operator is NO_GO",
              bp.go_fallback("Roofing Restoration", operator_id=OPERATOR_ID) == "NO_GO")
        check("go_fallback without operator is GO",
              bp.go_fallback("Roofing Restoration") == "GO")

        # ── Step 7: Build system prompt ──
        section("7. SYSTEM PROMPT DIFFERENTIATION")
        prompt_with = bp.build_system_prompt("Roofing Restoration", operator_id=OPERATOR_ID)
        prompt_without = bp.build_system_prompt("Roofing Restoration")

        check("With operator: prompt contains CONSERVATIVE",
              "CONSERVATIVE" in prompt_with,
              f"preview: {prompt_with[:60]}...")
        check("Without operator: prompt contains AGGRESSIVE",
              "AGGRESSIVE" in prompt_without,
              f"preview: {prompt_without[:60]}...")
        check("Prompts differ between operator and global",
              prompt_with != prompt_without,
              "operator and global prompts should be different")

        # ── Cleanup: Remove the operator override ──
        section("8. CLEANUP: REMOVE OPERATOR OVERRIDE")
        payload_remove = {
            "operator_id": OPERATOR_ID,
            "niche": "Roofing Restoration",
        }
        r = await client.post(f"{BASE}/api/brain/personality/operator/remove",
                               headers=HEADERS, json=payload_remove)
        check("Remove returned 200", r.status_code == 200,
              f"HTTP {r.status_code}")
        remove_result = r.json()
        check("Remove returned ok=True", remove_result.get("ok") is True,
              f"got {remove_result}")

        # Verify operator override is gone
        r = await client.get(f"{BASE}/api/brain/personality/operator/{OPERATOR_ID}", headers=HEADERS)
        op_snap_after = r.json()
        check("Operator override removed (empty overrides)",
              len(op_snap_after.get("overrides", {})) == 0,
              f"got {len(op_snap_after.get('overrides', {}))} overrides")

        # Global should still be aggressive
        profile_after = bp.personality_for_niche("Roofing Restoration")
        check("Global still aggressive after operator remove",
              profile_after.get("persona") == "aggressive",
              f"got {profile_after.get('persona')}")

        # ── Summary ──
        section("SUMMARY")
        total = passed + failed
        print(f"  Passed: {passed}/{total}")
        print(f"  Failed: {failed}/{total}")
        if failed > 0:
            pass
        else:
            print(f"  All checks passed! Operator override correctly takes precedence over global setting.")

    return {"passed": passed, "failed": failed}


if __name__ == "__main__":
    results = asyncio.run(main())
    print(f"\nExit code: {1 if results['failed'] > 0 else 0}")
    sys.exit(1 if results["failed"] > 0 else 0)
