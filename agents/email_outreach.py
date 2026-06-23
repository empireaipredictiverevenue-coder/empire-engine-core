"""Build agents/email_outreach.py — Resend-based email sequence.
Targets the 5 contractors with real emails + any future ones.
3-step sequence: intro (day 0), value-add (day 3), last-call (day 7).
"""
import os
import re
import sys
import json
import uuid
import time
import logging
import urllib.request
import urllib.error
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

from supabase import create_client

log = logging.getLogger("empire.email_outreach")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

RESEND_API = "https://api.resend.com/emails"
SEQUENCE = "contractor_recruit_email"
FROM_ADDR = "Empire AI <ops@empire-ai.co.uk>"


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _send_email(api_key: str, to: str, subject: str, html: str) -> dict:
    try:
        req = urllib.request.Request(
            RESEND_API,
            data=json.dumps({
                "from": FROM_ADDR,
                "to": [to],
                "subject": subject,
                "html": html,
            }).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
            return {"ok": True, "id": body.get("id")}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except Exception:
            err = {"raw": str(e)}
        return {"ok": False, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _email_valid(e: str) -> bool:
    if not e or "@" not in e:
        return False
    if e.startswith("__quarantine__"):
        return False
    if e.endswith("@pending.real-email"):
        return False
    if "@placeholder" in e or "@example" in e or "@empire-ai.placeholder" in e:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e))


# 3-step cadence (matches the SMS multi_touch_cadence)
STEPS = [
    {
        "step": 1, "day": 0,
        "subject_template": "Storm leads in {metro} — 3% on settled claims only",
        "body_template": """
        <p>Hi {first},</p>
        <p>Empire AI is routing <b>storm-damage leads</b> in {metro} to one local contractor per metro. You pay <b>3% on settled claims only</b> — no per-lead fees, no contracts.</p>
        <p>If you're licensed and active in {metro}, reply <b>YES</b> to get a sample lead this week.</p>
        <p>— Empire AI<br><a href="https://empire-ai.co.uk/for-roofing">View our roof leads</a></p>
        """,
    },
    {
        "step": 2, "day": 3,
        "subject_template": "{metro} storm leads — free sample this week",
        "body_template": """
        <p>Hi {first},</p>
        <p>Following up — we have storm-targeted leads in {metro} this week, no commitment. Reply <b>YES</b> for a free sample.</p>
        <p>— Empire AI</p>
        """,
    },
    {
        "step": 3, "day": 7,
        "subject_template": "Last note — {metro} leads",
        "body_template": """
        <p>Hi {first},</p>
        <p>Last note from me. If you ever want leads in {metro}, reply <b>YES</b>. Or reply <b>STOP</b> to opt out.</p>
        <p>— Empire AI</p>
        """,
    },
]


def _first_name(full: str) -> str:
    if not full:
        return "there"
    return full.split()[0].strip().title()[:40]


def _is_synthetic_email(e: str) -> bool:
    if not e:
        return True
    bad = ["__quarantine__", "pending.real-email", "@placeholder", "@example",
           "@empire-ai.placeholder", "test@", "noreply@", "info@<slug>"]
    return any(b in e for b in bad)


def _cooldown_ok(sb, contractor_id: str, step: int) -> bool:
    """Don't re-send the same step within 48h."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    r = sb.table("email_outreach_log").select("id,step,fired_at").eq("contractor_id", contractor_id).eq("step", step).gte("fired_at", cutoff).limit(1).execute()
    return not (r.data or [])


def _log_send(sb, contractor_id: str, step: int, status: str, detail: str = "", email_id: str = "") -> None:
    try:
        sb.table("email_outreach_log").insert({
            "contractor_id": contractor_id,
            "step": step,
            "status": status,
            "resend_id": email_id,
            "detail": detail[:500],
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning(f"email_outreach log insert failed: {e}")


def run() -> dict:
    started = datetime.now(timezone.utc)
    api_key = os.environ.get("RESEND_AFFILIATE_KEY") or os.environ.get("RESEND_API_KEY")
    if not api_key:
        return {"status": "error", "error": "no resend key", "sent": 0}

    sb = _sb()

    # 1) Find active contractors with valid emails
    r = sb.table("contractors").select("id,name,email,metro,phone").eq("active", True).limit(7000).execute()
    candidates = [c for c in (r.data or []) if _email_valid(c.get("email", "")) and not _is_synthetic_email(c.get("email", ""))]
    log.info(f"email_outreach: {len(candidates)} contractors with valid email")

    # 2) Find which sequences already exist
    sent_count = 0
    skipped = 0
    errors = 0
    for c in candidates:
        cid = c["id"]
        # Check if replied (any inbound email via the webhook)
        try:
            rr = sb.table("email_replies").select("id").eq("contractor_id", cid).limit(1).execute()
            if rr.data:
                skipped += 1
                continue
        except Exception:
            pass
        # Determine which step to send
        seq = sb.table("email_sequences").select("id,current_step,last_sent_at,created_at").eq("contractor_id", cid).eq("sequence_type", SEQUENCE).execute()
        seq_rows = seq.data or []
        # Find next step based on age
        for st in STEPS:
            if _cooldown_ok(sb, cid, st["step"]):
                # Check if this step was already sent
                existing = [r for r in seq_rows if r.get("current_step") == st["step"]]
                if existing:
                    continue  # already sent
                # Check elapsed time vs step day
                if seq_rows:
                    created_at = datetime.fromisoformat(seq_rows[0]["created_at"].replace("Z", "+00:00").split(".")[0])
                    age_days = (started - created_at).total_seconds() / 86400
                    if age_days < st["day"]:
                        continue
                # Build + send
                first = _first_name(c.get("name", ""))
                metro = c.get("metro") or "your area"
                subject = st["subject_template"].format(first=first, metro=metro)
                body = st["body_template"].format(first=first, metro=metro)
                res = _send_email(api_key, c["email"], subject, body)
                status = "ok" if res.get("ok") else "failed"
                _log_send(sb, cid, st["step"], status, detail=str(res.get("error", ""))[:300] if not res.get("ok") else "", email_id=res.get("id", ""))
                if res.get("ok"):
                    sent_count += 1
                    # Insert/update sequence row
                    if seq_rows:
                        sb.table("email_sequences").update({
                            "current_step": st["step"],
                            "last_sent_at": started.isoformat(),
                        }).eq("id", seq_rows[0]["id"]).execute()
                    else:
                        sb.table("email_sequences").insert({
                            "contractor_id": cid,
                            "sequence_type": SEQUENCE,
                            "email": c["email"],
                            "target_addr": c["email"],
                            "current_step": st["step"],
                            "status": "active",
                            "last_sent_at": started.isoformat(),
                            "created_at": started.isoformat(),
                        }).execute()
                else:
                    errors += 1

    summary = f"sent={sent_count} skipped={skipped} errors={errors} of {len(candidates)}"
    log.info(summary)
    sb.table("agent_activity").insert({
        "agent_name": "email_outreach",
        "run_id": str(uuid.uuid4()),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if errors == 0 else "ok",
        "rows_seen": len(candidates),
        "rows_processed": sent_count,
        "summary": summary,
    }).execute()
    return {"status": "ok", "sent": sent_count, "skipped": skipped, "errors": errors, "candidates": len(candidates)}


def main():
    res = run()
    sys.exit(0 if res["status"] == "ok" else 1)


if __name__ == "__main__":
    main()