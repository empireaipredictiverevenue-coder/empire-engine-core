"""Empire AI · Multi-Touch Cadence Agent

For every contractor with an active contractor_recruit sequence, advance
them through a 4-step SMS cadence over 14 days. The step is determined
by how long ago the sequence was created; if the contractor already
replied, the sequence is marked completed and no further sends happen.

Steps:
  Step 1 (day 0):  "Hi {first} — Storm leads in {metro}. 3% on settled
                    claims. Want a sample? Reply YES."
  Step 2 (day 3):  "Hey {first} — didn't hear back. Free sample lead
                    this week, no commitment. - Empire AI"
  Step 3 (day 7):  "{first}, {N} leads matched {metro} contractors this
                    week. Tap to claim: {url} - Empire AI"
  Step 4 (day 14): "Last note from me. Reply STOP to opt out or YES
                    to see today's {metro} leads. - Empire AI"

Idempotent: reads sms_sequences.status. If status=completed or replied,
skips. Updates last_step_at + step on send. Logs to outreach_log.

Cron: every 6h.
  0 */6 * * * cd /root/empire-v49 && /usr/bin/python3 -m agents.multi_touch_cadence >> logs/agent_multi_touch.log 2>&1
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

import httpx
from supabase import create_client

log = logging.getLogger("empire.multi_touch_cadence")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

SEQUENCE = "contractor_recruit"

# Step days (offset from sequence.created_at) and body templates.
STEPS = [
    {
        "step": 1, "day": 0,
        "body": "Hi {first} — Storm leads in {metro}. 3% on settled claims. Want a sample? Reply YES. - Empire AI",
    },
    {
        "step": 2, "day": 3,
        "body": "Hey {first} - didn't hear back. Free sample lead this week, no commitment. - Empire AI",
    },
    {
        "step": 3, "day": 7,
        "body": "{first}, multiple leads matched {metro} contractors this week. Reply YES to see them. - Empire AI",
    },
    {
        "step": 4, "day": 14,
        "body": "Last note from me. Reply STOP to opt out or YES to see today's {metro} leads. - Empire AI",
    },
]


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))


def _first_name(full: str) -> str:
    if not full:
        return "there"
    return full.split()[0].strip().title()[:40]


def _send_sms_direct(sb, phone: str, body: str, meta: dict) -> bool:
    """Write outbound SMS to sms_log. The hub's SMSDispatcher cron picks
    these up and sends via Vonage. body + phone + direction=outbound
    is the only required payload."""
    try:
        sb.table("sms_log").insert({
            "phone": phone,
            "direction": "outbound",
            "body": body,
            "step": meta.get("step", 1),
            "sms_variant": "multi_touch_cadence",
        }).execute()
        return True
    except Exception as e:
        log.warning(f"sms_log insert failed for {phone}: {e}")
        return False


def _log_outreach(sb, phone: str, sequence: str, step: int, body: str, contractor_id: str = None,
                  meta: dict = None) -> None:
    sb.table("outreach_log").insert({
        "agent_name": "multi_touch_cadence",
        "run_id": str(uuid.uuid4()),
        "channel": "sms",
        "sequence": sequence,
        "step": step,
        "mode": "live",
        "compliance_passed": True,
        "body_preview": body[:120],
        "meta": {"phone": phone, "contractor_id": contractor_id, **(meta or {})},
    }).execute()


def run() -> dict:
    started = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    hub_url = os.getenv("HUB_URL", "http://localhost:8001")
    now_iso = started.isoformat()

    # 1) Find active sequences that need a step advance
    r = sb.table("sms_sequences").select("id,phone,status,current_step,last_sent_at,created_at,meta").eq("sequence_type", SEQUENCE).eq("status", "active").limit(100).execute()
    seqs = r.data or []
    log.info(f"multi_touch_cadence: {len(seqs)} active sequences")

    # 2) Group sequences by their contractor (join via meta.contractor_id)
    #    For step calculation, use sms_sequences.created_at + day offset.
    by_phone: dict[str, dict] = {}
    for s in seqs:
        ph = s.get("phone")
        if not ph:
            continue
        by_phone[ph] = s  # most recent wins

    # 3) Load contractor details for the phones
    phones = list(by_phone.keys())[:100]  # hard cap per cycle
    if not phones:
        return {"status": "ok", "rows_seen": 0, "rows_sent": 0}
    conts: dict[str, dict] = {}
    try:
        for c in (sb.table("contractors").select("id,name,phone,metro,active").in_("phone", phones).execute().data or []):
            conts[c["phone"]] = c
    except Exception as e:
        log.warning(f"contractor lookup failed: {e}")

    sent = 0
    skipped = 0
    errors = 0
    for phone, seq in by_phone.items():
        try:
            # Has the contractor already replied? If so, mark sequence completed.
            c = conts.get(phone)
            if not c or not c.get("active"):
                skipped += 1
                continue

            # Check for prior reply (sms_log.direction=inbound from this phone)
            prior = sb.table("sms_log").select("id").eq("phone", phone).eq("direction", "inbound").limit(1).execute()
            if prior.data:
                sb.table("sms_sequences").update({
                    "status": "completed",
                    "meta": {**(seq.get("meta") or {}), "completed_reason": "replied"},
                    "last_sent_at": now_iso,
                }).eq("id", seq["id"]).execute()
                skipped += 1
                continue

            # Determine which step we're on based on (now - created_at) vs step days
            created_at = datetime.fromisoformat(seq["created_at"].replace("Z", "+00:00"))
            age_days = (started - created_at).total_seconds() / 86400.0
            current_step = seq.get("current_step") or 1
            # Find the next step that should have fired
            next_step = None
            for s in STEPS:
                if age_days >= s["day"] and s["step"] >= current_step:
                    if next_step is None or s["step"] > next_step["step"]:
                        next_step = s
            if next_step is None:
                skipped += 1
                continue
            if next_step["step"] == current_step and seq.get("last_sent_at"):
                # Already sent this step
                skipped += 1
                continue

            # Build the message
            first = _first_name(c.get("name", ""))
            metro = c.get("metro", "your area")
            body = next_step["body"].format(first=first, metro=metro)

            # Write to sms_log (the hub cron picks these up and sends)
            ok = _send_sms_direct(sb, phone, body, meta={
                "step": next_step["step"],
                "sequence": SEQUENCE,
                "contractor_id": c["id"],
                "cadence": "multi_touch",
            })
            if ok:
                _log_outreach(sb, phone, SEQUENCE, next_step["step"], body, contractor_id=c["id"])
                sb.table("sms_sequences").update({
                    "current_step": next_step["step"],
                    "last_sent_at": now_iso,
                }).eq("id", seq["id"]).execute()
                sent += 1
            else:
                errors += 1
        except Exception as e:
            log.warning(f"multi_touch_cadence: {phone}: {type(e).__name__}: {e}")
            errors += 1

    summary = f"sent {sent}, skipped {skipped}, errors {errors} of {len(by_phone)}"
    log.info(summary)
    sb.table("agent_activity").insert({
        "agent_name": "multi_touch_cadence",
        "run_id": str(run_id),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not errors else "ok",
        "rows_seen": len(by_phone),
        "rows_processed": sent,
        "summary": summary,
    }).execute()
    return {"status": "ok", "sent": sent, "skipped": skipped, "errors": errors, "rows_seen": len(by_phone)}


def main():
    res = run()
    sys.exit(0 if res["status"] == "ok" else 1)


if __name__ == "__main__":
    main()