#!/usr/bin/env python3
"""
synthetic_brain endpoint benchmark.
Hits /api/v1/synthetic/run N times with the same objective, logs per-call
(http_code, time_total, json_valid, all_fields_str, error) to CSV, prints
a summary (success rate, p50/p95 latency).

Usage: python3 scripts/benchmark_synthetic_brain.py <out_csv> [N_calls]
"""
import json
import sys
import time
import csv
import urllib.request
import urllib.error

OUT_CSV = sys.argv[1]
N_CALLS = int(sys.argv[2]) if len(sys.argv) > 2 else 10
URL = "http://127.0.0.1:8005/api/v1/synthetic/run"
API_KEY = "test-key-please-change-in-production"
OBJECTIVE = "Roofing lead gen ad, +15551234567"
TIMEOUT_S = 45  # hard ceiling per call; mark as failure if exceeded


def one_call(call_num: int) -> tuple:
    payload = json.dumps({"objective": OBJECTIVE}).encode()
    req = urllib.request.Request(
        URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
    )
    t0 = time.time()
    err = ""
    code = 0
    body = ""
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            code = resp.getcode()
            body = resp.read().decode()
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = e.read().decode()
        except Exception:
            body = ""
        err = f"HTTP {e.code}"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:90]
    elapsed = round(time.time() - t0, 2)

    # Validate: JSON parses + all 4 strategy meta fields are strings
    json_valid = False
    fields_str = False
    try:
        data = json.loads(body)
        json_valid = True
        meta = data.get("meta") or {}
        expected = [
            "script_executed",
            "voice_profile",
            "system_template_used",
            "production_location",
        ]
        fields_str = all(isinstance(meta.get(k), str) and meta.get(k) for k in expected)
        if not fields_str:
            bad = [k for k in expected if not isinstance(meta.get(k), str)]
            err = f"non_string_fields: {bad}"
    except Exception as e:
        err = f"json_parse: {e}"[:90]

    return (call_num, code, elapsed, json_valid, fields_str, err[:90])


def main():
    rows = [one_call(i) for i in range(1, N_CALLS + 1)]

    # CSV
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["call", "http", "time_s", "json_valid", "fields_str", "error"])
        for r in rows:
            w.writerow(r)

    # Per-call print
    for r in rows:
        print(
            f"  call {r[0]:2d}: HTTP {r[1]}  {r[2]:6.2f}s  "
            f"json_valid={r[3]}  fields_str={r[4]}  err={r[5]!r}"
        )

    # Summary
    successes = [r for r in rows if r[1] == 200 and r[3] and r[4]]
    partial = [r for r in rows if r[1] == 200 and r[3] and not r[4]]
    failures = [r for r in rows if r[1] != 200 or not r[3]]
    times = sorted(r[2] for r in successes)
    p50 = times[len(times) // 2] if times else 0.0
    p95 = times[int(len(times) * 0.95) - 1] if len(times) >= 2 else (times[0] if times else 0.0)
    mx = max(times, default=0.0)
    mn = min(times, default=0.0)

    print(f"\n  === SUMMARY ({OUT_CSV}) ===")
    print(f"  full_success:  {len(successes)}/{N_CALLS}")
    print(f"  partial:       {len(partial)}/{N_CALLS}  (200 but bad fields)")
    print(f"  failed:        {len(failures)}/{N_CALLS}")
    print(f"  latency (full_success only): min={mn}s  p50={p50}s  p95={p95}s  max={mx}s")


if __name__ == "__main__":
    main()
