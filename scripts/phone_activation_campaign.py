"""
Empire AI · Phone Activation Campaign
=======================================
One-shot campaign: tells all valid contractors about the new simplified
phone-based activation on /for-contractors — no UUID required anymore.

Sends:
  - Email via SMTP (smtp.resend.com:587) — replaces Resend REST API
  - SMS via Vonage (to contractors with phones)

Run:
  python3 scripts/phone_activation_campaign.py          # live send
  python3 scripts/phone_activation_campaign.py --dry-run # preview only
  python3 scripts/phone_activation_campaign.py --limit 10 # send to 10
"""

import os
import re
import sys
import uuid
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/root/empire-v49").resolve()
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client
import httpx

from scripts.helpers.smtp_email import send_smtp_email

log = logging.getLogger("phone_activation_campaign")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VONAGE_API_KEY = os.environ.get("VONAGE_API_KEY", "")
VONAGE_API_SECRET = os.environ.get("VONAGE_API_SECRET", "")
VONAGE_NUMBER = os.environ.get("VONAGE_NUMBER", "")

CAMPAIGN_NAME = "phone_activation_2026-06-23"
PRICING_URL = "https://empire-ai.co.uk/for-contractors"

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ── Email template ────────────────────────────────────────────────────
def _build_email_html(first: str, metro: str) -> str:
    body = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;color:#e2e8f0;background:#0a0f1c;padding:32px 24px;">
  <div style="font-size:11px;color:#64748b;letter-spacing:.16em;text-transform:uppercase;margin-bottom:20px;">Empire AI · Contractor Network</div>

  <div style="font-size:22px;font-weight:700;color:#f8fafc;letter-spacing:-0.02em;margin-bottom:16px;">
    Hi {first},
  </div>

  <p style="font-size:15px;line-height:1.7;color:#cbd5e1;margin:0 0 16px;">
    We made a change based on feedback from contractors: <strong style="color:#f8fafc;">you no longer need a contractor ID to activate a subscription.</strong>
  </p>

  <p style="font-size:15px;line-height:1.7;color:#cbd5e1;margin:0 0 16px;">
    Just visit <a href="{PRICING_URL}" style="color:#22c55e;text-decoration:underline;">empire-ai.co.uk/for-contractors</a>, enter the phone number we have on file for you, paste your Solana wallet, pick a tier, and you're set. No UUID, no invite link, no back-and-forth.
  </p>

  <div style="margin:24px 0;padding:18px 20px;background:#131a2e;border-left:3px solid #22c55e;font-size:13px;color:#94a3b8;line-height:1.7;">
    <strong style="color:#f8fafc;">Quick recap:</strong><br>
    • Free: $0/mo · 3 leads/mo · 24h delay<br>
    • Basic: $99/mo · 50 leads/mo · 60-min delay<br>
    • Pro: $299/mo · 200 leads/mo · instant delivery · analytics<br>
    • Enterprise: $499/mo · unlimited · top priority · dedicated rep<br><br>
    <strong style="color:#f8fafc;">Pay in USDC.</strong> No Stripe, no card on file. Your wallet.
  </div>

  <p style="font-size:15px;line-height:1.7;color:#cbd5e1;margin:0 0 12px;">
    If you have {metro}-area leads in your pipeline right now, Pro is the right call — 200 leads/mo at $299 is $1.50/lead. One closed job covers the year.
  </p>

  <table cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">
    <tr><td align="center" style="background:#22c55e;border-radius:8px;padding:14px 32px;">
      <a href="{PRICING_URL}" style="color:#0a0f1c;font-size:15px;font-weight:700;text-decoration:none;">Activate with your phone →</a>
    </td></tr>
  </table>

  <p style="font-size:13px;color:#64748b;margin:28px 0 0;border-top:1px solid #1e293b;padding-top:18px;">
    You're receiving this because you're a registered contractor in the Empire AI network. If you no longer want these updates, reply STOP to any SMS or reply to this email.
  </p>
