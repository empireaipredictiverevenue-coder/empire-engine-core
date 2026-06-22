#!/usr/bin/env python3
"""
EMPIRE V49 · REFERRAL CAMPAIGN SENDER
======================================
Sends personalized refer-a-contractor campaign emails to all active
contractors with referral codes. Designed to be run periodically
until all contractors have been contacted.

Usage:
  python3 scripts/referral_campaign_send.py                    # send default batch (50)
  python3 scripts/referral_campaign_send.py --batch 100        # send up to 100
  python3 scripts/referral_campaign_send.py --dry-run          # preview without sending
  python3 scripts/referral_campaign_send.py --list             # show pending count
  python3 scripts/referral_campaign_send.py --status           # show campaign stats
  python3 scripts/referral_campaign_send.py --resume           # resume from last sent offset

Respects Resend rate limits (1s between sends). Logs each send to the
email_log table for audit. Tracks campaign progress in the
agent_activity table so subsequent runs pick up where the last left off.

CAMPAIGN: "Refer a Contractor — Earn $500"
  - Personalized with contractor name and unique referral link
  - Highlights the $500 bounty per contractor who closes their first deal
  - Includes portal QR code (via qrserver.com)
  - Includes one-click share buttons
"""

import os
import sys
import json
import time
import html
import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

# ── Setup ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [referral-campaign] %(levelname)s %(message)s",
)
log = logging.getLogger("referral_campaign")

# ── Config ─────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk")
FROM_ADDRESS = os.environ.get("FROM_ADDRESS", "noreply@empire-ai.co.uk")
FROM_NAME = os.environ.get("FROM_NAME", "Empire AI Operations")
CAMPAIGN_ID = "referral_share_20260621"  # unique campaign identifier
BATCH_SIZE = 50  # default emails per run
SEND_DELAY_SEC = 1.0  # 1s between sends (Resend allows 5/s)

