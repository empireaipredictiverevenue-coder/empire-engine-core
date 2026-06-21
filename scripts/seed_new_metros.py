"""Seed radar_targets for 8 new metro areas — Phase 1 scaling.
Adds sample property-level entries per metro so the lead pipeline has
something to match against when storms hit these areas.

Usage:
    python3 scripts/seed_new_metros.py
    python3 scripts/seed_new_metros.py --dry-run
"""
import os
import sys
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client
from config.metros import METROS

# ── 8 new metros to add (storm-prone, high-pop, gaps in coverage) ──
NEW_METROS = [
    "Miami",           # FL — hurricane central
    "Orlando",         # FL — hurricane zone
    "Jacksonville",    # FL — hurricane zone
    "New Orleans",     # LA — hurricane zone
    "Charlotte",       # NC — hurricane + hail corridor
    "Oklahoma City",   # OK — tornado alley
    "St. Louis",       # MO — hail/wind belt
    "Nashville",       # TN — wind/hail
]

# Sample property addresses per metro (generic seed data)
SAMPLE_STREETS = [
    "100 Main St",
    "250 Oak Avenue",
    "475 Elm Street",
    "720 Maple Drive",
    "890 Pine Road",
]


def seed_metros(dry_run: bool = False) -> dict:
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

    results = {"metros_seeded": 0, "rows_inserted": 0, "errors": 0, "by_metro": {}}

    for metro_name in NEW_METROS:
        if metro_name not in METROS:
            print(f"  [SKIP] {metro_name} not in config/metros.py")
            results["errors"] += 1
            continue

        info = METROS[metro_name]
        lat = info["lat"]
        lon = info["lon"]
        state = info["state"]

        # Check if this metro already has radar coverage
        existing = sb.table("radar_targets").select("id").eq("state", state).limit(1).execute()
        # Also check by city match (handle compound names like "Oklahoma City")
        city_candidates = [metro_name]
        if "-" in metro_name:
            city_candidates.extend(p.strip() for p in metro_name.split("-"))
        if "/" in metro_name:
            city_candidates.extend(p.strip() for p in metro_name.split("/"))

        has_existing = False
        for city in city_candidates:
            r = sb.table("radar_targets").select("id").eq("city", city).eq("state", state).limit(1).execute()
            if r.data:
                has_existing = True
                break

        if has_existing:
            print(f"  [SKIP] {metro_name}, {state} — already has radar coverage")
            results["by_metro"][metro_name] = {"status": "already_present", "inserted": 0}
            continue

        inserted = 0
        for street in SAMPLE_STREETS:
            row = {
                "address": f"{street}, {metro_name}, {state}",
                "city": metro_name,
                "state": state,
                "phone": None,
                "email": None,
                "source": "metro_expansion_seed",
                "status": "active",
                "damage_severity": "unknown",
                "urgency_score": 5,
                "location": f"POINT({lon} {lat})",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "meta": {
                    "source": "metro_expansion_seed",
                    "seeded_at": datetime.now(timezone.utc).isoformat(),
                    "metro": metro_name,
                },
            }
            if dry_run:
                print(f"  [DRY-RUN] Would insert: {row['address']}")
                inserted += 1
            else:
                try:
                    sb.table("radar_targets").insert(row).execute()
                    inserted += 1
                except Exception as e:
                    print(f"  [ERROR] {street}, {metro_name}: {e}")
                    results["errors"] += 1

        results["rows_inserted"] += inserted
        results["metros_seeded"] += 1
        results["by_metro"][metro_name] = {"status": "seeded", "inserted": inserted}
        print(f"  [OK] {metro_name}, {state} — {inserted} entries seeded")

    return results


def main():
    parser = argparse.ArgumentParser(description="Seed radar_targets for 8 new metros")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted without writing")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  PHASE 1 METRO EXPANSION — SEED {len(NEW_METROS)} NEW METROS")
    print(f"  {'DRY RUN — no writes' if args.dry_run else 'LIVE MODE — writing to Supabase'}")
    print(f"{'='*60}\n")

    results = seed_metros(dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Metros seeded: {results['metros_seeded']}/{len(NEW_METROS)}")
    print(f"  Rows inserted: {results['rows_inserted']}")
    print(f"  Errors:        {results['errors']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
