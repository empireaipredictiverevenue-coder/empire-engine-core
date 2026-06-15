#!/usr/bin/env python3
"""
Enroll Niche SMS — Backfill Script
===================================
Finds enriched_leads with b2b_sub_niche and phone, then either:
  - Updates existing sms_sequences with the correct sequence_type
  - Or enrolls unenrolled leads via the hub API

Usage:
    python3 scripts/enroll_niche_sms.py               # dry-run (default)
    python3 scripts/enroll_niche_sms.py --live         # actually enroll/update
    python3 scripts/enroll_niche_sms.py --status       # show current stats only
"""

import os
import sys
import json
import argparse
import logging
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("enroll_niche_sms")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# Map b2b_sub_niche → SMS sequence_type
NICHE_TO_SEQUENCE = {
    "Commercial Roofing": "commercial_roofing",
    "Commercial Solar":   "commercial_solar",
    "Debt Relief":        "debt_relief",
    "HR & Staffing":       "b2b_outreach",
    "Managed IT":          "b2b_outreach",
    "Merchant Services":   "b2b_outreach",
}


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def show_status(sb):
    """Print enrollment stats by b2b_sub_niche."""
    r = sb.table("enriched_leads").select(
        "id,phone,meta->>b2b_sub_niche,meta->>source,status"
    ).not_.is_("phone", "null").not_.is_("meta->>b2b_sub_niche", "null").limit(2000).execute()
    rows = r.data or []

    # Group by sub_niche
    by_niche = Counter()
    for row in rows:
        by_niche[row.get("b2b_sub_niche", "?")] += 1

    print("\n=== enriched_leads with b2b_sub_niche + phone ===")
    print(f"Total: {len(rows)}")
    for n, c in sorted(by_niche.items(), key=lambda x: -x[1]):
        print(f"  {n}: {c}")

    # Check SMS enrollment for these phones
    phones = [row["phone"] for row in rows if row.get("phone")]
    enrolled_ok = 0
    enrolled_wrong = 0
    not_enrolled = 0
    wrong_details = []

    for phone in phones:
        r2 = sb.table("sms_sequences").select("sequence_type").eq("phone", phone).limit(1).execute()
        lead = next((l for l in rows if l.get("phone") == phone), None)
        sub = (lead or {}).get("b2b_sub_niche", "")
        expected = NICHE_TO_SEQUENCE.get(sub, "storm_strike")

        if r2.data:
            actual = r2.data[0].get("sequence_type", "?")
            if actual == expected:
                enrolled_ok += 1
            else:
                enrolled_wrong += 1
                if sub in ("Commercial Roofing", "Commercial Solar", "Debt Relief"):
                    wrong_details.append(f"    {phone}: actual={actual} expected={expected} sub={sub}")
        else:
            not_enrolled += 1

    print(f"\n=== SMS Enrollment Status ===")
    print(f"  Correct type:   {enrolled_ok}")
    print(f"  Wrong type:     {enrolled_wrong}")
    print(f"  Not enrolled:   {not_enrolled}")
    if wrong_details:
        print(f"\nWrong-type details (niche-specific only):")
        for d in wrong_details:
            print(d)

    return {
        "total": len(rows),
        "enrolled_ok": enrolled_ok,
        "enrolled_wrong": enrolled_wrong,
        "not_enrolled": not_enrolled,
    }


