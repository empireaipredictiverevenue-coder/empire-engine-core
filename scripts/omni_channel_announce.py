#!/usr/bin/env python3
"""
EMPIRE V49 · OMNI CHANNEL ANNOUNCEMENT
=========================================
Announces the new Omni Channel (clone any video from any platform) and
Omni Studio (AI video editing + AI avatar generation) to all 755 active
contractors with valid emails.

Sends a one-time announcement via Resend with personalized contractor
content, UTM tracking links, and campaign progress persistence.

Usage:
  python3 scripts/omni_channel_announce.py                       # send default batch (100)
  python3 scripts/omni_channel_announce.py --batch 200           # send up to 200
  python3 scripts/omni_channel_announce.py --dry-run             # preview without sending
  python3 scripts/omni_channel_announce.py --list                # show eligible count
  python3 scripts/omni_channel_announce.py --status              # show campaign stats
  python3 scripts/omni_channel_announce.py --resume              # resume from last offset
  python3 scripts/omni_channel_announce.py --all                 # send to ALL eligible in one run

Respects Resend rate limits (1s between sends). Logs each send to
email_log. Tracks progress in agent_activity table so subsequent runs
pick up where the last left off. Runs via Resend marketing quota.

CAMPAIGN: "omni_channel_launch_20260622"
  - Highlights Omni Channel: clone any video from YouTube, TikTok, IG, Twitter
  - Highlights Omni Studio: AI video editing, text overlay, captions, AI avatars
  - Includes demo links and CTA to try it
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
    format="%(asctime)s [omni-announce] %(levelname)s %(message)s",
)
log = logging.getLogger("omni_channel_announce")

# ── Config ─────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk")
FROM_ADDRESS = os.environ.get("FROM_ADDRESS", "noreply@empire-ai.co.uk")
FROM_NAME = os.environ.get("FROM_NAME", "Empire AI Operations")
CAMPAIGN_ID = "omni_channel_launch_20260622"
BATCH_SIZE = 100
SEND_DELAY_SEC = 1.0  # 1s between sends (Resend allows 5/s)

# ── Email HTML Template ────────────────────────────────────────────────
_CAMPAIGN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0a0a0a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; }
.container { max-width: 560px; margin: 0 auto; padding: 32px 24px; }
.header { border-bottom: 1px solid #27272a; padding-bottom: 20px; margin-bottom: 24px; }
.brand { font-size: 11px; color: #71717a; letter-spacing: .18em; text-transform: uppercase; margin-bottom: 6px; }
.brand em { color: #44E5B8; font-style: normal; }
.tagline { font-size: 20px; font-weight: 700; color: #44E5B8; }
h1 { font-size: 24px; font-weight: 700; color: #f4f4f5; margin-bottom: 12px; letter-spacing: -.02em; }
h2 { font-size: 18px; font-weight: 600; color: #f4f4f5; margin: 28px 0 12px; letter-spacing: -.01em; }
p { font-size: 14px; line-height: 1.7; color: #a1a1aa; margin-bottom: 16px; }
.highlight { color: #ffb800; font-weight: 600; }
.highlight-green { color: #44E5B8; font-weight: 600; }
.bullets { margin: 16px 0; padding: 0; list-style: none; }
.bullets li { padding: 10px 16px; margin-bottom: 6px; background: rgba(255,255,255,0.02); border-left: 2px solid #44E5B8; font-size: 13px; color: #d4d4d8; line-height: 1.5; }
.bullets li strong { color: #f4f4f5; }
.feature-card { background: rgba(255,255,255,0.03); border: 1px solid #27272a; padding: 18px; margin: 14px 0; }
.feature-card .fc-title { font-size: 14px; font-weight: 600; color: #44E5B8; margin-bottom: 6px; }
.feature-card .fc-desc { font-size: 12px; color: #a1a1aa; line-height: 1.6; }
.cta-row { margin: 28px 0; text-align: center; }
.cta { display: inline-block; background: #44E5B8; color: #000; padding: 14px 32px; text-decoration: none; font-weight: 700; font-size: 14px; letter-spacing: .04em; border-radius: 4px; }
.cta:hover { background: transparent; color: #44E5B8; outline: 2px solid #44E5B8; }
.cta-secondary { display: inline-block; border: 1px solid #44E5B8; color: #44E5B8; padding: 12px 28px; text-decoration: none; font-weight: 600; font-size: 13px; letter-spacing: .04em; border-radius: 4px; margin-left: 8px; }
.cta-secondary:hover { background: rgba(68,229,184,0.08); }
.badge { display: inline-block; background: rgba(68,229,184,0.1); border: 1px solid rgba(68,229,184,0.2); color: #44E5B8; font-size: 10px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; padding: 4px 10px; margin-bottom: 8px; }
.divider { border: none; border-top: 1px solid #27272a; margin: 24px 0; }
.footer { border-top: 1px solid #27272a; padding-top: 18px; margin-top: 28px; font-size: 10px; color: #52525b; line-height: 1.6; }
.footer a { color: #71717a; }
</style>
</head><body>
<div class="container">

<div class="header">
  <div class="brand">EMPIRE <em>AI</em> · Product Launch</div>
  <div class="tagline">Omni Channel + Omni Studio are live</div>
</div>

<h1>Hi __NAME__,</h1>

<p>We just shipped two major capabilities to the Empire AI platform — and both are designed to help you work smarter, not harder.</p>

<div class="badge">NEW</div>
<h2>📡 Omni Channel</h2>
<p>Clone <strong>any video from any platform</strong> — YouTube, TikTok, Instagram, Twitter/X, Facebook, Vimeo, LinkedIn, and 1000+ more sites.</p>

<div class="feature-card">
  <div class="fc-title">⬇️ One-click download</div>
  <div class="fc-desc">Paste a URL, get the video. 1080p max, subtitles, thumbnails, metadata. Channel/playlist bulk download supported.</div>
</div>

<div class="feature-card">
  <div class="fc-title">📝 Auto-transcription</div>
  <div class="fc-desc">Every cloned video is transcribed via Deepgram STT — get full transcripts with speaker diarization, word-level timestamps.</div>
</div>

<div class="feature-card">
  <div class="fc-title">📤 Cross-platform syndication</div>
  <div class="fc-desc">Push cloned content to Twitter, LinkedIn, Facebook, and more — all from one pipeline. Your content, your channels.</div>
</div>

<div class="badge">NEW</div>
<h2>🎬 Omni Studio</h2>
<p>AI-powered video editing and avatar generation — no desktop software required. All via API.</p>

<div class="feature-card">
  <div class="fc-title">✂️ Video Editing</div>
  <div class="fc-desc">Trim, concatenate, overlay text/captions, speed change, image overlay, transitions between clips. Full pipeline: chain operations in one call.</div>
</div>

<div class="feature-card">
  <div class="fc-title">👤 AI Avatars</div>
  <div class="fc-desc">Generate talking-head avatar videos from text scripts. Text-to-speech + animated composite. Perfect for video outreach, social content, and rapid content creation.</div>
</div>

<div class="feature-card">
  <div class="fc-title">🎯 Scene Detection</div>
  <div class="fc-desc">Auto-detect scene changes in any video via PySceneDetect. Get timestamped scene boundaries for rapid editing.</div>
</div>

<hr class="divider">

<p style="font-size:13px;color:#71717a;"><strong style="color:#d4d4d8;">Why this matters for you:</strong> If you produce content for your contracting business — social proof videos, before/after walkthroughs, educational clips — Omni Channel lets you find and clone the best content on any platform, and Omni Studio lets you edit and remix it with AI avatars narrating your message.</p>

<div class="cta-row">
  <a class="cta" href="__DEMO_LINK__">Try Omni Channel →</a>
  <a class="cta-secondary" href="__STUDIO_LINK__">Try Omni Studio →</a>
</div>

<p style="font-size:12px;color:#71717a;">Both products are available through the Suite API. Check your dashboard for access or reply to this email for a walkthrough.</p>

<p style="margin-top:28px;color:#d4d4d8;">— The Empire AI Team</p>

<div class="footer">
  <strong>Empire AI</strong> · Predictive Revenue Network<br>
  <a href="__UNSUBSCRIBE__">Unsubscribe</a> · <a href="__PORTAL_LINK__">Contractor Dashboard</a><br>
  <span>You're receiving this because you're a registered Empire AI contractor.</span>
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
            "total_sent":  meta.get("total_sent", 0),
            "last_batch":  meta.get("last_batch", 0),
            "last_run":    meta.get("last_run", ""),
            "errors":      meta.get("errors", 0),
            "completed":   meta.get("completed", False),
            "meta":        meta,
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
            "activity": "omni_channel_announce",
            "summary": f"Sent {batch_sent} emails (offset={offset}, total={total_sent})",
            "meta": {
                "last_offset": offset,
                "total_sent":  total_sent,
                "last_batch":  batch_sent,
                "last_run":    now,
                "errors":      errors,
                "completed":   completed,
                "campaign_id": CAMPAIGN_ID,
            },
            "created_at": now,
        }).execute()
    except Exception as e:
        log.warning(f"Could not save campaign progress: {e}")


# ── Email Logging ──────────────────────────────────────────────────────
def log_email_send(db, contractor_id: str, email: str, name: str,
                   resend_id: str, success: bool, error: str = ""):
    """Log the send result to email_log."""
    try:
        db.table("email_log").insert({
            "email":      email,
            "direction":  "outbound",
            "subject":    "Empire AI · Omni Channel + Studio are live",
            "step":       1,
            "message_id": resend_id or "",
            "delivered":  success,
            "meta": {
                "campaign_id":   CAMPAIGN_ID,
                "contractor_id": contractor_id,
                "contractor_name": name,
                "error": error[:200] if error else "",
            },
        }).execute()
    except Exception as e:
        log.warning(f"Could not log email send: {e}")


# ── Email Validation ───────────────────────────────────────────────────
def is_valid_email(email: str) -> bool:
    """Reject placeholder/invalid emails that cause 422 errors from Resend.

    NOTE: This is permissive for registered contractors (unlike the stricter
    version in scripts/contractor_outreach.py which filters Gmail for cold
    prospecting). Registered contractors already opted in, so we accept all
    legitimate email providers including Gmail.
    """
    import re
    if not email:
        return False
    # Control characters (cause 422 Unprocessable Entity from Resend)
    for c in email:
        if ord(c) < 32 or ord(c) == 127:
            return False
    # Whitespace
    if any(c.isspace() for c in email):
        return False
    # Only reject obvious placeholders — not real email providers
    bad_patterns = [
        "@empire-ai", "@placeholder", "@example.",
        "noreply@", "no-reply@",
        "test@", "spam@", "your@", "youremail",
        "@yoursite", "@domain.com", "@company.com",
    ]
    el = email.lower()
    for p in bad_patterns:
        if p in el:
            return False
    # Basic RFC check
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if len(local) > 64 or len(domain) > 255:
        return False
    tld = domain.rsplit(".", 1)[-1]
    if not (2 <= len(tld) <= 24 and tld.isalpha()):
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    return True


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
    parser = argparse.ArgumentParser(description="Empire AI Omni Channel Announcement")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Emails to send this run (default 100)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--list", action="store_true", help="Show eligible count and exit")
    parser.add_argument("--status", action="store_true", help="Show campaign stats and exit")
    parser.add_argument("--resume", action="store_true", help="Resume from last sent offset")
    parser.add_argument("--offset", type=int, default=0, help="Start from specific offset")
    parser.add_argument("--all", action="store_true", help="Send to ALL eligible in one run (override batch)")
    args = parser.parse_args()

    db = get_db()

    # ── Count total eligible (active contractors only with valid emails) ──
    r = db.table("contractors").select("id", count="exact") \
        .eq("active", True) \
        .neq("email", "") \
        .not_.is_("email", "null") \
        .execute()
    raw_count = r.count if hasattr(r, 'count') else 0

    # Get all with emails to count valid
    r2 = db.table("contractors").select("id,email,name,metro") \
        .eq("active", True) \
        .neq("email", "") \
        .not_.is_("email", "null") \
        .order("created_at") \
        .execute()
    all_rows = r2.data or []        # Filter valid emails
    eligible = [c for c in all_rows if is_valid_email(c.get("email", ""))]
    total_eligible = len(eligible)
    invalid_count = raw_count - total_eligible
    if invalid_count:
        log.info(f"  Filtered {invalid_count} invalid/placeholder emails")
        for c in all_rows:
            if not is_valid_email(c.get("email", "")):
                log.debug(f"  Rejected: {c.get('name')} <{c.get('email')}>")

    # ── STATUS mode ────────────────────────────────────────────────────
    if args.status:
        progress = get_campaign_progress(db)
        total = total_eligible
        print(f"\n📊 Omni Channel Announcement — Campaign Status")
        print(f"{'=' * 50}")
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
        total = total_eligible
        invalid_count = raw_count - total
        print(f"\n📋 Eligible contractors: {total}")
        print(f"  Invalid/bad emails:  {invalid_count}")
        print(f"  Total with emails:   {raw_count}")
        print(f"\n{'Name':36s} | {'Email':32s} | {'Metro':20s}")
        print("-" * 92)
        for c in eligible[:50]:
            name = (c.get("name") or "?")[:34]
            email = (c.get("email") or "?")[:30]
            metro = (c.get("metro") or "—")[:18]
            print(f"{name:36s} | {email:32s} | {metro:20s}")
        if len(eligible) > 50:
            print(f"\n  ... and {len(eligible) - 50} more")
        return

    # ── MAIN SEND LOGIC ────────────────────────────────────────────────
    progress = get_campaign_progress(db)
    offset = args.offset
    if args.resume and not offset:
        offset = progress["last_offset"]
    if not offset:
        offset = 0

    batch = total_eligible if args.all else args.batch

    log.info(f"🔁 Campaign: {CAMPAIGN_ID}")
    log.info(f"  Resume offset: {offset}")
    log.info(f"  Batch size:    {batch}")
    log.info(f"  Dry run:       {args.dry_run}")
    log.info(f"  Total sent:    {progress['total_sent']}")

    # Slice eligible list for this batch
    batch_rows = eligible[offset:offset + batch]

    if not batch_rows:
        log.info("✅ No more contractors to email. Campaign complete!")
        if not args.dry_run:
            save_campaign_progress(db, offset, 0, progress["total_sent"],
                                   errors=progress["errors"], completed=True)
        return

    log.info(f"📨 Sending {len(batch_rows)} emails (offset={offset})...")

    sent_count = 0
    error_count = 0

    for i, ctr in enumerate(batch_rows):
        name = ctr.get("name", "Contractor")
        email = ctr.get("email", "")
        ctr_id = ctr.get("id", "")
        metro = ctr.get("metro", "")

        if not email:
            log.warning(f"  ⏭  Skip {name}: missing email")
            continue

        safe_name = html.escape(name)

        # Build personalized links with UTM tracking
        demo_link = f"{PUBLIC_BASE_URL.rstrip('/')}/products/elite-scraper?ref=omni_announce&utm_source=email&utm_medium=announce&utm_campaign=omni_channel&utm_content={safe_name.replace(' ','_')}"
        studio_link = f"{PUBLIC_BASE_URL.rstrip('/')}/demo?ref=omni_studio&utm_source=email&utm_medium=announce&utm_campaign=omni_studio&utm_content={safe_name.replace(' ','_')}"
        portal_link = f"{PUBLIC_BASE_URL.rstrip('/')}/portal/contractors/login"
        unsubscribe_link = f"{PUBLIC_BASE_URL.rstrip('/')}/portal/contractors/login"

        # Personalize HTML
        html_content = _CAMPAIGN_HTML \
            .replace("__NAME__", safe_name) \
            .replace("__DEMO_LINK__", demo_link) \
            .replace("__STUDIO_LINK__", studio_link) \
            .replace("__PORTAL_LINK__", portal_link) \
            .replace("__UNSUBSCRIBE__", unsubscribe_link)

        subject = "Empire AI · Omni Channel + Studio are live"

        if args.dry_run:
            print(f"  📄 [{i + 1}/{len(batch_rows)}] Would send to {name} <{email}> (metro: {metro})")
            print(f"       Demo: {demo_link[:70]}...")
            # Show a snippet of the rendered HTML body (truncated)
            body_snippet = html_content[html_content.index('<h1>'):html_content.index('</h1>')+6] if '<h1>' in html_content else ''
            body_snippet = body_snippet[:120]
            if body_snippet:
                print(f"       Body: {body_snippet}...")
            sent_count += 1
            continue

        # Send via Resend
        result = send_resend(to=email, subject=subject, html=html_content)

        if result.get("ok"):
            sent_count += 1
            log.info(f"  ✅ [{i + 1}/{len(batch_rows)}] Sent to {name} <{email}> — {result.get('id', '')[:16]}...")
        else:
            error_count += 1
            log.error(f"  ❌ [{i + 1}/{len(batch_rows)}] Failed for {name} <{email}>: {result.get('error', 'unknown')}")

        # Log to email_log
        log_email_send(
            db=db,
            contractor_id=ctr_id,
            email=email,
            name=name,
            resend_id=result.get("id", ""),
            success=result.get("ok", False),
            error=result.get("error", ""),
        )

        # Rate limit
        time.sleep(SEND_DELAY_SEC)

    # Save progress
    total_sent = progress["total_sent"] + sent_count
    total_errors = progress["errors"] + error_count
    new_offset = offset + len(batch_rows)
    campaign_complete = new_offset >= total_eligible

    if not args.dry_run:
        save_campaign_progress(db, new_offset, sent_count, total_sent,
                               errors=total_errors, completed=campaign_complete)

    log.info(f"\n📊 Batch complete:")
    log.info(f"  Sent:     {sent_count}")
    log.info(f"  Errors:   {error_count}")
    log.info(f"  Total:    {total_sent}")
    log.info(f"  Of:       {total_eligible} eligible")
    log.info(f"  Next run: python3 scripts/omni_channel_announce.py --resume")

    if args.dry_run:
        log.info("  🏜️  DRY RUN — no emails were sent")

    # Print one-line summary for easy parsing
    print(f"\nSUMMARY: {sent_count} sent, {error_count} errors, {total_sent}/{total_eligible} total, "
          f"campaign_complete={campaign_complete}")


if __name__ == "__main__":
    main()
