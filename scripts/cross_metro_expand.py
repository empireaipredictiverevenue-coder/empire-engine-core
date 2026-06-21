"""Cross-Metro Contractor Expansion — Phase 1 Scaling
=====================================================
Seeds contractors in new metros by importing top-rated contractors from
nearby metros that commonly service storm-affected areas across state lines.
Roofing/HVAC/restoration contractors are "storm chasers" — they routinely
travel to hurricane zones. This script creates shadow entries for the 4 new
metros (Miami, Orlando, Jacksonville, New Orleans) so the dispatch pipeline
can route leads to them immediately.

Usage:
    python3 scripts/cross_metro_expand.py
    python3 scripts/cross_metro_expand.py --dry-run
    python3 scripts/cross_metro_expand.py --per-metro 25
"""
import os
import sys
import argparse
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

# ── Cross-metro mapping: new metro → source metros with actual contractors ──
# Source metros come from the 16 metros that actually have contractors.
# These are storm-chaser contractors who service hazard zones regionally.
CROSS_METRO_MAP: Dict[str, List[str]] = {
    # ── Phase 1a: Florida hurricane metros (already expanded, idempotent) ──
    "Miami":           ["New Orleans", "Atlanta", "Houston"],
    "Orlando":         ["Atlanta", "New Orleans", "Nashville"],
    "Jacksonville":    ["Atlanta", "Nashville", "Memphis"],
    # ── Phase 1b: Storm/hail metros (next 8 from the 40 with zero contractors) ──
    "Charlotte":       ["Atlanta", "Nashville", "Memphis"],
    "Birmingham":      ["Atlanta", "Nashville", "Memphis"],
    "Jackson":         ["New Orleans", "Memphis", "Dallas-Fort Worth"],
    "Little Rock":     ["Memphis", "Oklahoma City", "Dallas-Fort Worth"],
    "Indianapolis":    ["Nashville", "Kansas City", "Atlanta"],
    "Denver":          ["Kansas City", "Wichita", "Oklahoma City"],
    "Louisville":      ["Nashville", "Kansas City", "Atlanta"],
    "Knoxville":       ["Nashville", "Atlanta", "Memphis"],
}

# Target niches (storm-response — highest value for lead buying)
TARGET_NICHES = [
    "roofing", "restoration", "general contractor",
    "water mitigation", "hvac", "gutter", "tree removal",
    "emergency services",
]

# Minimum trust_score for a contractor to be cloned.
# Most have trust_score=5.0; this is a future-proof floor.
MIN_TRUST_SCORE = 1

# How many contractors to import per metro
DEFAULT_PER_METRO = 20


def _sb() -> Any:
    return create_client(
        os.getenv("SUPABASE_URL", ""),
        os.getenv("SUPABASE_SERVICE_KEY", ""),
    )


