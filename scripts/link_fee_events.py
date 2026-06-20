#!/usr/bin/env python3
"""
EMPIRE V49 · LINK FEE EVENTS TO CONTRACTORS
=============================================

Queries all fee_events, cross-references dispatches → contractors to resolve
names, phones, and emails, and:
  - Backfills any missing contractor_id / contact info into fee_event.meta
  - Prints a summary table showing fee_amount | contractor | phone | email | status
  - Reports orphaned records that can't be resolved

Usage:
    python3 scripts/link_fee_events.py                 # report + backfill
    python3 scripts/link_fee_events.py --dry-run        # report only, no writes
    python3 scripts/link_fee_events.py --report-only    # report only, no writes
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("link_fee_events")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _resolve_contractor(sb, cid: str) -> Optional[dict]:
    """Look up a contractor by ID and return name, phone, email."""
    try:
        r = sb.table("contractors").select("name, phone, email").eq("id", cid).limit(1).execute()
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return None


def _resolve_dispatch(sb, did: str) -> Optional[dict]:
    """Look up a dispatch by ID and return contractor_id."""
    try:
        r = sb.table("dispatches").select("contractor_id, lead_id").eq("id", did).limit(1).execute()
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return None


def run(dry_run: bool = False) -> dict:
    sb = _sb()
    started_at = datetime.now(timezone.utc)

    # ── 1. Fetch all fee_events ────────────────────────────────────────
    r = sb.table("fee_events").select("*").order("created_at", desc=True).limit(500).execute()
    fee_events = r.data or []
    total = len(fee_events)

    # ── 2. Process each fee_event ──────────────────────────────────────
    orphaned = []
    linked = []
    backfilled = 0
    already_complete = 0

    for fe in fee_events:
        fee_id = fe["id"]
        fee_amount = fe.get("fee_amount", 0)
        claim_amount = fe.get("claim_amount", 0)
        status = fe.get("status", "?")
        source = fe.get("source", "?")
        fe_meta = fe.get("meta") or {}
        if isinstance(fe_meta, str):
            try:
                fe_meta = json.loads(fe_meta)
            except Exception:
                fe_meta = {}

        # Check if meta already has contractor contact info
        has_contact = bool(
            fe_meta.get("contractor_name") or fe_meta.get("contractor_phone")
        )

        # Try to resolve contractor info
        cid = fe.get("contractor_id")
        contractor_info = None

        if cid:
            # Direct lookup by contractor_id
            contractor_info = _resolve_contractor(sb, cid)
        else:
            # Try via dispatch_id in meta
            dispatch_id = fe_meta.get("dispatch_id") if isinstance(fe_meta, dict) else None
            if dispatch_id:
                dispatch = _resolve_dispatch(sb, dispatch_id)
                if dispatch:
                    cid = dispatch.get("contractor_id")
                    if cid:
                        contractor_info = _resolve_contractor(sb, cid)

        if contractor_info:
            name = contractor_info.get("name") or "?"
            phone = contractor_info.get("phone") or ""
            email = contractor_info.get("email") or ""

            linked.append({
                "fee_id": fee_id,
                "fee_amount": fee_amount,
                "claim_amount": claim_amount,
                "status": status,
                "source": source,
                "contractor_name": name,
                "contractor_phone": phone,
                "contractor_email": email,
                "contractor_id": cid,
            })

            # Backfill contractor contact info into fee_event meta if missing
            if not has_contact and not dry_run:
                try:
                    updated_meta = dict(fe_meta)
                    updated_meta["contractor_name"] = name
                    updated_meta["contractor_phone"] = phone
                    updated_meta["contractor_email"] = email
                    if cid:
                        updated_meta["resolved_contractor_id"] = cid
                    sb.table("fee_events").update(
                        {"meta": updated_meta}
                    ).eq("id", fee_id).execute()
                    backfilled += 1
                except Exception as e:
                    log.warning(f"  backfill failed for {fee_id[:12]}: {e}")
            elif has_contact:
                already_complete += 1
        else:
            orphaned.append({
                "fee_id": fee_id,
                "fee_amount": fee_amount,
                "claim_amount": claim_amount,
                "status": status,
                "source": source,
                "contractor_id": cid,
                "meta": fe_meta,
            })

    # ── 3. Print report ────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    print(f"\n{'='*80}")
    print(f"  FEE EVENT → CONTRACTOR LINKAGE REPORT")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Mode: {'DRY RUN (no writes)' if dry_run else 'LIVE (backfilling)'}")
    print(f"{'='*80}\n")

    # Summary header
    total_fees = sum(f["fee_amount"] for f in fee_events)
    linked_fees = sum(f["fee_amount"] for f in linked)
    orphaned_fees = sum(f["fee_amount"] for f in orphaned)

    print(f"  Total fee_events:   {total}")
    print(f"  Linked:             {len(linked)}  (${linked_fees:,.2f})")
    print(f"  Orphaned:           {len(orphaned)}  (${orphaned_fees:,.2f})")
    print(f"  Already complete:   {already_complete}")
    print(f"  Backfilled:         {backfilled}")
    print(f"  Time:               {elapsed:.1f}s")
    print()

    # Linked table
    if linked:
        print(f"  {'Fee ID':<14} {'Contractor':<28} {'Phone':<16} {'Fee':>10} {'Status':<10}")
        print(f"  {'-'*14} {'-'*28} {'-'*16} {'-'*10} {'-'*10}")
        for row in sorted(linked, key=lambda x: -x["fee_amount"]):
            fid = row["fee_id"][:12]
            name = (row["contractor_name"] or "?")[:26]
            phone = (row["contractor_phone"] or "—")[:14]
            fee_fmt = f"${row['fee_amount']:,.0f}"
            stat = row["status"][:8]
            print(f"  {fid:<14} {name:<28} {phone:<16} {fee_fmt:>10} {stat:<10}")
        print()

    # Orphaned section
    if orphaned:
        print(f"  ⚠️  ORPHANED FEE EVENTS — no contractor info found:\n")
        print(f"  {'Fee ID':<14} {'Fee':>10} {'Source':<22} {'Status':<10}  Notes")
        print(f"  {'-'*14} {'-'*10} {'-'*22} {'-'*10}  {'-'*30}")
        for row in orphaned:
            fid = row["fee_id"][:12]
            fee_fmt = f"${row['fee_amount']:,.0f}"
            src = row["source"][:20]
            stat = row["status"][:8]
            meta = row.get("meta") or {}
            notes = ""
            if meta.get("test"):
                notes = "test data — no contractor linkage"
            elif isinstance(meta, dict) and meta.get("dispatch_id"):
                notes = f"dispatch={meta.get('dispatch_id','')[:12]} not found"
            else:
                notes = "no dispatch_id to cross-reference"
            print(f"  {fid:<14} {fee_fmt:>10} {src:<22} {stat:<10}  {notes}")
        print()
        print(f"  → These cannot be resolved without manual intervention.")
        print(f"    Recommended: Delete test records, mark small orphans as write-offs.\n")

    return {
        "total": total,
        "linked": len(linked),
        "orphaned": len(orphaned),
        "already_complete": already_complete,
        "backfilled": backfilled,
        "total_fees_usd": round(total_fees, 2),
        "linked_fees_usd": round(linked_fees, 2),
        "orphaned_fees_usd": round(orphaned_fees, 2),
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 1),
        "orphaned_records": [
            {"fee_id": o["fee_id"], "fee_amount": o["fee_amount"], "source": o["source"], "status": o["status"]}
            for o in orphaned
        ],
    }


def main():
    import argparse
    p = argparse.ArgumentParser(description="Link fee_events to contractor contact info")
    p.add_argument("--dry-run", action="store_true", help="Report only — no backfill writes")
    p.add_argument("--report-only", action="store_true", help="Alias for --dry-run")
    args = p.parse_args()

    dry = args.dry_run or args.report_only
    result = run(dry_run=dry)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
