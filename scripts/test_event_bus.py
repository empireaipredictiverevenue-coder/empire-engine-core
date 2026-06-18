#!/usr/bin/env python3
"""
Quick test: emit an event through the bus, then verify it via the REST API.
"""

import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    HUB = "http://localhost:8001"
    TOKEN = "Jaykub20*"

    # ── 1. Emit a test event ───────────────────────────────────────────
    print("═══ EMITTING TEST EVENT ═══")
    from empire_event_bus import bus
    await bus.emit(
        "brain.decision",
        data={
            "decision": "GO",
            "confidence": 0.85,
            "reasoning": "test event from test script",
            "target": "Dallas Industrial Storage LLC",
        },
        source="test_event_bus.py",
        severity="info",
    )
    print("✓ Event emitted to bus")

    # ── 2. Query the REST API ──────────────────────────────────────────
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        # Recent events (all types)
        print("\n═══ QUERYING /api/v1/events/recent ═══")
        r = await client.get(
            f"{HUB}/api/v1/events/recent",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        data = r.json()
        events = data.get("events", [])
        print(f"✓ Total recent events: {len(events)}")
        for ev in events[-3:]:
            print(f"  [{ev.get('severity','?')}] {ev.get('event_type')} "
                  f"from {ev.get('source')} "
                  f"→ {ev.get('data', {}).get('decision', '—')}")

        # Filtered by event type
        print("\n═══ FILTERED: event_type=brain.decision ═══")
        r2 = await client.get(
            f"{HUB}/api/v1/events/recent?event_type=brain.decision&limit=5",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        data2 = r2.json()
        events2 = data2.get("events", [])
        print(f"✓ brain.decision events: {len(events2)}")
        for ev in events2:
            print(f"  {ev.get('data', {}).get('decision')} "
                  f"({ev.get('data', {}).get('confidence', '?')}) "
                  f"— {ev.get('data', {}).get('reasoning', '')[:60]}")

        # Stats
        print("\n═══ QUERYING /api/v1/events/stats ═══")
        r3 = await client.get(
            f"{HUB}/api/v1/events/stats",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        data3 = r3.json()
        print(f"✓ Total emitted: {data3.get('metrics', {}).get('total_emitted', 0)}")
        print(f"✓ Counts by type: {data3.get('counts_by_type', {})}")

    print("\n✓ VERIFIED — event bus is working end-to-end")


if __name__ == "__main__":
    asyncio.run(main())