def expand_metros(dry_run: bool = False, per_metro: int = DEFAULT_PER_METRO) -> dict:
    sb = _sb()
    results: dict = {
        "metros_processed": 0,
        "total_imported": 0,
        "total_skipped_duplicate": 0,
        "errors": 0,
        "by_metro": {},
    }

    for target_metro, source_metros in CROSS_METRO_MAP.items():
        print(f"\n{'='*60}")
        print(f"  TARGET: {target_metro}")
        print(f"  Sources: {', '.join(source_metros)}")
        print(f"{'='*60}")

        # Check existing contractors in target metro
        existing = sb.table("contractors").select("id").eq("metro", target_metro).execute()
        existing_count = len(existing.data or [])
        print(f"  Existing contractors in {target_metro}: {existing_count}")

        # Fetch top contractors from source metros.
        # Order by completed_jobs (real activity signal) since trust_score is uniform.
        all_sources: List[Dict] = []
        for src_metro in source_metros:
            r = sb.table("contractors").select("*").eq("metro", src_metro).gte("trust_score", MIN_TRUST_SCORE).eq("active", True).order("completed_jobs", desc=True).limit(per_metro).execute()
            found = len(r.data or [])
            print(f"  {src_metro}: {found} qualified contractors (trust >= {MIN_TRUST_SCORE})")
            if r.data:
                all_sources.extend(r.data)

        # Deduplicate by name (same franchise may appear in multiple source metros)
        seen_names: set = set()
        unique_sources: List[Dict] = []
        for c in all_sources:
            name = (c.get("name") or c.get("business_name") or "").strip().lower()
            if name and name not in seen_names:
                seen_names.add(name)
                unique_sources.append(c)

        print(f"  Unique after dedup: {len(unique_sources)}")

        imported = 0
        skipped = 0
        sample: List[Dict] = []

        for contractor in unique_sources:
            # Build new contractor entry for the target metro
            orig_name = contractor.get("name") or contractor.get("business_name", "Unknown")
            orig_phone = contractor.get("phone", "")
            orig_trust = contractor.get("trust_score", 0)
            orig_specialties = contractor.get("specialties", [])
            orig_niche = contractor.get("niche", "")
            orig_trade = contractor.get("trade", "")
            orig_meta = contractor.get("meta", {}) or {}

            # Create a synthetic phone to avoid uniqueness collisions.
            # Takes first 3 + last 4 digits of original, inserts metro-specific hash.
            phone_digits = "".join(c for c in str(orig_phone) if c.isdigit())
            metro_hash = str(abs(hash(target_metro)) % 10000).zfill(4)
            if len(phone_digits) == 10:
                # US 10-digit: keep area code + last 4, hash replaces middle 3
                synthetic_phone = f"+1{phone_digits[:3]}{metro_hash}{phone_digits[6:]}"
            elif len(phone_digits) > 10:
                # International: use metro hash + last 6 of original
                synthetic_phone = f"+1{metro_hash}{phone_digits[-6:]}"
            else:
                synthetic_phone = f"+1555{metro_hash}0000"

            # Synthetic email to avoid uniqueness collisions
            synthetic_email = f"crossmetro.{uuid.uuid4().hex[:8]}@empire-ai.placeholder"

            payload = {
                "name": f"{orig_name} ({target_metro})",
                "phone": synthetic_phone,
                "email": synthetic_email,
                "metro": target_metro,
                "active": True,
                "trust_score": orig_trust,
                "specialties": orig_specialties if orig_specialties else [],
                "niche": orig_niche,
                "trade": orig_trade,
                "solana_wallet": None,
                "meta": {
                    "source": "cross_metro_expansion",
                    "cross_metro_source": contractor.get("metro", ""),
                    "cross_metro_original_id": contractor.get("id"),
                    "cross_metro_original_name": orig_name,
                    "cross_metro_original_phone": orig_phone,
                    "expanded_at": datetime.now(timezone.utc).isoformat(),
                    "note": "Shadow entry — real contractor imported from nearby metro for storm coverage. Update phone/email when discovered.",
                    "tcpa_consent": False,
                },
            }

            if dry_run:
                print(f"  [DRY-RUN] Would create: {payload['name'][:60]} | phone={synthetic_phone[:12]}...")
                imported += 1
                if len(sample) < 3:
                    sample.append({"name": payload["name"], "metro": target_metro, "source_metro": contractor.get("metro")})
            else:
                try:
                    # Check if a cross-metro entry already exists for this original contractor
                    dup_check = sb.table("contractors").select("id").eq("meta->>cross_metro_original_id", str(contractor.get("id"))).eq("metro", target_metro).limit(1).execute()
                    if dup_check.data:
                        skipped += 1
                        continue

                    sb.table("contractors").insert(payload).execute()
                    imported += 1
                    if len(sample) < 3:
                        sample.append({"name": payload["name"], "metro": target_metro, "source_metro": contractor.get("metro")})
                except Exception as e:
                    err_str = str(e)[:120]
                    print(f"  [ERROR] {orig_name[:40]}: {err_str}")
                    results["errors"] += 1

        results["metros_processed"] += 1
        results["total_imported"] += imported
        results["total_skipped_duplicate"] += skipped
        results["by_metro"][target_metro] = {
            "imported": imported,
            "skipped": skipped,
            "existing_before": existing_count,
            "sample": sample,
        }
        print(f"  → Imported: {imported}, Skipped (dup): {skipped}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Cross-metro contractor expansion for new metros")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing")
    parser.add_argument("--per-metro", type=int, default=DEFAULT_PER_METRO, help=f"Max contractors to pull from each source metro (default: {DEFAULT_PER_METRO})")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  PHASE 1 — CROSS-METRO CONTRACTOR EXPANSION")
    print(f"  {'DRY RUN — no writes' if args.dry_run else 'LIVE MODE'}")
    print(f"  Per source metro: up to {args.per_metro} contractors")
    print(f"  Source metro mapping:")
    for target, sources in CROSS_METRO_MAP.items():
        print(f"    {target:20s} ← {', '.join(sources)}")
    print(f"{'='*60}")

    results = expand_metros(dry_run=args.dry_run, per_metro=args.per_metro)

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Metros processed: {results['metros_processed']}")
    print(f"  Total imported:   {results['total_imported']}")
    print(f"  Skipped (dup):    {results['total_skipped_duplicate']}")
    print(f"  Errors:           {results['errors']}")
    for metro, m in sorted(results["by_metro"].items()):
        sample_names = ", ".join(s["name"][:30] for s in m.get("sample", [])[:2])
        print(f"  {metro:20s}: +{m['imported']} imported (had {m['existing_before']}) — {sample_names}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
