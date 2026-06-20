#!/usr/bin/env python3
"""
Empire AI · Prospector Sweep
=============================
Shared run script that scans all metros × all niches in sequence.
Orchestrates the prospector pipeline — find contractors, score them,
write to the 'prospects' table — with a clean progress dashboard.

Usage:
    python3 scripts/run_prospector_sweep.py
    python3 scripts/run_prospector_sweep.py --dry-run
    python3 scripts/run_prospector_sweep.py --metros Wichita Tulsa
    python3 scripts/run_prospector_sweep.py --niches roofing hvac
    python3 scripts/run_prospector_sweep.py --scout              # run mesh_scout too
    python3 scripts/run_prospector_sweep.py --json               # JSON output only
"""
import os
import sys
import json
import asyncio
import logging
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from config.metros import METROS
from bots.prospector import NICHES, run_multi as _prospector_multi

log = logging.getLogger("empire.prospector_sweep")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


# ── DASHBOARD ──────────────────────────────────────────────────────────

_DASH_FILL: str = "█"
_DASH_EMPTY: str = "░"


def _progress_bar(ratio: float, width: int = 24) -> str:
    filled: int = int(ratio * width)
    return _DASH_FILL * filled + _DASH_EMPTY * (width - filled)


def _print_summary(result: Dict[str, Any], elapsed_sec: float) -> None:
    total_found: int = result.get("total_found", 0)
    total_saved: int = result.get("total_saved", 0)
    metros_scanned: int = result.get("metros_scanned", 0)
    niches_scanned: int = result.get("niches_scanned", 0)
    by_metro: Dict[str, int] = result.get("by_metro", {})
    by_niche: Dict[str, int] = result.get("by_niche", {})

    print()
    print("=" * 60)
    print("  PROSPECTOR SWEEP — DASHBOARD")
    print("=" * 60)
    print(f"  Ran at:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Duration:    {elapsed_sec:.1f}s")
    print(f"  Metros:      {metros_scanned}")
    print(f"  Niches:      {niches_scanned}")
    print(f"  Found:       {total_found} prospects")
    print(f"  New saved:   {total_saved} prospects")
    print()

    # Per-niche breakdown
    if by_niche and any(by_niche.values()):
        max_niche_count: int = max(by_niche.values()) if by_niche else 1
        print("  ── By Niche ──")
        for niche in sorted(by_niche, key=lambda n: by_niche[n], reverse=True):
            cnt: int = by_niche[niche]
            bar: str = _progress_bar(cnt / max_niche_count)
            print(f"    {bar}  {niche:<22s}  {cnt:>4d}")
        print()

    # Per-metro breakdown
    if by_metro and any(by_metro.values()):
        max_metro_count: int = max(by_metro.values()) if by_metro else 1
        print("  ── By Metro ──")
        for metro in sorted(by_metro, key=lambda m: by_metro[m], reverse=True):
            cnt = by_metro[metro]
            bar = _progress_bar(cnt / max_metro_count)
            print(f"    {bar}  {metro:<24s}  {cnt:>4d}")
        print()

    print("=" * 60)
    print()


async def _run_scout(dry_run: bool) -> Optional[Dict[str, Any]]:
    """Optionally run mesh_scout storm analysis across all metros."""
    try:
        from bots.mesh_scout import run_once as scout_run_once
        scout_result: Dict[str, Any] = await scout_run_once(dry_run=dry_run)
        log.info(f"[scout] complete: {scout_result.get('tasks_created', 0)} tasks created")
        return scout_result
    except Exception as e:
        log.warning(f"[scout] skipped or failed: {e}")
        return None


def _build_cli() -> argparse.ArgumentParser:
    p: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Run prospector sweep across all metros × all niches.",
    )
    p.add_argument(
        "--metros",
        nargs="*",
        default=None,
        help="Metro(s) to scan (default: all configured metros)",
    )
    p.add_argument(
        "--niches",
        nargs="*",
        default=None,
        help="Niche(s) to scan (default: all configured niches)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Score and report prospects but don't write to DB",
    )
    p.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output raw JSON result instead of dashboard",
    )
    p.add_argument(
        "--scout",
        action="store_true",
        default=False,
        help="Also run mesh_scout storm analysis across all metros",
    )
    return p


async def main() -> None:
    parser: argparse.ArgumentParser = _build_cli()
    args: argparse.Namespace = parser.parse_args()

    started_at: datetime = datetime.now(timezone.utc)

    # Resolve metros and niches
    metros: Optional[List[str]] = args.metros
    niches: Optional[List[str]] = args.niches

    # Validate metro names against shared config
    if metros:
        unknown: List[str] = [m for m in metros if m not in METROS]
        if unknown:
            print(f"[SWEEP] Unknown metros: {unknown}")
            print(f"[SWEEP] Available: {list(METROS.keys())}")
            sys.exit(1)

    # Validate niche names
    if niches:
        unknown_niches: List[str] = [n for n in niches if n not in NICHES]
        if unknown_niches:
            print(f"[SWEEP] Unknown niches: {unknown_niches}")
            print(f"[SWEEP] Available: {NICHES}")
            sys.exit(1)

    # Run prospector sweep
    metro_count: int = len(metros or METROS)
    niche_count: int = len(niches or NICHES)
    log.info(f"starting prospector sweep ({metro_count} metros × {niche_count} niches)"
             + (" [dry-run]" if args.dry_run else ""))

    result: Dict[str, Any] = await _prospector_multi(
        metros=metros, niches=niches, dry_run=args.dry_run,
    )

    # Optionally run scout
    scout_result: Optional[Dict[str, Any]] = None
    if args.scout:
        log.info("running mesh_scout storm analysis across all metros...")
        scout_result = await _run_scout(dry_run=args.dry_run)

    elapsed: float = (datetime.now(timezone.utc) - started_at).total_seconds()

    if args.json:
        output: Dict[str, Any] = {
            "prospector": result,
            "scout": scout_result,
            "elapsed_sec": round(elapsed, 1),
            "dry_run": args.dry_run,
            "run_at": started_at.isoformat(),
        }
        print(json.dumps(output, indent=2))
    else:
        _print_summary(result, elapsed)
        if scout_result:
            scout_tasks: int = scout_result.get("tasks_created", 0)
            print(f"  Scout tasks created: {scout_tasks}")
            print()

    # Exit non-zero if nothing was found (useful for cron alerts)
    if result.get("total_found", 0) == 0:
        log.warning("sweep completed but found zero prospects")
        sys.exit(1)

    log.info(f"sweep complete in {elapsed:.1f}s"
             f" — {result['total_found']} found, {result['total_saved']} saved")


if __name__ == "__main__":
    asyncio.run(main())
