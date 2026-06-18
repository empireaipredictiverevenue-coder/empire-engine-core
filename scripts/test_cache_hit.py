#!/usr/bin/env python3
"""
Test token proxy cache: fire the same brain decision twice.
First call = cache miss (hits Ollama), second = cache hit (returns instantly).
"""

import asyncio
import httpx
import json
import time

HUB = "http://localhost:8001"
TOKEN = "Jaykub20*"
PAYLOAD = {
    "lead": {
        "name": "Dallas Industrial Storage LLC",
        "phone": "+12145551234",
        "email": "info@dallasindustrial.example.com",
        "address": "4501 Commerce St",
        "city": "Dallas",
        "state": "TX",
        "asset_value": 1200000,
    },
    "alert_summary": {
        "event": "Severe Thunderstorm Warning",
        "severity": "Severe",
        "urgency": "Immediate",
        "area": "Dallas County, TX",
    },
}


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=90) as client:

        # ── Call 1: should be a cache miss ─────────────────────────────
        print("═══ CALL 1 (expect cache miss → slow) ═══")
        t1 = time.time()
        r1 = await client.post(f"{HUB}/api/v1/closer/score", headers=headers, json=PAYLOAD)
        elapsed1 = time.time() - t1
        data1 = r1.json()
        print(f"  Result: {data1.get('decision')} (conf {data1.get('confidence', 0):.2f})")
        print(f"  Time:   {elapsed1:.1f}s")

        # ── Call 2: same payload → should be cache hit ────────────────
        print("\n═══ CALL 2 (same payload → expect cache hit, fast) ═══")
        t2 = time.time()
        r2 = await client.post(f"{HUB}/api/v1/closer/score", headers=headers, json=PAYLOAD)
        elapsed2 = time.time() - t2
        data2 = r2.json()
        print(f"  Result: {data2.get('decision')} (conf {data2.get('confidence', 0):.2f})")
        print(f"  Time:   {elapsed2:.1f}s")

        # ── Call 3: different payload → cache miss ────────────────────
        PAYLOAD2 = {
            "lead": {
                "name": "Houston Warehouse Solutions",
                "phone": "+17135559876",
                "email": "ops@houstonwarehouse.example.com",
                "address": "8900 Katy Fwy",
                "city": "Houston",
                "state": "TX",
                "asset_value": 850000,
            },
            "alert_summary": {
                "event": "Flash Flood Warning",
                "severity": "Severe",
                "urgency": "Immediate",
                "area": "Harris County, TX",
            },
        }
        print("\n═══ CALL 3 (different lead → cache miss) ═══")
        t3 = time.time()
        r3 = await client.post(f"{HUB}/api/v1/closer/score", headers=headers, json=PAYLOAD2)
        elapsed3 = time.time() - t3
        data3 = r3.json()
        print(f"  Result: {data3.get('decision')} (conf {data3.get('confidence', 0):.2f})")
        print(f"  Time:   {elapsed3:.1f}s")

        # ── Summary ───────────────────────────────────────────────────
        print("\n═══ SUMMARY ═══")
        speedup = elapsed1 / elapsed2 if elapsed2 > 0 else 0
        print(f"  Call 1 (miss):  {elapsed1:.1f}s")
        print(f"  Call 2 (hit):   {elapsed2:.1f}s  {'✓ FASTER' if elapsed2 < elapsed1 else '? not cached'}")
        print(f"  Call 3 (miss):  {elapsed3:.1f}s")
        if elapsed2 < elapsed1:
            print(f"  Speedup:  {speedup:.1f}x")
        else:
            print("  (Calls were same speed — proxy may have bypassed cache for this task type)")


if __name__ == "__main__":
    asyncio.run(main())
