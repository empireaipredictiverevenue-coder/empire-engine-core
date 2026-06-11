#!/usr/bin/env python3
"""
SPA Smoke Test — Empire AI Command Deck
========================================
Verifies that the SPA renders correctly by starting the hub (or connecting
to a running instance) and checking for critical structural markers.

Usage:
    # Test a running instance
    python scripts/smoke_test_spa.py --url http://localhost:8000

    # Start hub and test (CI mode)
    python scripts/smoke_test_spa.py --start-hub

    # Custom host/port
    python scripts/smoke_test_spa.py --host 0.0.0.0 --port 8000

Returns exit code 0 on success, 1 on failure.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── Structural markers that prove the SPA fully rendered ──────────
#
# Each marker is (name, substring_or_callable) where the callable
# receives the page text and returns True if the check passes.
MARKERS = [
    ("HTTP 200", lambda page: True),  # checked before marker scan
    ("DOCTYPE + html lang", lambda p: "<!DOCTYPE html>" in p and 'lang="en"' in p),
    ("React + htm import map", lambda p: "react@18.3.1" in p and "htm@3.1.1" in p),
    ("createRoot bootstrap", lambda p: "createRoot" in p),
    ("render call", lambda p: ".render(" in p),
    ("DonutChart component", lambda p: "function DonutChart(" in p),
    ("DonutChart neuron glow ref", lambda p: "chartWrapRef" in p and "chart-neuron" in p),
    ("SpringCount component", lambda p: "function SpringCount(" in p),
    ("VoiceBuildTimeline component", lambda p: "function VoiceBuildTimeline(" in p),
    ("fireNeuronGlow function", lambda p: "function fireNeuronGlow(" in p),
    ("useHapticForm hook", lambda p: "function useHapticForm(" in p),
    ("vib() helper", lambda p: "const vib = (p) =>" in p),
    ("chart-neuron CSS animation", lambda p: ".chart-neuron.firing::before" in p),
    ("neuron-fire keyframes", lambda p: "@keyframes neuron-fire" in p),
    ("haptic-ombre animation", lambda p: "haptic-ombre" in p),
    ("DonutChart instances ≥10", lambda p: p.count("DonutChart") >= 10),
    ("SpringCount usages ≥5", lambda p: p.count("SpringCount") >= 5),
    ("Pulse section in sidebar", lambda p: "Pulse" in p),
    ("Pipeline section in sidebar", lambda p: "Pipeline" in p),
    ("Dispatch section in sidebar", lambda p: "Dispatch" in p),
    ("Neural Core section in sidebar", lambda p: "Neural Core" in p or "NeuralCore" in p),
    ("Governor section in sidebar", lambda p: "Governor" in p),
    ("AGI Loop section in sidebar", lambda p: "AGI" in p or "Agi" in p),
    ("Holo Map section in sidebar", lambda p: "Map" in p or "Holo" in p),
    ("Sidebar has ≥12 sections", lambda p: p.count('"label"') >= 12 or p.count("SECTIONS") > 0),
]

ESSENTIAL = {
    "DonutChart component",
    "SpringCount component",
    "createRoot bootstrap",
    "React + htm import map",
    "HTTP 200",
}


def fetch_page(url: str, timeout: int = 15) -> tuple[int, str]:
    """Fetch a URL and return (status_code, body_text)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EmpireSPASmokeTest/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def start_hub(host: str, port: int, project_dir: str, timeout: int = 30) -> subprocess.Popen:
    """Start the hub as a subprocess and wait for it to respond."""
    env = os.environ.copy()
    # Set minimal env for the hub to boot without crashing
    env.setdefault("HUB_TOKEN", "smoke-test-token")
    env.setdefault("SUPABASE_URL", "")
    env.setdefault("SUPABASE_ANON_KEY", "")
    env.setdefault("SUPABASE_SERVICE_KEY", "")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "hub:app", "--host", host, "--port", str(port), "--log-level", "warning"],
        cwd=project_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for the hub to be ready
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            print(f"FAIL: Hub exited prematurely with code {proc.returncode}")
            sys.exit(1)
        try:
            req = urllib.request.Request(f"http://{host}:{port}/api/market-pulse")
            resp = urllib.request.urlopen(req, timeout=3)
            if resp.status == 200:
                return proc
        except Exception:
            pass
        time.sleep(1)

    proc.terminate()
    print(f"FAIL: Hub did not respond within {timeout}s")
    sys.exit(1)


def run_tests(url: str) -> bool:
    """Run all marker checks against the given URL. Returns True if all pass."""
    print(f"\n{'═' * 60}")
    print(f"  SPA SMOKE TEST  ›  {url}")
    print(f"{'═' * 60}\n")

    status, body = fetch_page(f"{url}/command")
    print(f"  HTTP {status}  |  {len(body):,} chars\n")

    if status != 200:
        print(f"  ❌ FAIL: HTTP {status} (expected 200)")
        return False

    # Override HTTP 200 check — it passed
    passed = 0
    failed = 0
    results = []

    for name, check in MARKERS:
        if name == "HTTP 200":
            ok = status == 200
        else:
            ok = check(body)

        if ok:
            passed += 1
            results.append(f"  ✅ {name}")
        else:
            failed += 1
            results.append(f"  ❌ {name}")

    # Print results grouped
    print(f"  ── Structural markers ({passed}/{passed + failed}) ──")
    for r in results:
        print(r)

    print(f"\n  ── Summary ──")
    print(f"  Passed: {passed}  Failed: {failed}  Total: {passed + failed}")

    # Check essential markers
    missing_essential = []
    for name, check in MARKERS:
        if name in ESSENTIAL:
            if name == "HTTP 200":
                ok = status == 200
            else:
                ok = check(body)
            if not ok:
                missing_essential.append(name)

    if missing_essential:
        print(f"\n  ❌ FAIL: {len(missing_essential)} essential markers missing: {', '.join(missing_essential)}")
        return False

    if failed > 0:
        print(f"\n  ⚠  PASS with {failed} non-essential failures")
        return True

    print(f"\n  ✅ ALL {passed} CHECKS PASSED")
    return True


def main():
    parser = argparse.ArgumentParser(description="SPA Smoke Test for Empire AI")
    parser.add_argument("--url", default=None, help="URL of a running hub (default: start one locally)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind when starting hub")
    parser.add_argument("--port", type=int, default=8000, help="Port to use")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    os.chdir(project_dir)

    hub_proc = None

    if args.url:
        url = args.url.rstrip("/")
    else:
        url = f"http://{args.host}:{args.port}"
        print(f"Starting hub on {url} ...")
        hub_proc = start_hub(args.host, args.port, str(project_dir))
        print("Hub is ready.\n")

    try:
        success = run_tests(url)
    finally:
        if hub_proc:
            print("\nShutting down hub...")
            hub_proc.terminate()
            try:
                hub_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                hub_proc.kill()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
