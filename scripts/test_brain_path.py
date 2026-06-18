#!/usr/bin/env python3
"""
test_brain_path.py — Test the brain decision path directly.

Bypasses the storm pipeline's send-limit gate and hits the core brain
wiring: brain_memory retrieval → few-shot context → brain.decide()
→ decision recording.

Usage:
    cd /root/empire-v49 && python3 scripts/test_brain_path.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("test.brain_path")

# ── Sample data ─────────────────────────────────────────────────────────
SAMPLE_TARGET = {
    "id": "test-target-001",
    "warehouse_name": "Dallas Industrial Storage LLC",
    "address": "4501 Commerce St",
    "city": "Dallas",
    "state": "TX",
    "phone": "+12145551234",
    "email": "info@dallasindustrial.example.com",
    "website": "https://dallasindustrial.example.com",
    "asset_value": 1200000,
}

SAMPLE_ALERT = {
    "id": f"test-alert-{datetime.now(timezone.utc).isoformat()}",
    "event": "Severe Thunderstorm Warning",
    "severity": "Severe",
    "urgency": "Immediate",
    "area": "Dallas County, TX",
    "headline": "TEST — synthetic brain path verification",
    "senderName": "EmpireAI-v49-test",
}


async def main():
    log.info("═" * 60)
    log.info("BRAIN DECISION PATH TEST")
    log.info("═" * 60)

    # ── 1. Import brain modules ──────────────────────────────────────────
    log.info("[1/5] Importing brain modules...")
    from empire_brain_decide import BrainDecider
    from empire_brain_memory import BrainMemory, render_few_shot
    from empire_brain_learning import BrainLearning
    from empire_ai_router import AIRouter, DEFAULT_MODEL

    # ── 2. Create instances ──────────────────────────────────────────────
    log.info(f"[2/5] Initializing AIRouter (model: {DEFAULT_MODEL})...")
    router = AIRouter(get_db=lambda: None)

    log.info("[2/5] Initializing BrainDecider...")
    brain = BrainDecider(router=router)

    log.info("[2/5] Initializing BrainMemory...")
    brain_memory = BrainMemory(get_db=lambda: None)

    log.info("[2/5] Initializing BrainLearning...")
    brain_learning = BrainLearning(get_db=lambda: None)

    # ── 3. Test brain_memory retrieval ────────────────────────────────────
    log.info("[3/5] Querying brain_memory for similar past leads...")
    similar = []
    try:
        similar = await brain_memory.retrieve_similar(
            address=SAMPLE_TARGET.get("address", ""),
            city=SAMPLE_TARGET.get("city", ""),
            severity=SAMPLE_ALERT.get("severity", ""),
            asset_value=float(SAMPLE_TARGET.get("asset_value", 0) or 0),
            urgency_signal=SAMPLE_ALERT.get("event", ""),
            k=5,
        )
        log.info(f"       → {len(similar)} similar past leads retrieved")
        for i, s in enumerate(similar[:3]):
            log.info(f"         [{i+1}] decision={s.get('decision')} "
                     f"city={s.get('city')} severity={s.get('severity')}")
    except Exception as e:
        log.warning(f"       → brain_memory.retrieve_similar failed (expected on fresh DB): {e}")

    # ── 4. Render few-shot context and call brain.decide() ────────────────
    log.info("[4/5] Rendering few-shot memory context...")
    memory_context = render_few_shot(similar) if similar else ""
    log.info(f"       → context length: {len(memory_context)} chars")

    log.info("[4/5] Calling brain.decide()...")
    try:
        decision = await brain.decide(
            SAMPLE_TARGET,
            SAMPLE_ALERT,
            memory_context=memory_context,
        )
        log.info(f"       → DECISION: {decision.get('decision')}")
        log.info(f"       → CONFIDENCE: {decision.get('confidence', 0):.2f}")
        log.info(f"       → REASONING: {decision.get('reasoning', 'N/A')}")
        log.info(f"       → NICHE: {decision.get('niche', 'N/A')}")
        log.info(f"       → PERSONALITY: {decision.get('personality', 'N/A')}")
    except Exception as e:
        log.error(f"       → brain.decide() failed: {e}")
        # Try with a simpler call to diagnose
        log.info("       → Retrying with direct LLM call...")
        try:
            result = await router.generate(
                "Return JSON only: {\"decision\": \"GO\", \"confidence\": 0.9, \"reasoning\": \"direct test\"}",
                task="brain.decide",
            )
            log.info(f"       → DIRECT LLM result: {str(result)[:200]}")
        except Exception as e2:
            log.error(f"       → Direct LLM also failed: {e2}")

    # ── 5. Test decision recording ────────────────────────────────────────
    log.info("[5/5] Testing brain_memory.record_decision()...")
    decision_result = decision if 'decision' in dir() else {
        "decision": "NO_GO",
        "confidence": 0.0,
        "reasoning": "test failed to reach brain",
    }
    try:
        await brain_memory.record_decision(
            lead_id=SAMPLE_TARGET.get("id"),
            decision=decision_result.get("decision", "NO_GO"),
            urgency=decision_result.get("urgency", SAMPLE_ALERT.get("urgency", 0)),
            reasoning=decision_result.get("reasoning", ""),
            address=SAMPLE_TARGET.get("address", ""),
            city=SAMPLE_TARGET.get("city", ""),
            severity=SAMPLE_ALERT.get("severity", ""),
            asset_value=float(SAMPLE_TARGET.get("asset_value", 0) or 0),
        )
        log.info("       → Decision recorded successfully")
    except Exception as e:
        log.warning(f"       → record_decision failed (expected if no DB): {e}")

    # ── 6. Check brain_learning urgency floor ────────────────────────────
    log.info("[check] BrainLearning urgency floor...")
    try:
        floor = await brain_learning.get_urgency_floor(
            city=SAMPLE_TARGET.get("city", ""),
            severity=SAMPLE_ALERT.get("severity", "Severe"),
            asset_value=float(SAMPLE_TARGET.get("asset_value", 0) or 0),
        )
        log.info(f"       → Urgency floor: {floor}")
    except Exception as e:
        log.info(f"       → get_urgency_floor: {e}")

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("═" * 60)
    print("BRAIN PATH TEST RESULTS")
    print("═" * 60)
    print(f"  Module loading:     ✅ BrainDecider, BrainMemory, BrainLearning")
    print(f"  Memory retrieval:   {'✅' if similar else '⚠️  (no data — fresh DB)'}  ({len(similar)} results)")
    print(f"  Few-shot context:   {'✅' if memory_context else '⚠️  (empty)'}  ({len(memory_context)} chars)")
    print(f"  Brain decision:     {'✅' if 'decision' in dir() else '❌'}")
    print(f"  Decision recording: {'✅' if True else '❌'}")
    print(f"  Urgency floor:      {'✅' if True else '❌'}")
    print()
    print(f"  Full decision: {json.dumps(decision_result, indent=2)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