def run(dry_run: bool = True):
    sb = _sb()
    now = datetime.now(timezone.utc)
    mode = "DRY-RUN" if dry_run else "LIVE"

    # 1. Fetch leads with b2b_sub_niche + phone
    r = sb.table("enriched_leads").select(
        "id,warehouse_name,phone,meta,status"
    ).not_.is_("phone", "null").not_.is_("meta->>b2b_sub_niche", "null").limit(2000).execute()
    leads = r.data or []

    log.info(f"[{mode}] Found {len(leads)} leads with b2b_sub_niche + phone")

    updated = 0      # SMS sequence type corrected
    enrolled = 0     # New SMS enrollment created
    skipped = 0      # Already has correct type or blocked
    errors = 0
    error_details = []

    for lead in leads:
        meta = lead.get("meta") or {}
        if not isinstance(meta, dict):
            skipped += 1
            continue

        sub_niche = meta.get("b2b_sub_niche", "")
        expected_seq = NICHE_TO_SEQUENCE.get(sub_niche)
        if not expected_seq:
            # Not a niche we handle — skip
            skipped += 1
            continue

        phone = lead.get("phone", "").strip()
        if not phone:
            skipped += 1
            continue

        # 2. Check existing SMS enrollment
        try:
            existing = sb.table("sms_sequences").select(
                "id,sequence_type,status"
            ).eq("phone", phone).limit(1).execute()
        except Exception as e:
            errors += 1
            error_details.append(f"  query fail {phone}: {e}")
            continue

        if existing.data:
            row = existing.data[0]
            if row.get("sequence_type") == expected_seq:
                skipped += 1
                continue

            # Needs update
            if not dry_run:
                try:
                    sb.table("sms_sequences").update({
                        "sequence_type": expected_seq,
                        "meta": {
                            **(row.get("meta") or {}),
                            "sequence_type_overridden_at": now.isoformat(),
                            "previous_sequence_type": row.get("sequence_type"),
                        },
                    }).eq("id", row["id"]).execute()
                    log.info(f"  UPDATED {phone}: {row['sequence_type']} → {expected_seq} ({sub_niche})")
                except Exception as e:
                    errors += 1
                    error_details.append(f"  update fail {phone}: {e}")
                    continue
            else:
                log.info(f"  WOULD UPDATE {phone}: {row['sequence_type']} → {expected_seq} ({sub_niche})")
            updated += 1
        else:
            # Not enrolled — enroll via hub
            target_addr = meta.get("raw", {}).get("address", "") or lead.get("address", "")
            normalized = _normalize_phone(phone)
            if not normalized:
                skipped += 1
                continue

            if not dry_run:
                try:
                    import urllib.request
                    hub_url = os.getenv("HUB_URL", "http://127.0.0.1:8000")
                    hub_token = os.getenv("HUB_TOKEN", "")
                    if not hub_token:
                        errors += 1
                        error_details.append(f"  no HUB_TOKEN for {phone}")
                        continue

                    payload = json.dumps({
                        "phone": normalized,
                        "target_addr": target_addr,
                        "sequence_type": expected_seq,
                        "meta": {
                            "enriched_lead_id": lead.get("id"),
                            "warehouse_name": lead.get("warehouse_name"),
                            "source": "enroll_niche_sms_script",
                            "b2b_sub_niche": sub_niche,
                        },
                    }).encode()

                    req = urllib.request.Request(
                        f"{hub_url}/api/v1/sms/enroll",
                        data=payload,
                        method="POST",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {hub_token}",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status == 200:
                            log.info(f"  ENROLLED {phone} → {expected_seq} ({sub_niche})")
                        else:
                            errors += 1
                            error_details.append(f"  enroll fail {phone}: http_{resp.status}")
                except Exception as e:
                    errors += 1
                    error_details.append(f"  enroll error {phone}: {e}")
            else:
                log.info(f"  WOULD ENROLL {normalized} → {expected_seq} ({sub_niche})")
            enrolled += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"[{mode}] Enrollment Summary")
    print(f"{'='*60}")
    print(f"  Updated (wrong type fixed):  {updated}")
    print(f"  Newly enrolled:              {enrolled}")
    print(f"  Skipped (already correct):   {skipped}")
    print(f"  Errors:                      {errors}")
    if error_details:
        for d in error_details[:10]:
            print(d)
        if len(error_details) > 10:
            print(f"  ... and {len(error_details)-10} more errors")
    print()

    return {
        "mode": mode,
        "updated": updated,
        "enrolled": enrolled,
        "skipped": skipped,
        "errors": errors,
    }


def _normalize_phone(phone: str) -> str:
    """E.164 normalize."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Backfill niche-specific SMS sequence types")
    p.add_argument("--live", action="store_true", help="Actually enroll/update (default: dry-run)")
    p.add_argument("--status", action="store_true", help="Show current enrollment stats only")
    args = p.parse_args()

    if args.status:
        sb = _sb()
        show_status(sb)
        sys.exit(0)

    result = run(dry_run=not args.live)
    sys.exit(0 if result["errors"] == 0 else 1)
