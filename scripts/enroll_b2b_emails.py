#!/usr/bin/env python3
"""
B2B Email Enrollment Script
============================
Bulk-enrolls existing B2B leads (from radar_targets) into the
b2b_outreach email drip sequence.

Usage:
    python3 scripts/enroll_b2b_emails.py              # dry-run (default)
    python3 scripts/enroll_b2b_emails.py --live        # actually enroll
    python3 scripts/enroll_b2b_emails.py --max 200     # limit to 200 leads
    python3 scripts/enroll_b2b_emails.py --sub-niche 'Managed IT'  # filter by sub-niche
    python3 scripts/enroll_b2b_emails.py --status      # show current enrollment stats
"""

import os, sys, json, re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")
from supabase import create_client

# Placeholder email filter
_PLACEHOLDER_RE = re.compile(r"(user@domain|logo@|noreply|wix|sentry)", re.I)

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)

def _is_valid_email(email: str) -> bool:
    if not email or not email.strip():
        return False
    email = email.strip().lower()
    if _PLACEHOLDER_RE.search(email):
        return False
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))

def show_status(sb):
    """Show current B2B email enrollment stats."""
    r = sb.table("email_sequences").select("id, status, sequence_type").eq("sequence_type", "b2b_outreach").execute()
    rows = r.data or []
    total = len(rows)
    by_status = {}
    for row in rows:
        s = row.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    print("=" * 60)
    print("B2B EMAIL SEQUENCE STATUS (b2b_outreach)")
    print("=" * 60)
    print(f"  Total enrolled: {total}")
    for s, cnt in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {s}: {cnt}")

    # Also show how many B2B leads have emails but aren't enrolled
    r2 = sb.table("radar_targets").select("id").eq("meta->>source", "B2B Lead Gen").not_.is_("email", "null").neq("email", "").execute()
    total_with_email = len(r2.data or [])

    print(f"\n  B2B leads with email (in radar_targets): {total_with_email}")
    print(f"  Not yet enrolled: {max(0, total_with_email - total)}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="Bulk-enroll B2B leads into email drip campaign")
    p.add_argument("--live", action="store_true", help="Actually enroll (default: dry-run)")
    p.add_argument("--max", type=int, default=500, help="Max leads to enroll (default: 500)")
    p.add_argument("--sub-niche", choices=["Managed IT", "Merchant Services", "HR & Staffing"],
                   help="Filter by sub-niche")
    p.add_argument("--status", action="store_true", help="Show enrollment status and exit")
    args = p.parse_args()

    sb = _sb()

    if args.status:
        return show_status(sb)

    # Query B2B leads with valid emails
    query = sb.table("radar_targets").select("id, email, warehouse_name, meta, city, state") \
        .eq("meta->>source", "B2B Lead Gen") \
        .not_.is_("email", "null") \
        .neq("email", "")

    if args.sub_niche:
        query = query.eq("meta->>b2b_sub_niche", args.sub_niche)

    r = query.limit(args.max).execute()
    all_leads = r.data or []

    # Filter to valid emails only
    leads = [l for l in all_leads if _is_valid_email(l.get("email", ""))]
    filtered = len(all_leads) - len(leads)

    print(f"B2B leads with email: {len(all_leads)} ({filtered} filtered as placeholders)")
    print(f"Valid leads:          {len(leads)}")
    print(f"Mode:                 {'LIVE' if args.live else 'DRY-RUN'}")
    print()

    if args.live:
        enrolled = 0
        skipped = 0
        for lead in leads:
            email = lead["email"].strip().lower()
            meta = lead.get("meta", {}) or {}
            sub_niche = meta.get("b2b_sub_niche", "Business Services")
            company = (lead.get("warehouse_name") or "").strip()

            # Check if already enrolled
            existing = sb.table("email_sequences").select("id").eq("email", email).limit(1).execute()
            if existing.data:
                skipped += 1
                continue

            try:
                sb.table("email_sequences").insert({
                    "email":         email,
                    "target_addr":   f"{lead.get('city', '')}, {lead.get('state', '')}",
                    "sequence_type": "b2b_outreach",
                    "current_step":  0,
                    "status":        "active",
                    "next_send_at":  datetime.now(timezone.utc).isoformat(),
                    "meta": {
                        "company":        company,
                        "b2b_sub_niche":  sub_niche,
                        "city":           lead.get("city"),
                        "state":          lead.get("state"),
                        "source":         "B2B Lead Gen",
                    },
                }).execute()
                enrolled += 1
                print(f"  ✓ {enrolled:3d}. {company[:40]:40s} → {email:30s} ({sub_niche})")
            except Exception as e:
                print(f"  ✗ {company[:40]:40s} → {email:30s} error: {e}")

        print(f"\n{'=' * 60}")
        print(f"Enrolled: {enrolled} | Skipped (already enrolled): {skipped}")
    else:
        # Dry-run: show what would be enrolled
        for i, lead in enumerate(leads[:10], 1):
            meta = lead.get("meta", {}) or {}
            company = (lead.get("warehouse_name") or "").strip()
            sub_niche = meta.get("b2b_sub_niche", "?")
            print(f"  {i:3d}. {company[:40]:40s} → {lead['email']:30s} ({sub_niche})")

        if len(leads) > 10:
            print(f"  ... and {len(leads) - 10} more")

        print(f"\n{'=' * 60}")
        print(f"DRY-RUN: {len(leads)} would be enrolled")
        print("Run with --live to actually enroll")


if __name__ == "__main__":
    main()
