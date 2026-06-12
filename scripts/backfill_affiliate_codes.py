"""
Backfill Affiliate Codes
=========================
Scans existing inbound_leads where affiliate_code IS NULL and checks
raw_jsonb (JSONB) and the source field for embedded affiliate information.

Candidate fields checked (in priority order):
  1. raw_jsonb -> 'affiliate_code'   (direct affiliate code)
  2. raw_jsonb -> 'ref'              (referral code)
  3. raw_jsonb -> 'utm_source'       (UTM source tracking, filtered)
  4. raw_jsonb -> any key containing "aff" (fallback)
  5. source field matching prefix    (e.g. "aff_xxx", "ref_xxx")

Run modes:
  python3 scripts/backfill_affiliate_codes.py        # dry-run (default)
  python3 scripts/backfill_affiliate_codes.py --apply # write to DB
  python3 scripts/backfill_affiliate_codes.py --lead-id 42  # single lead test
"""

import os
import re
import sys
import json
import argparse
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def get_sb():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY env vars required")
        sys.exit(1)
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def extract_affiliate_from_raw(raw) -> str | None:
    """Try to extract an affiliate_code from raw_jsonb dict/string."""
    if not raw:
        return None

    if isinstance(raw, dict):
        # Direct affiliate_code field
        aff = raw.get("affiliate_code")
        if aff and isinstance(aff, str) and aff.strip():
            return aff.strip()

        # ref field
        ref = raw.get("ref")
        if ref and isinstance(ref, str) and ref.strip():
            return ref.strip()

        # utm_source — only use if it looks like a code (not "(direct)" or generic)
        utm = raw.get("utm_source")
        if utm and isinstance(utm, str) and utm.strip():
            u = utm.strip()
            if u.lower() not in ("(direct)", "direct", "organic", "social", "email", "none", ""):
                return u

        # Check any field with "aff" in the name
        for k, v in raw.items():
            if "aff" in k.lower() and isinstance(v, str) and v.strip():
                return v.strip()

    elif isinstance(raw, str):
        # Try parsing as JSON first
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return extract_affiliate_from_raw(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        # Try regex patterns in the raw string
        patterns = [
            r'"?affiliate_code"?\s*[=:]\s*["\']?([a-zA-Z0-9_-]+)',
            r'"?ref"?\s*[=:]\s*["\']?([a-zA-Z0-9_-]+)',
            r'"?utm_source"?\s*[=:]\s*["\']?([a-zA-Z0-9_-]+)',
        ]
        for pat in patterns:
            m = re.search(pat, raw)
            if m:
                val = m.group(1)
                if val.lower() not in ("(direct)", "direct", "organic", "social", "email", "none"):
                    return val

    return None


def extract_affiliate_from_source(source: str) -> str | None:
    """Check source field for affiliate-like prefixes."""
    if not source or not isinstance(source, str):
        return None
    s = source.strip().lower()
    for prefix in ("aff_", "ref_", "affiliate_", "utm_"):
        if s.startswith(prefix):
            suffix = s[len(prefix):]
            if suffix and suffix not in ("(direct)", "direct", "organic", "social", "email", "none"):
                return suffix
    return None


def backfill(dry_run: bool = True, lead_id: int | None = None):
    sb = get_sb()

    # Build query for leads with NULL affiliate_code
    query = sb.table("inbound_leads") \
        .select("id,name,source,raw_jsonb,affiliate_code") \
        .is_("affiliate_code", "null")

    if lead_id:
        query = query.eq("id", lead_id)

    r = query.execute()
    candidates = r.data or []

    if not candidates:
        print("No leads found with NULL affiliate_code.")
        return

    total = len(candidates)
    print(f"Found {total} lead(s) with NULL affiliate_code to check.\n")

    updated = 0
    skipped = 0
    errors = 0

    for row in candidates:
        lid = row["id"]
        name = row.get("name", "?")
        source = row.get("source", "")
        raw = row.get("raw_jsonb")

        aff_code = extract_affiliate_from_raw(raw)
        if not aff_code:
            aff_code = extract_affiliate_from_source(source)

        if aff_code:
            print(f"  [{lid}] {name[:40]:40s} source={source[:15]:15s} → affiliate_code={aff_code}")
            if not dry_run:
                try:
                    sb.table("inbound_leads").update({"affiliate_code": aff_code}).eq("id", lid).execute()
                    updated += 1
                except Exception as e:
                    print(f"    ERROR updating lead {lid}: {e}")
                    errors += 1
        else:
            skipped += 1

    print()
    print("=" * 60)
    print(f"Backfill complete.")
    print(f"  Total scanned:   {total}")
    print(f"  Updated:         {updated if not dry_run else '(dry-run, would update)'}")
    print(f"  Skipped (no aff info found): {skipped}")
    print(f"  Errors:          {errors}")
    print(f"  Mode:            {'DRY RUN' if dry_run else 'APPLIED'}")
    if dry_run and (total - skipped) > 0:
        print(f"\n  Re-run with --apply to write {total - skipped} affiliate_code(s) to DB.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill affiliate_code on existing inbound leads")
    parser.add_argument("--apply", action="store_true", help="Write affiliate_code to DB (default: dry-run)")
    parser.add_argument("--lead-id", type=int, help="Process a single lead ID for testing")
    args = parser.parse_args()

    backfill(
        dry_run=not args.apply,
        lead_id=args.lead_id,
    )
