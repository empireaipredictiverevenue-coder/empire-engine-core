"""
Empire AI · Fee Urgency Push
============================

For pending fees with discount_expires_at in the next 24h: send a final-chance
SMS+email. Marks the fee so we don't re-push.

Cron (every hour):
  0 * * * * /usr/bin/python3 /root/empire-v49/scripts/fee_urgency_push.py >> /root/empire-v49/logs/fee_urgency_push.log 2>&1

Tone rule (operator-style): direct, human, slightly urgent. No "Congratulations"
or AI-polished language. Numbers up front, deadline up top.
"""
import os, sys, json, asyncio, logging, time, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx, jwt as pyjwt
from supabase import create_client

log = logging.getLogger("fee_urgency_push")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
URGENCY_WINDOW_HOURS = 24  # push when expires within this
MARKER_KEY = "urgency_pushed_at"


def _send_vonage_sms(to: str, body: str) -> dict:
    """Send SMS via Vonage Messages API (JWT auth, same as push_discount_sms.py)."""
    app_id = os.environ.get("VONAGE_APPLICATION_ID", "")
    key_path = os.environ.get("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    from_number = os.environ.get("VONAGE_NUMBER", "12142277528").lstrip("+")
    if not (app_id and os.path.exists(key_path)):
        return {"ok": False, "error": "vonage creds missing"}
    with open(key_path) as f:
        private_key = f.read()
    now = int(time.time())
    token = pyjwt.encode(
        {"iat": now, "exp": now + 180, "jti": str(uuid.uuid4()), "application_id": app_id},
        private_key, algorithm="RS256",
    )
    msg = {"from": from_number, "to": to.lstrip("+"),
           "message_type": "text", "text": body[:1000], "channel": "sms"}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post("https://api.nexmo.com/v1/messages",
                json=msg,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        return {"ok": r.status_code < 400, "status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _send_resend_email(to: str, subject: str, html: str) -> dict:
    """Send email via Resend."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    from_addr = os.environ.get("FROM_ADDRESS", "noreply@empire-ai.co.uk")
    if not api_key:
        return {"ok": False, "error": "RESEND_API_KEY missing"}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post("https://api.resend.com/emails",
                json={"from": f"Empire AI <{from_addr}>", "to": [to], "subject": subject, "html": html},
                headers={"Authorization": f"Bearer {api_key}"})
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _format_deadline(expires_at: str) -> str:
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        delta = exp - datetime.now(timezone.utc)
        hrs = max(0, int(delta.total_seconds() // 3600))
        if hrs <= 0:
            return "today"
        if hrs == 1:
            return "in 1 hour"
        return f"in {hrs} hours"
    except Exception:
        return "soon"


def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    now = datetime.now(timezone.utc)
    window_end = (now + timedelta(hours=URGENCY_WINDOW_HOURS)).isoformat()

    # Pending fees with active discount expiring within the window, not yet pushed.
    fees = sb.table("fee_events").select(
        "id,claim_id,contractor_id,fee_amount,discount_amount,discount_expires_at,meta"
    ).eq("status", "pending").lte("discount_expires_at", window_end).execute().data or []
    # Filter to ones we haven't pushed yet
    pending = []
    for f in fees:
        meta = f.get("meta") or {}
        if isinstance(meta, str):
            try: meta = json.loads(meta)
            except Exception: meta = {}
        if not meta.get(MARKER_KEY):
            f["_meta"] = meta
            pending.append(f)

    log.info(f"fees expiring within {URGENCY_WINDOW_HOURS}h: {len(fees)}, un-pushed: {len(pending)}")

    sent = 0
    skipped = 0
    errors = 0
    for f in pending:
        cid = f.get("contractor_id")
        c = sb.table("contractors").select("name,phone,email").eq("id", cid).limit(1).execute().data
        if not c or not c[0].get("phone"):
            skipped += 1
            continue
        cont = c[0]
        name = cont["name"]
        first = name.split()[0]
        fee_amt = float(f["fee_amount"])
        disc_amt = float(f.get("discount_amount") or 0)
        new_total = max(0, fee_amt - disc_amt)
        deadline = _format_deadline(f.get("discount_expires_at", ""))
        claim_id = f.get("claim_id", "")

        # SMS — short, urgent, one tap
        sms = (
            f"Empire AI: {first}, {deadline} your {disc_amt:,.0f} discount expires. "
            f"Pay {new_total:,.0f} now → empire-ai.co.uk/pay/{claim_id} STOP to opt out."
        )
        # Email — same message, formatted
        subject = f"[Empire AI] {first}, your {disc_amt:,.0f} discount expires {deadline}"
        html = f"""<p>Hey {first},</p>
<p>Quick heads up: your <strong>{disc_amt:,.0f} USD discount</strong> on the {fee_amt:,.0f} USD settlement fee
expires <strong>{deadline}</strong>. After that, the fee goes back to the full {fee_amt:,.0f}.</p>
<p>Pay here (takes about 60 seconds):<br>
<a href="https://empire-ai.co.uk/pay/{claim_id}" style="display:inline-block;background:#16a34a;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:600">
Pay {new_total:,.0f} USDC now
</a></p>
<p>Wallet: <code style="font-size:12px">{VAULT_WALLET}</code></p>
<p>Reply to this email if anything's off.</p>
<p>— Empire AI</p>
<p style="font-size:11px;color:#999">Claim ID: {claim_id}</p>
"""

        # Send
        sms_r = _send_vonage_sms(cont["phone"], sms)
        em_r = _send_resend_email(cont.get("email") or "ops@empire-ai.co.uk", subject, html) \
               if cont.get("email") else {"ok": True, "skipped": "no email"}

        # Mark
        new_meta = dict(f["_meta"])
        new_meta[MARKER_KEY] = now.isoformat()
        new_meta["urgency_pushes"] = (new_meta.get("urgency_pushes") or []) + [{
            "ts": now.isoformat(),
            "sms_ok": sms_r.get("ok", False),
            "email_ok": em_r.get("ok", False),
            "deadline": f.get("discount_expires_at"),
        }]
        sb.table("fee_events").update({"meta": new_meta}).eq("id", f["id"]).execute()

        status = "OK" if (sms_r.get("ok") or em_r.get("ok")) else "FAIL"
        log.info(f"  {status} {first} {cont['phone']} ${new_total:,.0f} ({deadline})")
        if sms_r.get("ok") or em_r.get("ok"):
            sent += 1
        else:
            errors += 1

    print(json.dumps({"window_hours": URGENCY_WINDOW_HOURS,
                      "expiring_total": len(fees),
                      "unpushed": len(pending),
                      "sent": sent, "skipped": skipped, "errors": errors}))


if __name__ == "__main__":
    main()