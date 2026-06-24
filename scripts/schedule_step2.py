"""
Empire AI · Schedule Step 2 for tier_intro
==========================================

Promote all `sent` step-1 rows to `pending` step-2 with `next_send_at = +3d`,
so the daily 10am cron (scripts/contractor_outreach.py send) picks them up.

Use this after manually sending step 1 (e.g. one-off batch) to bridge into
the cron-driven cadence.

Idempotent: only updates rows currently at step=1 status=sent.

Usage:
    python3 scripts/schedule_step2.py
"""
import os
from datetime import datetime, timezone, timedelta
from supabase import create_client
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass


def schedule_step2(sequence: str = "tier_intro", delay_days: int = 3) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    now = datetime.now(timezone.utc)
    send_at = now + timedelta(days=delay_days)

    # All step-1 sent rows for this sequence
    r = sb.table("contractor_outreach").select("id").eq(
        "sequence", sequence).eq("step", 1).eq("status", "sent").execute().data or []
    updated = 0
    failed = 0
    for row in r:
        try:
            sb.table("contractor_outreach").update({
                "step": 2,
                "status": "pending",
                "next_send_at": send_at.isoformat(),
                "notes": f"step 2 auto-scheduled at {now.isoformat()}",
            }).eq("id", row["id"]).execute()
            updated += 1
        except Exception as e:
            failed += 1
            print(f"  err {row['id'][:8]}: {e}")
    print(f"sequence={sequence}  step 1 sent: {len(r)}  → step 2 pending scheduled for {send_at.isoformat()}")
    print(f"updated: {updated}  failed: {failed}")
    return {"updated": updated, "failed": failed, "scheduled_for": send_at.isoformat()}


if __name__ == "__main__":
    schedule_step2()