</div>"""
    return body


def _build_sms_body(first: str) -> str:
    return (
        f"Empire AI: Hi {first}, you can now activate a subscription with just your phone number — "
        f"no contractor ID needed. Visit {PRICING_URL} to pick a tier in 60 seconds. Reply STOP to opt out."
    )


def _first_name(name: str) -> str:
    if not name:
        return "there"
    return name.split()[0].strip().title()


def _is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    bad = [
        "__quarantine__", "pending.real-email", "@placeholder", "@example",
        "@empire-ai", "noreply@", "test@", "spam@",
        "@yoursite", "@domain.com", "@company.com",
    ]
    el = email.lower()
    if any(b in el for b in bad):
        return False
    for c in email:
        if ord(c) < 32 or ord(c) == 127:
            return False
    if any(c.isspace() for c in email):
        return False
    return bool(EMAIL_RE.match(email))


def _send_email(to: str, subject: str, html: str) -> dict:
    """Send via SMTP (smtp.resend.com:587). Returns {ok, message_id} or {ok, error}.

    Uses the shared SMTP helper which authenticates with RESEND_API_KEY
    via STARTTLS on port 587. No REST API call.
    """
    return send_smtp_email(to=to, subject=subject, html=html)


def _send_sms(to: str, body: str) -> dict:
    """Send SMS via Vonage. Returns {ok, message_uuid} or {ok, error}.

    Vonage SMS API authenticates via api_key/api_secret in the request
    body, not HTTP Basic auth headers. Credentials go in the JSON payload.
    """
    if not VONAGE_API_KEY or not VONAGE_API_SECRET or not VONAGE_NUMBER:
        return {"ok": False, "error": "Vonage not configured"}
    payload = {
        "api_key": VONAGE_API_KEY,
        "api_secret": VONAGE_API_SECRET,
        "from": VONAGE_NUMBER,
        "to": to,
        "text": body,
        "type": "text",
    }
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                "https://rest.nexmo.com/sms/json",
                json=payload,
            )
            data = r.json()
            ok = r.status_code < 400 and data.get("messages", [{}])[0].get("status") == "0"
            msg_uuid = data.get("messages", [{}])[0].get("message-id") if ok else None
            return {"ok": ok, "message_uuid": msg_uuid, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _log_send(sb, contractor_id: str, channel: str, status: str, detail: str = "") -> None:
    """Log the campaign send to contractor_outreach table.

    Note: contractor_outreach has no 'channel' column, so we embed
    the channel in the 'notes' field instead.
    """
    try:
        sb.table("contractor_outreach").insert({
            "contractor_id": contractor_id,
            "sequence": CAMPAIGN_NAME,
            "step": 1,
            "status": status,
            "notes": f"channel={channel}: {detail[:280]}",
            "last_sent_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning(f"log insert failed for {contractor_id}: {e}")


def _already_sent(sb, contractor_id: str) -> bool:
    """Check if this contractor already received this campaign."""
    try:
        r = sb.table("contractor_outreach").select("id").eq("contractor_id", contractor_id).eq("sequence", CAMPAIGN_NAME).limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


def run(dry_run: bool = False, limit: int = 0) -> dict:
    """Main campaign run."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    started = datetime.now(timezone.utc)

    # 1) Fetch contractors with valid emails
    r = sb.table("contractors").select("id,name,email,phone,metro").eq("active", True).not_.is_("email", "null").limit(7000).execute()
    all_contractors = r.data or []
    candidates = [c for c in all_contractors if _is_valid_email(c.get("email", ""))]
    log.info(f"Found {len(candidates)} contractors with valid email")

    if limit and limit < len(candidates):
        candidates = candidates[:limit]
        log.info(f"Limited to {limit}")

    # Stats
    email_sent = 0
    sms_sent = 0
    already = 0
    email_errors = 0
    sms_errors = 0

    for c in candidates:
        cid = c["id"]
        first = _first_name(c.get("name", ""))
        metro = c.get("metro") or "your area"
        email = c["email"]
        phone = c.get("phone", "")

        # Skip if already got this campaign
        if _already_sent(sb, cid):
            already += 1
            continue

        if dry_run:
            log.info(f"[DRY-RUN] Would email {email} ({first}) and SMS {phone}")
            email_sent += 1
            if phone:
                sms_sent += 1
            continue

        # ── Send email ──────────────────────────────────────────────
        subject = "Empire AI · Activate with your phone — no ID needed"
        html = _build_email_html(first, metro)
        e_res = _send_email(email, subject, html)
        if e_res.get("ok"):
            email_sent += 1
            _log_send(sb, cid, "email", "sent", f"campaign_email: {e_res.get('message_id','')}")
            log.info(f"[EMAIL] ✓ {email} ({first})")
        else:
            email_errors += 1
            _log_send(sb, cid, "email", "failed", f"campaign_email error: {e_res.get('error','')}")
            log.warning(f"[EMAIL] ✗ {email}: {e_res.get('error','unknown')}")

        # ── Send SMS ────────────────────────────────────────────────
        if phone:
            sms_body = _build_sms_body(first)
            s_res = _send_sms(phone, sms_body)
            if s_res.get("ok"):
                sms_sent += 1
                _log_send(sb, cid, "sms", "sent", f"campaign_sms: {s_res.get('message_uuid','')}")
                log.info(f"[SMS]   ✓ {phone} ({first})")
            else:
                sms_errors += 1
                _log_send(sb, cid, "sms", "failed", f"campaign_sms error: {s_res.get('error','')}")
                log.warning(f"[SMS]   ✗ {phone}: {s_res.get('error','unknown')}")

    # Log to agent_activity
    summary = (
        f"campaign={CAMPAIGN_NAME} "
        f"candidates={len(candidates)} "
        f"email_sent={email_sent} "
        f"sms_sent={sms_sent} "
        f"already_sent={already} "
        f"email_errors={email_errors} "
        f"sms_errors={sms_errors} "
        f"dry_run={'yes' if dry_run else 'no'}"
    )
    try:
        sb.table("agent_activity").insert({
            "agent_name": CAMPAIGN_NAME,
            "run_id": str(uuid.uuid4()),
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok" if email_errors == 0 and sms_errors == 0 else "warn",
            "rows_seen": len(candidates),
            "rows_processed": email_sent + sms_sent,
            "rows_errored": email_errors + sms_errors,
            "summary": summary,
        }).execute()
    except Exception as e:
        log.warning(f"agent_activity insert failed: {e}")

    result = {
        "campaign": CAMPAIGN_NAME,
        "candidates": len(candidates),
        "email_sent": email_sent,
        "sms_sent": sms_sent,
        "already_sent": already,
        "email_errors": email_errors,
        "sms_errors": sms_errors,
        "dry_run": dry_run,
    }
    log.info(f"Done: {summary}")
    return result


def main():
    p = argparse.ArgumentParser(description="Phone Activation Campaign — one-shot email + SMS")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no sends")
    p.add_argument("--limit", type=int, default=0, help="Max contractors to process (0 = all)")
    args = p.parse_args()

    if args.dry_run:
        log.info("=== DRY RUN MODE ===")

    result = run(dry_run=args.dry_run, limit=args.limit)

    if args.dry_run:
        print(f"\nDry run summary:")
    else:
        print(f"\nLive send summary:")
    print(f"  Campaign:     {result['campaign']}")
    print(f"  Candidates:   {result['candidates']}")
    print(f"  Email sent:   {result['email_sent']}")
    print(f"  SMS sent:     {result['sms_sent']}")
    print(f"  Already sent: {result['already_sent']}")
    print(f"  Email errors: {result['email_errors']}")
    print(f"  SMS errors:   {result['sms_errors']}")
    print(f"  Dry run:      {'yes' if result['dry_run'] else 'no'}")

    sys.exit(0 if result["email_errors"] == 0 and result["sms_errors"] == 0 else 1)


if __name__ == "__main__":
    main()
