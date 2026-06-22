"""
Empire AI · Auto-Nudge Enrollment
====================================

Cron: runs daily after the main outreach send. Finds two segments:

  A. Opened-but-didn't-click, last_send_at > 3 days ago
     → enroll in tier_nudge sequence step 1

  B. Clicked-but-didn't-activate, last_send_at > 7 days ago
     → enroll in tier_nudge sequence step 2 (the harder-sell)

The tier_nudge templates are already in scripts/contractor_outreach.py.
This script just creates the contractor_outreach rows; the main
process_pending_sends picks them up and sends.

Cron: 30 10 * * * (after the 10am send runs)
"""
import os, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

now = datetime.now(timezone.utc)


def enroll_nudges():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # Segment A: opened-not-clicked, sent > 3 days ago, not already in tier_nudge
    three_days_ago = (now - timedelta(days=3)).isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # Get already-enrolled in tier_nudge to avoid duplicates
    existing = sb.table("contractor_outreach").select("contractor_id,sequence").eq("sequence", "tier_nudge").execute().data or []
    already_nudge = {e["contractor_id"] for e in existing}

    # Find all sent tier_intro rows with opened_at but no clicked_at
    r = sb.table("contractor_outreach").select(
        "contractor_id,last_sent_at,opened_at,clicked_at"
    ).eq("sequence", "tier_intro").eq("status", "sent").lt("last_sent_at", three_days_ago).not_.is_("opened_at", "null").execute()
    seg_a = []
    for row in (r.data or []):
        if row.get("clicked_at"):
            continue  # already clicked → not segment A
        if row["contractor_id"] in already_nudge:
            continue
        seg_a.append(row["contractor_id"])

    # Find all sent tier_intro rows with clicked_at but no paid_at, sent > 7 days ago
    r = sb.table("contractor_outreach").select(
        "contractor_id,last_sent_at,clicked_at,paid_at"
    ).eq("sequence", "tier_intro").eq("status", "sent").lt("last_sent_at", seven_days_ago).not_.is_("clicked_at", "null").is_("paid_at", "null").execute()
    seg_b = []
    for row in (r.data or []):
        if row["contractor_id"] in already_nudge:
            continue
        seg_b.append(row["contractor_id"])

    # Enroll seg_a in tier_nudge step 1, seg_b in tier_nudge step 2
    to_insert = []
    for cid in seg_a:
        to_insert.append({
            "contractor_id": cid,
            "sequence": "tier_nudge",
            "step": 1,
            "status": "pending",
            "next_send_at": now.isoformat(),
            "notes": f"opened-no-click → nudge step 1 ({now.isoformat()})",
        })
    for cid in seg_b:
        to_insert.append({
            "contractor_id": cid,
            "sequence": "tier_nudge",
            "step": 2,
            "status": "pending",
            "next_send_at": now.isoformat(),
            "notes": f"clicked-no-pay → nudge step 2 ({now.isoformat()})",
        })

    inserted = 0
    if to_insert:
        # batch insert in chunks of 100
        for i in range(0, len(to_insert), 100):
            sb.table("contractor_outreach").insert(to_insert[i:i+100]).execute()
            inserted += len(to_insert[i:i+100])

    print(f"seg_a (opened-no-click, >3d): {len(seg_a)} enrolled in tier_nudge step 1")
    print(f"seg_b (clicked-no-pay, >7d):    {len(seg_b)} enrolled in tier_nudge step 2")
    print(f"total inserted: {inserted}")
    return {"seg_a": len(seg_a), "seg_b": len(seg_b), "inserted": inserted}


if __name__ == "__main__":
    enroll_nudges()