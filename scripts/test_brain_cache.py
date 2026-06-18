#!/usr/bin/env python3
"""
test_brain_cache.py — Fire a brain decision through the wrapped AIRouter
twice and compare timing to verify the token proxy cache.

Call 1: Ollama (slow, ~85s) — cache miss
Call 2: Same payload (fast, ~0.3s) — cache hit
"""
import json
import time
import urllib.request
import urllib.error

HUB_URL = "http://localhost:8001"
TOKEN = "Jaykub20*"

LEAD_PAYLOAD = {
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


def fire(label: str, timeout: int) -> dict:
    """POST to /api/v1/closer/score and return the parsed result + timing."""
    url = f"{HUB_URL}/api/v1/closer/score"
    data = json.dumps(LEAD_PAYLOAD).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = round(time.time() - start, 1)
            result = json.loads(resp.read().decode())
            return {"elapsed_s": elapsed, **result}
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {"elapsed_s": elapsed, "error": str(e)}


if __name__ == "__main__":
    print("=" * 60)
    print("TOKEN PROXY CACHE TEST")
    print("=" * 60)
    print(f"Lead: Dallas Industrial Storage LLC")
    print()

    # ── Call 1: Cache MISS (hits Ollama, ~85s) ────────────────
    print("[1/2] Firing brain decision (cache miss — hitting Ollama)...")
    print(f"      This will take ~85s...")
    r1 = fire("call-1", timeout=180)
    print(f"      Elapsed: {r1['elapsed_s']}s")
    if "error" in r1:
        print(f"      ERROR: {r1['error']}")
        decision = r1.get("decision", "ERROR")
        confidence = r1.get("confidence", 0)
        reasoning = r1.get("reasoning", r1.get("error", ""))
    else:
        decision = r1.get("decision", r1.get("status", "?"))
        confidence = r1.get("confidence", r1.get("score", 0))
        reasoning = r1.get("reasoning", "")
    print(f"      Decision: {decision}")
    print(f"      Confidence: {confidence}")
    print(f"      Reasoning: {str(reasoning)[:200]}")
    print()

    # ── Call 2: Cache HIT (from token proxy, ~0.3s) ───────────
    print("[2/2] Firing SAME brain decision (cache hit — should be instant)...")
    r2 = fire("call-2", timeout=30)
    print(f"      Elapsed: {r2['elapsed_s']}s")
    if "error" in r2:
        print(f"      ERROR: {r2['error']}")
    else:
        decision2 = r2.get("decision", r2.get("status", "?"))
        confidence2 = r2.get("confidence", r2.get("score", 0))
        reasoning2 = r2.get("reasoning", "")
        print(f"      Decision: {decision2}")
        print(f"      Confidence: {confidence2}")
        print(f"      Reasoning: {str(reasoning2)[:200]}")

    # ── Summary ────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    c1_time = r1["elapsed_s"]
    c2_time = r2["elapsed_s"]

    if c2_time > 0 and c1_time > 0:
        speedup = round(c1_time / c2_time, 1)
    else:
        speedup = "N/A"

    print(f"  Call 1 (cache miss):  {c1_time}s")
    print(f"  Call 2 (cache hit):   {c2_time}s")
    print(f"  Speedup:              {speedup}x")
    print()

    if c2_time < 5:
        print("  ✅ TOKEN PROXY CACHE IS WORKING — Call 2 was served from cache")
    else:
        print("  ⚠️  Call 2 was NOT cached — check if token proxy is active")
