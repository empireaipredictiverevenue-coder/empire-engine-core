"""
Empire AI · Outreach Retry
=============================

Retries pending outreach rows that failed to send (resend errors, network
blips, etc). Uses exponential backoff: skip rows whose last attempt was
less than `min_retry_hours` ago.

Cron: */30 * * * * (every 30 min, light load)
"""
import os, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

now = datetime.now(timezone.utc)
MIN_RETRY_HOURS = 1  # skip if last attempt <1h ago
MAX_BATCH = 50


def retry_pending(limit: int = MAX_BATCH):
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # Find pending rows. last_sent_at is null for ones that never sent.
    # Filter out rows attempted in the last hour.
    cutoff = (now - timedelta(hours=MIN_RETRY_HOURS)).isoformat()
    r = sb.table("contractor_outreach").select("id,contractor_id,sequence,step,last_sent_at").eq("status", "pending").or_(f"last_sent_at.is.null,last_sent_at.lt.{cutoff}").limit(limit).execute()
    rows = r.data or []
    if not rows:
        print("no pending rows to retry")
        return {"retried": 0}

    # The contractor_outreach send function lives in scripts/contractor_outreach.py
    # We import it here. If it fails to import, we fall back to direct resend.
    try:
        sys.path.insert(0, "/root/empire-v49")
        from scripts.contractor_outreach import _send_resend, TEMPLATES, _first_name, PRICING_URL
    except ImportError as e:
        print(f"failed to import scripts.contractor_outreach: {e}")
        return {"error": "import"}

    # Build contractor lookup
    ids = list({row["contractor_id"] for row in rows})
    conts = {c["id"]: c for c in (sb.table("contractors").select("id,name,email").in_("id", ids).execute().data or [])}

    sent = 0
    errors = 0
    for row in rows:
        c = conts.get(row["contractor_id"])
        if not c or not c.get("email"):
            continue
        seq_tmpl = TEMPLATES.get(row["sequence"], {})
        step_tmpl = seq_tmpl.get(row["step"])
        if not step_tmpl:
            continue
        attributed_url = f"{PRICING_URL}?outreach_id={row['id']}&cid={row['contractor_id']}"
        subject = step_tmpl["subject"]
        body = step_tmpl["body"].format(first=_first_name(c.get("name")), url=attributed_url)
        r = _send_resend(c["email"], subject, body, outreach_id=row["id"])
        if r.get("ok"):
            advance_hours = {"tier_intro": {1: 72, 2: 96, 3: 168, 4: None},
                             "tier_nudge": {1: 72, 2: None},
                             "final_push": {1: None}}[row["sequence"]][row["step"]]
            update = {
                "status": "sent",
                "last_sent_at": now.isoformat(),
                "next_send_at": (now + timedelta(hours=advance_hours)).isoformat() if advance_hours else None,
                "step": row["step"] + 1 if advance_hours else row["step"],
                "updated_at": now.isoformat(),
            }
            sb.table("contractor_outreach").update(update).eq("id", row["id"]).execute()
            sent += 1
        else:
            errors += 1
            sb.table("contractor_outreach").update({
                "last_sent_at": now.isoformat(),  # record attempt time
            }).eq("id", row["id"]).execute()
    print(f"retried {sent}, errors {errors}")
    return {"retried": sent, "errors": errors}


if __name__ == "__main__":
    retry_pending()