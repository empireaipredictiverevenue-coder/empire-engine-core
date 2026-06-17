"""Combined email discovery: v2 (fast known-domain) then v1 (HTTP check).

Runs two phases on leads missing phone & email:
  Phase 1 — v2:  known-domain substring mapping + name guessing (local, ~0.1s/lead)
  Phase 2 — v1:  HTTP GET to verify domain existence (~1-2s/lead)

Both phases query leads with phone=null AND email=null.  Phase 2 naturally
skips whatever Phase 1 filled in, so no dedup is needed.

Usage:
    python3 -m agents.email_discovery_fallback
    python3 -m agents.email_discovery_fallback --max-per-run 1000
"""
import sys, argparse, time

sys.path.insert(0, "/root/empire-v49")

from agents.email_discovery_fallback.email_discovery_v2 import run as run_v2
from agents.email_discovery_fallback.email_discovery import run as run_v1


def main():
    p = argparse.ArgumentParser(
        description="Email discovery: v2 (known-domain) + v1 (HTTP) in sequence"
    )
    p.add_argument("--max-per-run", type=int, default=1000,
                    help="Max leads to scan per phase (default 1000)")
    p.add_argument("--v1-only", action="store_true",
                    help="Skip v2, run only the HTTP-based v1 phase")
    p.add_argument("--v2-only", action="store_true",
                    help="Skip v1, run only the fast v2 phase")
    args = p.parse_args()

    start = time.time()

    # ── Phase 1: v2 (fast known-domain mapping + name guessing) ──────
    v2_result = {"candidates": 0, "known": 0, "guessed": 0}
    if not args.v1_only:
        print("=" * 60)
        print("PHASE 1: email_discovery_v2 (known-domain + name guess)")
        print("=" * 60)
        v2_result = run_v2(max_per_run=args.max_per_run)
        print(f"[v2] {v2_result}")
    else:
        print("[v2] SKIPPED (--v1-only)")

    # ── Phase 2: v1 (HTTP domain check) ─────────────────────────────
    # v1 naturally skips leads that v2 already wrote emails to
    v1_result = {"candidates": 0, "found": 0, "guesses": 0}
    if not args.v2_only:
        print()
        print("=" * 60)
        print("PHASE 2: email_discovery v1 (HTTP domain check)")
        print("=" * 60)
        v1_result = run_v1(max_per_run=args.max_per_run)
        print(f"[v1] {v1_result}")
    else:
        print("[v1] SKIPPED (--v2-only)")

    # ── Combined summary ────────────────────────────────────────────
    elapsed = time.time() - start
    total_found = v2_result.get("known", 0) + v2_result.get("guessed", 0) + v1_result.get("found", 0)
    print()
    print("=" * 60)
    print(f"COMBINED: {v2_result.get('known',0)} known-domain + "
          f"{v2_result.get('guessed',0)} v2-guess + "
          f"{v1_result.get('found',0)} v1-http = {total_found} emails found "
          f"in {elapsed:.1f}s")
    print("=" * 60)

    return {
        "v2": v2_result,
        "v1": v1_result,
        "total_found": total_found,
        "elapsed_seconds": round(elapsed, 1),
    }


if __name__ == "__main__":
    result = main()
    print(f"FINAL: {result}")