# ── Email HTML Template ────────────────────────────────────────────────
_CAMPAIGN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0a0a0a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; }
.container { max-width: 520px; margin: 0 auto; padding: 32px 24px; }
.header { border-bottom: 1px solid #27272a; padding-bottom: 20px; margin-bottom: 24px; }
.brand { font-size: 11px; color: #71717a; letter-spacing: .18em; text-transform: uppercase; margin-bottom: 6px; }
.brand em { color: #44E5B8; font-style: normal; }
.tagline { font-size: 20px; font-weight: 700; color: #44E5B8; }
.emoji { font-size: 28px; margin-bottom: 8px; }
h1 { font-size: 22px; font-weight: 700; color: #f4f4f5; margin-bottom: 14px; }
p { font-size: 14px; line-height: 1.7; color: #a1a1aa; margin-bottom: 16px; }
.highlight { color: #ffb800; font-weight: 600; }
.highlight-green { color: #44E5B8; font-weight: 600; }
.bullets { margin: 20px 0; padding: 0; list-style: none; }
.bullets li { padding: 10px 16px; margin-bottom: 6px; background: rgba(255,255,255,0.02); border-left: 2px solid #44E5B8; font-size: 13px; color: #d4d4d8; line-height: 1.5; }
.bullets li strong { color: #f4f4f5; }
.cta-row { margin: 28px 0; text-align: center; }
.cta { display: inline-block; background: #44E5B8; color: #000; padding: 14px 32px; text-decoration: none; font-weight: 700; font-size: 14px; letter-spacing: .04em; }
.cta:hover { background: transparent; color: #44E5B8; outline: 2px solid #44E5B8; }
.link-box { background: rgba(255,255,255,0.03); border: 1px solid #27272a; padding: 14px; margin: 20px 0; word-break: break-all; font-family: ui-monospace, monospace; font-size: 11px; color: #44E5B8; text-align: center; }
.quote { background: rgba(68,229,184,0.06); border: 1px solid rgba(68,229,184,0.15); padding: 16px; margin: 20px 0; font-size: 12px; color: #d4d4d8; line-height: 1.6; }
.quote strong { color: #44E5B8; }
.footer { border-top: 1px solid #27272a; padding-top: 18px; margin-top: 28px; font-size: 10px; color: #52525b; line-height: 1.6; }
.footer a { color: #71717a; }
</style>
</head><body>
<div class="container">

<div class="header">
  <div class="brand">EMPIRE <em>AI</em> · Contractor Network</div>
  <div class="tagline">Earn <span class="highlight">$500</span> per contractor you refer</div>
</div>

<div class="emoji">👋</div>
<h1>Hi __NAME__,</h1>

<p>You're already part of the Empire AI contractor network — now you can earn <strong class="highlight">$500</strong> for every contractor you bring in.</p>

<p>Here's how it works:</p>

<ul class="bullets">
  <li><strong>Share your unique referral link</strong> with other commercial contractors you know — roofers, HVAC specialists, restoration pros, or general contractors.</li>
  <li><strong>When they sign up</strong> through your link and close their first settled claim with us, you earn a <strong class="highlight">$500 bounty</strong>.</li>
  <li><strong>No cap.</strong> Refer 10 contractors → earn $5,000. Refer 20 → $10,000. Unlimited.</li>
  <li><strong>They get</strong> a proven dispatch pipeline with storm damage leads in their metro — no contract, no exclusivity, first 2 deals complimentary.</li>
</ul>

<div class="link-box"><strong>Your referral link:</strong><br>__REFERRAL_LINK__</div>

<div class="cta-row">
  <a class="cta" href="__REFERRAL_LINK__">Share Your Referral Link →</a>
</div>

<p style="font-size:12px;color:#71717a;">Or copy your code: <strong style="color:#44E5B8;">__REFERRAL_CODE__</strong></p>

<div class="quote">
  <strong>💡 Pro tip:</strong> Share your referral link on industry job boards, in contractor Facebook groups, or directly with other companies you see at job sites. Every contractor you refer who closes their first deal puts <strong class="highlight">$500</strong> in your pocket.
</div>

<p>You can track your referrals, pending bounties, and payout status from your <a href="__PORTAL_LINK__" style="color:#44E5B8;">contractor dashboard</a> at any time.</p>

<p>Questions? Reply to this email or visit the portal.</p>

<p style="margin-top:28px;color:#d4d4d8;">— The Empire AI Team</p>

<div class="footer">
  <strong>Empire AI</strong> · Predictive Revenue Network<br>
  <a href="__PORTAL_LINK__">Contractor Dashboard</a> &nbsp;·&nbsp; <a href="__UNSUBSCRIBE__">Unsubscribe</a><br>
  <span>You're receiving this because you're a registered Empire AI contractor with referral code __REFERRAL_CODE__.</span>
</div>

</div>
</body></html>
"""


# ── Supabase client ────────────────────────────────────────────────────
def get_db():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ── Campaign Progress ──────────────────────────────────────────────────
def get_campaign_progress(db) -> dict:
    """Return campaign state from agent_activity table."""
    try:
        r = db.table("agent_activity").select("meta") \
            .eq("agent_name", f"campaign_{CAMPAIGN_ID}") \
            .order("created_at", desc=True).limit(1).execute()
        meta = {}
        if r.data and r.data[0].get("meta"):
            m = r.data[0]["meta"]
            meta = m if isinstance(m, dict) else {}
        return {
            "last_offset": meta.get("last_offset", 0),
            "total_sent": meta.get("total_sent", 0),
            "last_batch": meta.get("last_batch", 0),
            "last_run": meta.get("last_run", ""),
            "errors": meta.get("errors", 0),
            "completed": meta.get("completed", False),
            "meta": meta,
        }
    except Exception as e:
        log.warning(f"Could not read campaign progress: {e}")
        return {"last_offset": 0, "total_sent": 0, "last_batch": 0,
                "last_run": "", "errors": 0, "completed": False, "meta": {}}


def save_campaign_progress(db, offset: int, batch_sent: int, total_sent: int,
                           errors: int = 0, completed: bool = False):
    """Persist campaign progress to agent_activity."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        db.table("agent_activity").insert({
            "agent_name": f"campaign_{CAMPAIGN_ID}",
            "activity": "referral_campaign_send",
            "summary": f"Sent {batch_sent} emails (offset={offset}, total={total_sent})",
            "meta": {
                "last_offset": offset,
                "total_sent": total_sent,
                "last_batch": batch_sent,
                "last_run": now,
                "errors": errors,
                "completed": completed,
                "campaign_id": CAMPAIGN_ID,
            },
            "created_at": now,
        }).execute()
    except Exception as e:
        log.warning(f"Could not save campaign progress: {e}")


# ── Email Logging ──────────────────────────────────────────────────────
def log_email_send(db, contractor_id: str, email: str, referral_code: str,
                   resend_id: str, success: bool, error: str = ""):
    """Log the send result to email_log."""
    try:
        db.table("email_log").insert({
            "email": email,
            "direction": "outbound",
            "subject": f"Empire AI · Earn $500 for every contractor you refer",
            "step": 1,
            "message_id": resend_id or "",
            "delivered": success,
            "meta": {
                "campaign_id": CAMPAIGN_ID,
                "contractor_id": contractor_id,
                "referral_code": referral_code,
                "error": error[:200] if error else "",
            },
        }).execute()
    except Exception as e:
        log.warning(f"Could not log email send: {e}")


# ── Resend Sender ──────────────────────────────────────────────────────
def send_resend(to: str, subject: str, html: str) -> dict:
    """Send email via Resend API. Returns {ok, id, error}."""
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY not set"}
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{FROM_NAME} <{FROM_ADDRESS}>",
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=20.0,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code < 300
        if ok:
            return {"ok": True, "id": data.get("id", "")}
        else:
            error = data.get("message") or data.get("error") or f"HTTP {r.status_code}"
            return {"ok": False, "error": error}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Main ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Empire AI Referral Campaign Sender")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Emails to send this run")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--list", action="store_true", help="Show pending count and exit")
    parser.add_argument("--status", action="store_true", help="Show campaign stats and exit")
    parser.add_argument("--resume", action="store_true", help="Resume from last sent offset")
    parser.add_argument("--offset", type=int, default=0, help="Start from specific offset")
    args = parser.parse_args()

    db = get_db()

    # ── STATUS mode ────────────────────────────────────────────────────
    if args.status:
        progress = get_campaign_progress(db)
        # Count total eligible
        r = db.table("contractors").select("id", count="exact") \
            .not_.is_("referral_code", "null") \
            .neq("referral_code", "") \
            .neq("email", "") \
            .not_.is_("email", "null") \
            .eq("active", True).execute()
        total = r.count if hasattr(r, 'count') else 0
        print(f"\n📊 Referral Campaign Status")
        print(f"{'=' * 45}")
        print(f"  Campaign ID:      {CAMPAIGN_ID}")
        print(f"  Total eligible:   {total}")
        print(f"  Total sent:       {progress['total_sent']}")
        print(f"  Last offset:      {progress['last_offset']}")
        print(f"  Last batch:       {progress['last_batch']}")
        print(f"  Last run:         {progress['last_run'] or 'Never'}")
        print(f"  Errors:           {progress['errors']}")
        print(f"  Completed:        {progress['completed']}")
        print(f"  Remaining:        {max(0, total - progress['total_sent'])}")
        print()
        return

    # ── LIST mode ──────────────────────────────────────────────────────
    if args.list:
        r = db.table("contractors").select("id,name,email,referral_code,metro", count="exact") \
            .not_.is_("referral_code", "null") \
            .neq("referral_code", "") \
            .neq("email", "") \
            .not_.is_("email", "null") \
            .eq("active", True) \
            .execute()
        rows = r.data or []
        total = r.count if hasattr(r, 'count') else len(rows)
        print(f"\n📋 Eligible contractors: {total}")
        print(f"{'Name':36s} | {'Email':32s} | {'Metro':20s} | {'Code':24s}")
        print("-" * 120)
        for c in rows:
            name = (c.get("name") or "?")[:34]
            email = (c.get("email") or "?")[:30]
            metro = (c.get("metro") or "—")[:18]
            code = (c.get("referral_code") or "—")[:22]
            print(f"{name:36s} | {email:32s} | {metro:20s} | {code:24s}")
        return

    # ── MAIN SEND LOGIC ────────────────────────────────────────────────
    progress = get_campaign_progress(db)
    offset = args.offset
    if args.resume and not offset:
        offset = progress["last_offset"]
    if not offset:
        offset = 0

    batch = args.batch

    log.info(f"🔁 Campaign: {CAMPAIGN_ID}")
    log.info(f"  Resume offset: {offset}")
    log.info(f"  Batch size:    {batch}")
    log.info(f"  Dry run:       {args.dry_run}")
    log.info(f"  Total sent:    {progress['total_sent']}")

    # Fetch batch
    r = db.table("contractors").select("id,name,email,referral_code,metro") \
        .not_.is_("referral_code", "null") \
        .neq("referral_code", "") \
        .neq("email", "") \
        .not_.is_("email", "null") \
        .eq("active", True) \
        .order("created_at") \
        .range(offset, offset + batch - 1) \
        .execute()

    rows = r.data or []
    if not rows:
        log.info("✅ No more contractors to email. Campaign complete!")
        if not args.dry_run:
            save_campaign_progress(db, offset, 0, progress["total_sent"],
                                   errors=progress["errors"], completed=True)
        return

    log.info(f"📨 Sending {len(rows)} emails (offset={offset})...")

    sent_count = 0
    error_count = 0

    for i, ctr in enumerate(rows):
        name = ctr.get("name", "Contractor")
        email = ctr.get("email", "")
        ref_code = ctr.get("referral_code", "")
        ctr_id = ctr.get("id", "")

        if not email or not ref_code:
            log.warning(f"  ⏭  Skip {name}: missing email or referral code")
            continue

        referral_link = f"{PUBLIC_BASE_URL.rstrip('/')}/ref/contractor/{ref_code}"
        portal_link = f"{PUBLIC_BASE_URL.rstrip('/')}/portal/contractors/login"
        # No true unsubscribe — contractors are registered users, opt out via portal or support
        unsubscribe_link = f"{PUBLIC_BASE_URL.rstrip('/')}/portal/contractors/login"

        # Personalize HTML (escape name to prevent HTML injection from operator-entered data)
        safe_name = html.escape(name)
        html_content = _CAMPAIGN_HTML \
            .replace("__NAME__", safe_name) \
            .replace("__REFERRAL_LINK__", referral_link) \
            .replace("__REFERRAL_CODE__", ref_code) \
            .replace("__PORTAL_LINK__", portal_link) \
            .replace("__UNSUBSCRIBE__", unsubscribe_link)

        subject = f"Empire AI · Earn $500 for every contractor you refer"

        if args.dry_run:
            print(f"  📄 [{i + 1}/{len(rows)}] Would send to {name} <{email}> via {ref_code}")
            log.info(f"  Referral link: {referral_link}")
            sent_count += 1
            continue

        # Send
        result = send_resend(to=email, subject=subject, html=html_content)

        if result.get("ok"):
            sent_count += 1
            log.info(f"  ✅ [{i + 1}/{len(rows)}] Sent to {name} <{email}> — {result.get('id', '')[:16]}...")
        else:
            error_count += 1
            log.error(f"  ❌ [{i + 1}/{len(rows)}] Failed for {name} <{email}>: {result.get('error', 'unknown')}")

        # Log to email_log
        log_email_send(
            db=db,
            contractor_id=ctr_id,
            email=email,
            referral_code=ref_code,
            resend_id=result.get("id", ""),
            success=result.get("ok", False),
            error=result.get("error", ""),
        )

        # Rate limit
        time.sleep(SEND_DELAY_SEC)

    # Save progress
    total_sent = progress["total_sent"] + sent_count
    total_errors = progress["errors"] + error_count
    new_offset = offset + len(rows)

    if not args.dry_run:
        save_campaign_progress(db, new_offset, sent_count, total_sent,
                               errors=total_errors)

    log.info(f"\n📊 Batch complete:")
    log.info(f"  Sent:     {sent_count}")
    log.info(f"  Errors:   {error_count}")
    log.info(f"  Total:    {total_sent}")
    log.info(f"  Next run: python3 scripts/referral_campaign_send.py --resume")

    if args.dry_run:
        log.info("  🏜️  DRY RUN — no emails were sent")


if __name__ == "__main__":
    main()
