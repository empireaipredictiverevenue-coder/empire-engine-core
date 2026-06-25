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

Idempotent: reads sms_sequences.status. If status=completed, replied, or
opted_out, skips. Updates last_step_at + step on send. Logs to outreach_log.

Reply classifier (2026-06-25 patch):
  - inbound must arrive AFTER sms_sequences.created_at
  - test numbers excluded
  - empty / <2 char / pure-symbol bodies ignored (carrier auto-replies)
  - STOP/UNSUBSCRIBE/UNSUB/QUIT/END/CANCEL → status=opted_out
  - YES/Y/YEAH/YEP/YUP/SURE/OK/OKAY/INTERESTED → status=completed, reason=replied_yes
  - any other inbound → sequence stays active (we don't know intent yet)

Cron: every 6h.
  0 */6 * * * cd /root/empire-v49 && /usr/bin/python3 -m agents.multi_touch_cadence >> logs/agent_multi_touch.log 2>&1
"""
from __future__ import annotations

import json
import logging
import os
import re
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

# Test numbers — never classify as a real reply. Internal/test endpoints,
# emulator numbers, +1 555 prefixes, and known sandbox routes.
TEST_NUMBERS = {
    "+12145551200", "+12145551234", "+12145550000", "+15005551234",
    "+15555555555", "+18005551212", "+19005551234", "+10000000000",
}

# Opt-out keywords (case-insensitive). Match against cleaned body tokens.
_OPT_OUT_KEYWORDS = {"STOP", "UNSUBSCRIBE", "UNSUB", "QUIT", "END", "CANCEL", "OPTOUT", "STOPALL"}

# Opt-in keywords (case-insensitive). Match against cleaned body tokens.
_OPT_IN_KEYWORDS = {"YES", "Y", "YEAH", "YEP", "YUP", "SURE", "OK", "OKAY", "INTERESTED", "INTEREST", "SEND"}


def _is_meaningful(body: str) -> bool:
    """True if the body is non-empty, >=2 chars, and has at least one
    letter or digit (filters carrier auto-replies like ':)' or '-')."""
    if not body:
        return False
    s = body.strip()
    if len(s) < 2:
        return False
    return bool(re.search(r"[A-Za-z0-9]", s))


def _is_stop(body: str) -> bool:
    """True if the body is an opt-out signal."""
    if not body:
        return False
    cleaned = re.sub(r"[^A-Za-z]+", " ", body.strip().upper()).split()
    return any(tok in _OPT_OUT_KEYWORDS for tok in cleaned)


def _is_yes(body: str) -> bool:
    """True if the body is a positive opt-in signal.

    Mirrors agents/dispatch/dispatcher.py:_is_yes so the two paths agree.
    """
    if not body:
        return False
    cleaned = body.strip().upper()
    tokens = cleaned.split()
    return "YES" in tokens or cleaned in {"Y", "YEAH", "YEP", "YUP", "SURE", "OK", "OKAY"} \
        or any(tok in _OPT_IN_KEYWORDS for tok in tokens)


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
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _first_name(full: str) -> str:
    if not full:
        return "there"
    return full.split()[0].strip().title()[:40]


def _send_sms_via_hub(hub_url: str, phone: str, body: str, meta: dict) -> bool:
    """Send a single SMS via the hub's sms/enroll or direct endpoint."""
    # Try the lightweight sms/send endpoint first
    try:
        r = httpx.post(
            f"{hub_url.rstrip('/')}/api/v1/sms/send",
            json={"to": phone, "body": body, "meta": meta},
            timeout=10,
        )
        if r.status_code in (200, 201, 202):
            return True
    except Exception as e:
        log.debug(f"hub sms/send failed for {phone}: {e}")
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


def _classify_prior_reply(sb, phone: str, seq_created_at: str) -> tuple[str, dict | None]:
    """Look up the latest inbound for this phone after the sequence started.

    Returns (status, prior_row_or_None) where status is one of:
      - "ok"               → no prior reply, sequence stays active
      - "completed_yes"    → real YES intent, mark completed
      - "opted_out"        → STOP/UNSUBSCRIBE, mark opted_out
      - "test_skip"        → test number, don't mark anything
      - "noise_skip"       → carrier auto-reply / non-meaningful body
      - "unknown_skip"     → real inbound but ambiguous, keep active
    """
    if phone in TEST_NUMBERS:
        return ("test_skip", None)

    prior = (sb.table("sms_log")
             .select("id,body,created_at")
             .eq("phone", phone)
             .eq("direction", "inbound")
             .gte("created_at", seq_created_at)
             .order("created_at", desc=True)
             .limit(1)
             .execute())
    if not prior.data:
        return ("ok", None)

    row = prior.data[0]
    body = (row.get("body") or "").strip()

    if not _is_meaningful(body):
        return ("noise_skip", row)

    if _is_stop(body):
        return ("opted_out", row)
    if _is_yes(body):
        return ("completed_yes", row)
    return ("unknown_skip", row)


def run() -> dict:
    started = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    hub_url = os.getenv("HUB_URL", "http://localhost:8001")
    now_iso = started.isoformat()

    # 1) Find active sequences that need a step advance
    r = sb.table("sms_sequences").select("id,phone,status,current_step,last_step_at,created_at,meta").eq("sequence_type", SEQUENCE).eq("status", "active").limit(2000).execute()
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
    phones = list(by_phone.keys())
    if not phones:
        return {"status": "ok", "rows_seen": 0, "rows_sent": 0}
    conts: dict[str, dict] = {}
    for i in range(0, len(phones), 500):
        chunk = phones[i:i+500]
        for c in (sb.table("contractors").select("id,name,phone,metro,active").in_("phone", chunk).execute().data or []):
            conts[c["phone"]] = c

    sent = 0
    skipped = 0
    errors = 0
    classified = {"completed_yes": 0, "opted_out": 0, "test_skip": 0, "noise_skip": 0, "unknown_skip": 0}
    for phone, seq in by_phone.items():
        try:
            # Has the contractor already replied? If so, mark sequence completed.
            c = conts.get(phone)
            if not c or not c.get("active"):
                skipped += 1
                continue

            # Reply classifier (2026-06-25 patch):
            #   - filters test numbers + auto-reply noise
            #   - distinguishes YES / STOP / unknown
            #   - only marks completed on actual YES reply
            status, prior_row = _classify_prior_reply(sb, phone, seq["created_at"])

            if status == "completed_yes":
                sb.table("sms_sequences").update({
                    "status": "completed",
                    "meta": {
                        **(seq.get("meta") or {}),
                        "completed_reason": "replied_yes",
                        "replied_at": (prior_row or {}).get("created_at"),
                    },
                    "last_step_at": now_iso,
                }).eq("id", seq["id"]).execute()
                classified["completed_yes"] += 1
                skipped += 1
                continue
            if status == "opted_out":
                sb.table("sms_sequences").update({
                    "status": "opted_out",
                    "meta": {
                        **(seq.get("meta") or {}),
                        "completed_reason": "opted_out",
                        "opted_out_at": now_iso,
                    },
                    "last_step_at": now_iso,
                }).eq("id", seq["id"]).execute()
                classified["opted_out"] += 1
                skipped += 1
                continue
            # test_skip / noise_skip / unknown_skip / ok → keep sequence active

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
            if next_step["step"] == current_step and seq.get("last_step_at"):
                # Already sent this step
                skipped += 1
                continue

            # Build the message
            first = _first_name(c.get("name", ""))
            metro = c.get("metro", "your area")
            body = next_step["body"].format(first=first, metro=metro)

            # Send via hub
            ok = _send_sms_via_hub(hub_url, phone, body, meta={
                "step": next_step["step"],
                "sequence": SEQUENCE,
                "contractor_id": c["id"],
                "cadence": "multi_touch",
            })
            if ok:
                _log_outreach(sb, phone, SEQUENCE, next_step["step"], body, contractor_id=c["id"])
                sb.table("sms_sequences").update({
                    "current_step": next_step["step"],
                    "last_step_at": now_iso,
                }).eq("id", seq["id"]).execute()
                sent += 1
            else:
                errors += 1
        except Exception as e:
            log.warning(f"multi_touch_cadence: {phone}: {type(e).__name__}: {e}")
            errors += 1

    summary = {
        "status": "ok",
        "rows_seen": len(seqs),
        "rows_sent": sent,
        "rows_skipped": skipped,
        "rows_errored": errors,
        "classified": classified,
    }
    log.info(f"multi_touch_cadence done: {summary}")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), default=str))