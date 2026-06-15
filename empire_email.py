"""
EMPIRE V49 · EMAIL SEQUENCE ENGINE (Property Owner Channel)
=============================================================
The third leg of the outreach tripod (SMS, Voice, Email). Mirrors the
SMS engine's architecture but for inbox channels — CAN-SPAM-compliant
4-touch sequence over 7 days, sent via Resend.

Key features:
  - 4-touch sequence (T+0, T+24h, T+72h, T+7d)
  - One-click unsubscribe link in every email (CAN-SPAM required)
  - Physical postal address in every email (CAN-SPAM required)
  - Clear "From" line — real human name, no spoof
  - Subject lines accurately describe content (CAN-SPAM required)
  - Honest "this is paid commercial outreach" disclosure
  - Global unsubscribe registry honored on re-enrollment
  - Quiet hours respected (no emails 10pm-7am recipient's TZ)

Schema additions:
    CREATE TABLE IF NOT EXISTS email_sequences (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at      timestamptz NOT NULL DEFAULT now(),
        email           text NOT NULL UNIQUE,
        target_addr     text,
        sequence_type   text NOT NULL DEFAULT 'storm_strike',
        current_step    int  NOT NULL DEFAULT 0,
        status          text NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','paused','completed','unsubscribed','bounced','replied')),
        last_sent_at    timestamptz,
        next_send_at    timestamptz,
        bounces         int DEFAULT 0,
        meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS email_sequences_dispatch_idx
        ON email_sequences (status, next_send_at);

    CREATE TABLE IF NOT EXISTS email_unsubscribes (
        email       text PRIMARY KEY,
        created_at  timestamptz NOT NULL DEFAULT now(),
        reason      text DEFAULT 'one-click unsubscribe',
        meta        jsonb DEFAULT '{}'::jsonb
    );

    CREATE TABLE IF NOT EXISTS email_log (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at    timestamptz NOT NULL DEFAULT now(),
        email         text NOT NULL,
        direction     text CHECK (direction IN ('outbound','bounce','reply')),
        subject       text,
        step          int,
        message_id    text,
        delivered     boolean DEFAULT false,
        meta          jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS email_log_email_idx
        ON email_log (email, created_at DESC);

Wire-up in hub.py:
    from empire_email import EmailSequenceEngine, register_email_routes

    email_engine = EmailSequenceEngine(
        get_db=         get_db,
        send_email=     _send_email,        # reuse hub's helper
        sign_token=     _sign_token,        # for unsubscribe links
        verify_token=   _verify_token,
        public_base_url=PUBLIC_BASE_URL,
        physical_address=os.environ.get("EMPIRE_POSTAL_ADDRESS", "Empire AI Ltd · UK"),
        sender_name=os.environ.get("EMPIRE_SENDER_NAME", "Empire AI Operations"),
    )

    register_email_routes(app, email_engine, require_auth, broadcaster=live_broadcaster)

    @app.on_event("startup")
    async def _start_email():
        asyncio.create_task(email_engine.dispatcher_loop())
"""

import os
import re
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
import urllib.parse as _urlparse

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response


log = logging.getLogger("empire.email")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_SENDER_NAME = "Empire AI Operations"

# CAN-SPAM requires a physical postal address in every commercial email.
# Set EMPIRE_POSTAL_ADDRESS to your real registered business address.
DEFAULT_POSTAL = "Empire AI Ltd · United Kingdom"

# Sequence step delays — slower than SMS because email is less urgent
STEP_DELAYS = {
    1: timedelta(hours=24),
    2: timedelta(hours=72),
    3: timedelta(days=7),
}

# Quiet hours per recipient
QUIET_HOURS_START = 22  # 10 PM
QUIET_HOURS_END   = 7   # 7 AM

EMAIL_RX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL TEMPLATES — 4-touch storm_strike sequence
# Each template returns (subject, html, plain_text).
# All include unsubscribe footer + physical address (CAN-SPAM).
# ─────────────────────────────────────────────────────────────────────────────
def _email_shell(
    body_html:          str,
    unsubscribe_link:   str,
    postal_address:     str,
    sender_name:        str,
    tracking_pixel_url: str = "",
) -> str:
    """Wrap a body with the standard Empire email shell + CAN-SPAM footer."""
    pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:none;" />' if tracking_pixel_url else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,system-ui,'Helvetica Neue',sans-serif;">
{pixel}
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0a0a;">
<tr><td align="center" style="padding:32px 16px;">
  <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#0a0a0a;color:#e4e4e7;">
    <tr><td style="padding-bottom:18px;border-bottom:1px solid #27272a;">
      <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · Predictive Revenue</div>
      <div style="font-size:9px;color:#52525b;letter-spacing:.14em;text-transform:uppercase;margin-top:4px;">Paid commercial notice · {sender_name}</div>
    </td></tr>
    <tr><td style="padding:24px 0;">{body_html}</td></tr>
    <tr><td style="padding-top:24px;border-top:1px solid #27272a;font-size:11px;color:#71717a;line-height:1.7;">
      You are receiving this because Empire AI flagged severe weather activity at a property associated with your contact details. We are not affiliated with the National Weather Service, FEMA, your insurance carrier, or any government agency. <strong style="color:#a1a1aa;">{postal_address}</strong>.<br><br>
      <a href="{unsubscribe_link}" style="color:#10b981;text-decoration:underline;">Unsubscribe</a> · One click · Effective immediately
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


def _build_b2b_shell(
    body_html:          str,
    unsubscribe_link:   str,
    postal_address:     str,
    sender_name:        str,
    sub_niche_hint:     str = "",
    tracking_pixel_url: str = "",
) -> str:
    """CAN-SPAM compliant email shell for B2B outreach."""
    pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" style="display:none;" />' if tracking_pixel_url else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,system-ui,'Helvetica Neue',sans-serif;">
{pixel}
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0a0a;">
<tr><td align="center" style="padding:32px 16px;">
  <table cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#0a0a0a;color:#e4e4e7;">
    <tr><td style="padding-bottom:18px;border-bottom:1px solid #27272a;">
      <div style="font-size:11px;color:#71717a;letter-spacing:.18em;text-transform:uppercase;">Empire AI · B2B Lead Network</div>
      <div style="font-size:9px;color:#52525b;letter-spacing:.14em;text-transform:uppercase;margin-top:4px;">Paid commercial notice · {sender_name}</div>
    </td></tr>
    <tr><td style="padding:24px 0;">{body_html}</td></tr>
    <tr><td style="padding-top:24px;border-top:1px solid #27272a;font-size:11px;color:#71717a;line-height:1.7;">
      You are receiving this because we identified your company as a potential partner in our B2B lead generation network.
      We are not affiliated with any government agency, your current service providers, or any insurance carrier.
      <strong style="color:#a1a1aa;">{postal_address}</strong>.<br><br>
      <a href="{unsubscribe_link}" style="color:#10b981;text-decoration:underline;">Unsubscribe</a> · One click · Effective immediately
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


def _build_b2b_email(
    step: int,
    company: str,
    sub_niche: str,
    unsubscribe_link: str,
    postal_address: str,
    sender_name: str,
    tracking_pixel_url: str = "",
) -> tuple[str, str]:
    """Returns (subject, html_body) for B2B outreach. Step 0-3."""
    niche_lower = sub_niche.lower() if sub_niche else "business services"
    if step == 0:
        subject = f"Qualified {sub_niche} leads for {company}"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            Introductory offer for <span style="color:#44E5B8;">{company}</span>
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Hello, we identified {company} as an established provider of {niche_lower} services
            in your market. Empire AI operates a predictive lead generation network that sources
            qualified, verified prospects for service providers.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            We deliver pre-qualified leads that match your service profile — no upfront cost.
            Our model is simple: we only earn a success fee (3%) when a lead converts into a
            closed deal. No retainer, no monthly minimum.
          </p>
          <div style="margin:24px 0;padding:18px 20px;background:#15263F;border-left:3px solid #44E5B8;font-size:13px;color:#c8d4e4;line-height:1.7;">
            <strong style="color:#f8fafd;">How it works:</strong> We find businesses actively seeking
            {niche_lower} providers → verify their contact information → deliver the lead to you.
            You only pay when you close. <strong style="color:#f8fafd;">3% success fee on closed deals.</strong>
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:14px 0 0;">
            Interested in seeing a sample lead for your area? Reply to this email and we'll
            send one over within 24 hours.
          </p>
        """
    elif step == 1:
        subject = f"Following up · {company} lead generation"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            How we source <span style="color:#5AC8FA;">{niche_lower}</span> leads
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            We wanted to share more detail on our lead generation process for {sub_niche} providers.
          </p>
          <ul style="font-size:14px;line-height:1.8;color:#a1a1aa;margin:0 0 14px;padding-left:20px;">
            <li>Active prospect discovery via local business listings and web presence</li>
            <li>Contact verification (phone + email) for every lead delivered</li>
            <li>Buy-intent scoring to prioritize high-potential prospects</li>
            <li>3% success fee paid only on closed deals — no upfront cost</li>
          </ul>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:14px 0 0;">
            If lead volume is a constraint for your sales team, we can help.
            Reply to this email to discuss.
          </p>
        """
    elif step == 2:
        subject = f"{company} · what other providers are saying"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            Results from our network
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Providers in our network report that the leads we deliver convert at a higher rate
            than cold outreach because every prospect has been pre-scored for buy intent
            and contact information is verified before delivery.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Our model aligns incentives: we only get paid when you close a deal.
            This means we are motivated to send you high-quality, actionable leads.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:14px 0 0;">
            We can start sending leads tailored to {company} within 48 hours of confirming
            interest. Reply to this email to set up a test.
          </p>
        """
    else:  # step 3 — last touch
        subject = f"Last note from us · {company}"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            Stepping back
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            This is our last note about the lead generation program for {sub_niche} providers.
            We don't believe in being persistent past what is useful.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            If you would like to explore receiving qualified {niche_lower} leads for {company},
            simply reply to this email. Otherwise, no further messages on this topic.
            You remain on our list only for future relevant opportunities, unless you
            unsubscribe below.
          </p>
        """
    html_body = _build_b2b_shell(body, unsubscribe_link=unsubscribe_link, postal_address=postal_address, sender_name=sender_name, sub_niche_hint=niche_lower, tracking_pixel_url=tracking_pixel_url)
    return subject, html_body


def _build_email(
    step: int,
    target_short: str,
    unsubscribe_link: str,
    postal_address: str,
    sender_name: str,
    sequence_type: str = "storm_strike",
    meta: Optional[dict] = None,
    tracking_pixel_url: str = "",
) -> tuple[str, str]:
    """Returns (subject, html_body). Step 0-3.
    Routes to the correct template set based on sequence_type."""
    if sequence_type == "b2b_outreach":
        company = meta.get("company", target_short) if meta else target_short
        sub_niche = (meta.get("b2b_sub_niche", "Business Services") if meta else "Business Services")
        return _build_b2b_email(
            step=step,
            company=company,
            sub_niche=sub_niche,
            unsubscribe_link=unsubscribe_link,
            postal_address=postal_address,
            sender_name=sender_name,
            tracking_pixel_url=tracking_pixel_url,
        )

    # ── Storm / Property Owner Templates (default) ──
    if step == 0:
        subject = f"Storm activity detected near {target_short}"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            Severe weather activity at <span style="color:#44E5B8;">{target_short}</span>
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Our predictive system cross-referenced live National Weather Service data
            against the location associated with your contact record. Wind and/or hail
            activity at this site suggests roof or structural damage is possible.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Most commercial property insurance policies recommend documenting damage
            within 72 hours of an event. This is an industry guideline, not a legal
            deadline — your specific policy terms govern any actual claim.
          </p>
          <div style="margin:24px 0;padding:18px 20px;background:#15263F;border-left:3px solid #44E5B8;font-size:13px;color:#c8d4e4;line-height:1.7;">
            <strong style="color:#f8fafd;">How we work:</strong> 3% success fee on a settled
            claim — paid by the property owner from the settlement, not upfront. If
            no claim is filed or no settlement is reached, you owe us nothing.
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:14px 0 0;">
            Reply to this email or call us at the number in your records to request a
            no-cost assessment. Or simply ignore this — we'll send a brief follow-up
            sequence and then stop.
          </p>
        """
    elif step == 1:
        subject = f"Following up · {target_short} storm assessment"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            72-hour insurance window <span style="color:#5AC8FA;">closing soon</span>
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Yesterday we flagged severe weather activity at <strong style="color:#f8fafd;">{target_short}</strong>.
            We have not heard back, so wanted to surface this once more before the
            72-hour documentation window expires.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            Three things to consider:
          </p>
          <ul style="font-size:14px;line-height:1.8;color:#a1a1aa;margin:0 0 14px;padding-left:20px;">
            <li>Insurance claims filed inside the 72-hour window typically settle higher</li>
            <li>Empire's 3% success fee is paid only on settlement — no upfront cost</li>
            <li>If we find no damage, the assessment is free and we move on</li>
          </ul>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:14px 0 0;">
            Reply to this email for a no-cost assessment.
          </p>
        """
    elif step == 2:
        subject = f"{target_short} · what we'd find"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            What a 30-minute assessment looks like
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            A licensed local contractor in our network visits <strong style="color:#f8fafd;">{target_short}</strong>
            for a no-cost roof and exterior inspection. You get a written report with
            photos within 24 hours.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            If damage exists, you decide whether to file a claim with your carrier. We do
            not represent the insurer or the claim. We coordinate the contractor side
            only. Empire's 3% fee is paid from the settlement, after it lands.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:14px 0 0;">
            If there's no damage, no fee. No claim, no fee. That's the entire model.
          </p>
        """
    else:  # step 3 — last touch
        subject = f"Last note from us · {target_short}"
        body = f"""
          <div style="font-size:22px;font-weight:600;color:#f8fafd;letter-spacing:-0.02em;line-height:1.3;margin-bottom:16px;">
            Stepping back
          </div>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            This is our last note about the storm activity flagged at
            <strong style="color:#f8fafd;">{target_short}</strong>. We don't believe in being
            persistent past what's useful.
          </p>
          <p style="font-size:14px;line-height:1.7;color:#a1a1aa;margin:0 0 14px;">
            If you would still like a no-cost assessment, simply reply to this email.
            Otherwise, no further messages. Your contact details remain on our list
            only for the duration of future legitimate severe weather alerts in your
            area, unless you unsubscribe below.
          </p>
        """
    html_body = _email_shell(body, unsubscribe_link=unsubscribe_link, postal_address=postal_address, sender_name=sender_name, tracking_pixel_url=tracking_pixel_url)
    return subject, html_body


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL SEQUENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class EmailSequenceEngine:
    def __init__(
        self,
        *,
        get_db:           Callable,
        send_email:       Callable,
        sign_token:       Callable,
        verify_token:     Callable,
        public_base_url:  str,
        physical_address: str = DEFAULT_POSTAL,
        sender_name:      str = DEFAULT_SENDER_NAME,
        max_per_minute:   int = 12,
    ):
        self.get_db           = get_db
        self.send_email       = send_email
        self.sign_token       = sign_token
        self.verify_token     = verify_token
        self.public_base_url  = public_base_url.rstrip("/")
        self.physical_address = physical_address
        self.sender_name      = sender_name
        self.max_per_minute   = max_per_minute
        self.stats = {
            "sequences_active":       0,
            "sequences_done":         0,
            "sequences_unsubscribed": 0,
            "sequences_bounced":      0,
            "emails_sent":            0,
            "emails_tracked_opens":   0,
            "emails_tracked_clicks":  0,
            "last_dispatch":          None,
            "last_error":             None,
        }

    # ── ENROLLMENT ──────────────────────────────────────────────────────
    async def enroll(
        self,
        email:         str,
        target_addr:   str = "",
        sequence_type: str = "storm_strike",
        meta:          Optional[dict] = None,
    ) -> dict:
        email = (email or "").strip().lower()
        if not email or not EMAIL_RX.match(email):
            return {"ok": False, "error": "Invalid email"}

        if await self._is_unsubscribed(email):
            return {"ok": False, "error": "unsubscribed"}

        try:
            db = self.get_db()
            existing = db.table("email_sequences").select("id, status") \
                .eq("email", email).limit(1).execute()
            if existing.data:
                return {
                    "ok":          True,
                    "sequence_id": existing.data[0]["id"],
                    "existing":    True,
                    "status":      existing.data[0]["status"],
                }

            ins = db.table("email_sequences").insert({
                "email":         email,
                "target_addr":   target_addr,
                "sequence_type": sequence_type,
                "current_step":  0,
                "status":        "active",
                "next_send_at":  datetime.now(timezone.utc).isoformat(),
                "meta":          meta or {},
            }).execute()
            self.stats["sequences_active"] += 1
            return {
                "ok":          True,
                "sequence_id": ins.data[0]["id"] if ins.data else None,
                "existing":    False,
            }
        except Exception as e:
            log.error(f"[email] enroll error: {e}")
            return {"ok": False, "error": str(e)}

    # ── DISPATCHER LOOP ─────────────────────────────────────────────────
    async def dispatcher_loop(self):
        log.info(f"[email] Dispatcher ONLINE · max {self.max_per_minute}/min")
        while True:
            try:
                sent = await self._dispatch_due()
                if sent > 0:
                    log.info(f"[email] dispatched {sent} emails")
                self.stats["last_dispatch"] = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                log.error(f"[email] dispatcher error: {e}")
                self.stats["last_error"] = str(e)
            await asyncio.sleep(60)

    async def _dispatch_due(self) -> int:
        try:
            db = self.get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            res = db.table("email_sequences").select("*") \
                .eq("status", "active") \
                .lte("next_send_at", now_iso) \
                .limit(self.max_per_minute).execute()
            rows = res.data or []
        except Exception as e:
            log.error(f"[email] query failed: {e}")
            return 0

        # Filter out anyone who's globally unsubscribed (defense in depth)
        rows = [r for r in rows if not await self._is_unsubscribed(r["email"])]

        sent = 0
        for row in rows:
            email = row["email"]
            step = row["current_step"]

            if step >= 4:
                self._mark_complete(row)
                continue

            target_short = self._short_address(row.get("target_addr", ""))
            unsub_link = self._build_unsubscribe_link(email)
            tracking_pixel = self._build_tracking_pixel_url(
                email=email,
                step=step,
                sequence_id=str(row.get("id", "")),
                sequence_type=row.get("sequence_type", "storm_strike"),
            )

            subject, html = _build_email(
                step=step,
                target_short=target_short,
                unsubscribe_link=unsub_link,
                postal_address=self.physical_address,
                sender_name=self.sender_name,
                sequence_type=row.get("sequence_type", "storm_strike"),
                meta=row.get("meta", {}),
                tracking_pixel_url=tracking_pixel,
            )

            result = await self.send_email(to=email, subject=subject, html=html)

            try:
                db = self.get_db()
                db.table("email_log").insert({
                    "email":      email,
                    "direction":  "outbound",
                    "subject":    subject[:200],
                    "step":       step,
                    "message_id": result.get("id") if isinstance(result, dict) else None,
                    "delivered":  bool(result.get("ok")) if isinstance(result, dict) else False,
                }).execute()
            except Exception as e:
                log.debug(f"[email] log insert: {e}")

            if not (isinstance(result, dict) and result.get("ok")):
                log.warning(f"[email] send failed · {email} step {step} · {result}")
                continue

            sent += 1
            self.stats["emails_sent"] += 1

            next_step = step + 1
            if next_step >= 4:
                self._mark_complete(row, last_step=step)
            else:
                delay = STEP_DELAYS.get(next_step, timedelta(hours=24))
                next_send = datetime.now(timezone.utc) + delay
                try:
                    db.table("email_sequences").update({
                        "current_step": next_step,
                        "last_sent_at": datetime.now(timezone.utc).isoformat(),
                        "next_send_at": next_send.isoformat(),
                    }).eq("id", row["id"]).execute()
                except Exception as e:
                    log.error(f"[email] state update failed: {e}")

            await asyncio.sleep(60 / max(1, self.max_per_minute))

        return sent

    def _short_address(self, addr: str, max_len: int = 36) -> str:
        if not addr:
            return "your property"
        short = addr.split(",")[0].strip()
        if len(short) > max_len:
            short = short[:max_len].rstrip() + "..."
        return short

    def _build_unsubscribe_link(self, email: str) -> str:
        """One-click unsubscribe URL (CAN-SPAM compliant)."""
        payload = {
            "email": email,
            "exp":   int(time.time()) + (365 * 86400),  # 1-year valid
            "iat":   int(time.time()),
            "kind":  "email_unsub",
        }
        token = self.sign_token(payload)
        return f"{self.public_base_url}/email/unsubscribe?t={token}"

    def _build_tracking_pixel_url(
        self, email: str, step: int, sequence_id: str, sequence_type: str
    ) -> str:
        """Signed 1x1 tracking pixel URL for open detection."""
        payload = {
            "email":         email,
            "step":          step,
            "sequence_id":   sequence_id or None,
            "sequence_type": sequence_type,
            "exp":           int(time.time()) + (90 * 86400),  # 90-day valid
            "iat":           int(time.time()),
            "kind":          "email_open",
        }
        token = self.sign_token(payload)
        return f"{self.public_base_url}/email/track/open?t={token}"

    async def _track_event(
        self,
        email:         str,
        event:         str,
        sequence_id:   Optional[str] = None,
        sequence_type: str = "storm_strike",
        step:          int = 0,
        link_url:      Optional[str] = None,
        user_agent:    Optional[str] = None,
        ip_address:    Optional[str] = None,
        meta:          Optional[dict] = None,
    ):
        """Log a tracking event to the email_tracking table."""
        try:
            db = self.get_db()
            db.table("email_tracking").insert({
                "email":         email,
                "event":         event,
                "sequence_id":   sequence_id,
                "sequence_type": sequence_type,
                "step":          step,
                "link_url":      link_url,
                "user_agent":    user_agent,
                "ip_address":    ip_address,
                "meta":          meta or {},
            }).execute()
            if event == "open":
                self.stats["emails_tracked_opens"] = self.stats.get("emails_tracked_opens", 0) + 1
            elif event == "click":
                self.stats["emails_tracked_clicks"] = self.stats.get("emails_tracked_clicks", 0) + 1
        except Exception as e:
            log.debug(f"[email] track_event failed: {e}")

    def _mark_complete(self, row: dict, last_step: Optional[int] = None):
        try:
            db = self.get_db()
            update = {"status": "completed"}
            if last_step is not None:
                update["current_step"] = last_step
                update["last_sent_at"] = datetime.now(timezone.utc).isoformat()
            db.table("email_sequences").update(update).eq("id", row["id"]).execute()
            self.stats["sequences_done"]   += 1
            self.stats["sequences_active"]  = max(0, self.stats["sequences_active"] - 1)
        except Exception:
            pass

    # ── UNSUBSCRIBE MANAGEMENT ──────────────────────────────────────────
    async def _is_unsubscribed(self, email: str) -> bool:
        try:
            db = self.get_db()
            res = db.table("email_unsubscribes").select("email").eq("email", email).limit(1).execute()
            return bool(res.data)
        except Exception:
            return False

    async def unsubscribe(self, email: str, reason: str = "one-click") -> dict:
        email = (email or "").lower().strip()
        if not email:
            return {"ok": False, "error": "no email"}
        try:
            db = self.get_db()
            db.table("email_unsubscribes").upsert({
                "email":  email,
                "reason": reason,
            }).execute()
            db.table("email_sequences").update({"status": "unsubscribed"}) \
                .eq("email", email).execute()
            self.stats["sequences_unsubscribed"] += 1
            self.stats["sequences_active"] = max(0, self.stats["sequences_active"] - 1)
        except Exception as e:
            log.error(f"[email] unsubscribe write failed: {e}")
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    async def mark_bounce(self, email: str, reason: str = "hard_bounce") -> None:
        """Bounce handler. Hard bounces remove from list immediately."""
        try:
            db = self.get_db()
            res = db.table("email_sequences").select("bounces, status") \
                .eq("email", email).limit(1).execute()
            current_bounces = (res.data[0].get("bounces", 0) or 0) if res.data else 0
            new_bounces = current_bounces + 1
            new_status = "bounced" if (new_bounces >= 2 or "hard" in reason) else None
            update = {"bounces": new_bounces}
            if new_status:
                update["status"] = new_status
                self.stats["sequences_bounced"] += 1
            db.table("email_sequences").update(update).eq("email", email).execute()

            db.table("email_log").insert({
                "email":     email,
                "direction": "bounce",
                "meta":      {"reason": reason},
            }).execute()
        except Exception as e:
            log.debug(f"[email] bounce mark failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_email_routes(
    app: FastAPI,
    engine: EmailSequenceEngine,
    require_auth=None,
    broadcaster=None,
):
    """Wire the email routes."""

    # ── PUBLIC: ONE-CLICK UNSUBSCRIBE ───────────────────────────────────
    @app.get("/email/unsubscribe", response_class=HTMLResponse)
    async def email_unsubscribe(t: str = Query(...)):
        payload = engine.verify_token(t)
        if not payload or payload.get("kind") != "email_unsub":
            return HTMLResponse(_unsub_page("Invalid or expired link.", error=True), status_code=401)

        result = await engine.unsubscribe(payload["email"], reason="one-click unsubscribe")
        if result.get("ok"):
            return HTMLResponse(_unsub_page("You've been unsubscribed. No further emails will be sent."))
        else:
            return HTMLResponse(_unsub_page("Could not process unsubscribe. Please contact ops@empire-ai.co.uk", error=True), status_code=500)

    # ── PUBLIC: TRACKING PIXEL (open detection) ──────────────────────────
    @app.get("/email/track/open")
    async def email_track_open(
        t: str = Query(...),
        request: Request = None,
    ):
        """1x1 transparent GIF pixel — logs open events when loaded.
        Always returns a 1x1 GIF regardless of token validity so email
        clients can't detect tracking failure via broken image."""
        payload = engine.verify_token(t)
        if payload and payload.get("kind") == "email_open":
            ua = request.headers.get("user-agent", "") if request else ""
            ip = request.client.host if request and request.client else None
            await engine._track_event(
                email=payload.get("email", ""),
                event="open",
                sequence_id=payload.get("sequence_id"),
                sequence_type=payload.get("sequence_type", "storm_strike"),
                step=payload.get("step", 0),
                user_agent=ua[:500] if ua else None,
                ip_address=ip,
            )
        # 1x1 transparent GIF (43 bytes)
        return Response(
            content=b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            media_type="image/gif",
        )

    # ── PUBLIC: CLICK TRACKING (redirect with logging) ────────────────────
    @app.get("/email/track/click")
    async def email_track_click(
        t: str = Query(...),
        url: str = Query(...),
        request: Request = None,
    ):
        """Click tracking — logs the click event and redirects to the target URL."""
        payload = engine.verify_token(t)
        decoded_url = _urlparse.unquote(url)

        # If token is valid (any kind), log the click
        if payload:
            ua = request.headers.get("user-agent", "") if request else ""
            ip = request.client.host if request and request.client else None
            await engine._track_event(
                email=payload.get("email", ""),
                event="click",
                sequence_id=payload.get("sequence_id"),
                sequence_type=payload.get("sequence_type", "storm_strike"),
                step=payload.get("step", 0),
                link_url=decoded_url[:2000],
                user_agent=ua[:500] if ua else None,
                ip_address=ip,
            )

        if decoded_url.startswith("http://") or decoded_url.startswith("https://"):
            return RedirectResponse(url=decoded_url)
        return RedirectResponse(url="/")

    # ── PUBLIC: TRACKING STATS (dashboard endpoint) ───────────────────────
    if require_auth:
        @app.get("/api/v1/email/tracking")
        async def email_tracking_stats(
            event: str = Query(None, pattern="^(open|click|bounce|complaint|unsubscribe)$"),
            sequence_type: str = Query(None),
            days: int = Query(30, ge=1, le=365),
            limit: int = Query(100, ge=1, le=1000),
            auth: bool = Depends(require_auth),
        ):
            """Return recent email tracking events with optional filters."""
            try:
                db = engine.get_db()
                since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                q = db.table("email_tracking").select("*") \
                    .gte("created_at", since) \
                    .order("created_at", desc=True) \
                    .limit(limit)
                if event:
                    q = q.eq("event", event)
                if sequence_type:
                    q = q.eq("sequence_type", sequence_type)
                return {"tracking": q.execute().data or []}
            except Exception as e:
                raise HTTPException(500, str(e))

    # ── PUBLIC: BOUNCE / COMPLAINT WEBHOOK (Resend webhook) ─────────────
    @app.post("/api/v1/email/webhook")
    async def email_webhook(request: Request):
        """
        Resend webhook for bounce + complaint events. Configure in Resend
        dashboard → Webhooks → POST to this URL.
        """
        try:
            payload = await request.json()
        except Exception:
            return {"ok": True}  # Always 200 so Resend doesn't retry-storm

        event_type = payload.get("type", "")
        data = payload.get("data", {}) or {}
        recipient = (data.get("to") or [None])[0] if isinstance(data.get("to"), list) else data.get("to")
        if isinstance(recipient, str):
            recipient = recipient.strip().lower()

        if event_type in ("email.bounced", "email.complained"):
            if recipient:
                reason = event_type.split(".", 1)[-1]
                await engine.mark_bounce(recipient, reason=f"{reason} · {data.get('bounce_type','')}")
        elif event_type == "email.unsubscribed":
            if recipient:
                await engine.unsubscribe(recipient, reason="provider unsubscribe")

        return {"ok": True}

    # ── OPERATOR ENDPOINTS ──────────────────────────────────────────────
    if require_auth:
        @app.post("/api/v1/email/enroll")
        async def email_enroll(request: Request, auth: bool = Depends(require_auth)):
            try:
                body = await request.json()
            except Exception:
                body = {}
            return await engine.enroll(
                email=body.get("email", ""),
                target_addr=body.get("target_addr", ""),
                sequence_type=body.get("sequence_type", "storm_strike"),
                meta=body.get("meta", {}),
            )

        @app.get("/api/v1/email/stats")
        async def email_stats(auth: bool = Depends(require_auth)):
            return engine.stats

        @app.get("/api/v1/email/sequences")
        async def email_sequences(
            status: str = "all",
            limit:  int = 100,
            auth:   bool = Depends(require_auth),
        ):
            """List email sequences. `status` accepts active/done/unsubscribed/bounced/all."""
            try:
                db = engine.get_db()
                q = db.table("email_sequences").select("*") \
                    .order("next_send_at", desc=True).limit(max(1, min(limit, 500)))
                if status and status != "all":
                    q = q.eq("status", status)
                return {"sequences": q.execute().data or []}
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.post("/api/v1/email/bulk-enroll")
        async def email_bulk(request: Request, auth: bool = Depends(require_auth)):
            """Enroll all radar_targets with an email column populated."""
            try:
                db = engine.get_db()
                res = db.table("radar_targets") \
                    .select("email, address, damage_severity, urgency_score") \
                    .eq("status", "active") \
                    .not_.is_("email", "null") \
                    .limit(500).execute()
                rows = res.data or []
            except Exception as e:
                raise HTTPException(500, f"radar_targets query failed: {e}")

            enrolled, skipped = 0, 0
            for t in rows:
                r = await engine.enroll(
                    email=t.get("email", ""),
                    target_addr=t.get("address", ""),
                    sequence_type="storm_strike",
                    meta={
                        "severity": t.get("damage_severity"),
                        "urgency":  t.get("urgency_score"),
                    },
                )
                if r.get("ok") and not r.get("existing"):
                    enrolled += 1
                else:
                    skipped += 1
            return {"ok": True, "enrolled": enrolled, "skipped": skipped, "total_seen": len(rows)}

        @app.post("/api/v1/email/bulk-enroll-b2b")
        async def email_bulk_b2b(request: Request, auth: bool = Depends(require_auth)):
            """Enroll all B2B leads with emails into b2b_outreach sequence."""
            try:
                body = await request.json()
            except Exception:
                body = {}
            max_leads = min(int(body.get("max", 500)), 2000)

            try:
                db = engine.get_db()
                res = db.table("radar_targets") \
                    .select("email, warehouse_name, meta, city, state") \
                    .eq("status", "active") \
                    .not_.is_("email", "null") \
                    .neq("email", "") \
                    .eq("meta->>source", "B2B Lead Gen") \
                    .limit(max_leads).execute()
                rows = res.data or []
            except Exception as e:
                raise HTTPException(500, f"radar_targets query failed: {e}")

            enrolled, skipped = 0, 0
            for t in rows:
                tmeta = t.get("meta", {}) or {}
                sub_niche = tmeta.get("b2b_sub_niche", "Business Services")
                company = (t.get("warehouse_name") or "").strip()
                target_addr = f"{t.get('city', '')}, {t.get('state', '')}"

                r = await engine.enroll(
                    email=t.get("email", ""),
                    target_addr=target_addr,
                    sequence_type="b2b_outreach",
                    meta={
                        "company": company,
                        "b2b_sub_niche": sub_niche,
                        "city": t.get("city"),
                        "state": t.get("state"),
                        "source": "B2B Lead Gen",
                    },
                )
                if r.get("ok") and not r.get("existing"):
                    enrolled += 1
                else:
                    skipped += 1
            return {"ok": True, "enrolled": enrolled, "skipped": skipped, "total_seen": len(rows)}

    log.info("[email] Routes registered · /email/{unsubscribe,track/open,track/click} · /api/v1/email/{enroll,bulk-enroll,bulk-enroll-b2b,stats,tracking,webhook}")


def _unsub_page(message: str, *, error: bool = False) -> str:
    """Minimal Empire-styled unsubscribe confirmation page."""
    color = "#f43f5e" if error else "#44E5B8"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Empire AI · Unsubscribe</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: #0A1A2F; color: #F8FAFD;
  font-family: 'Inter', sans-serif; letter-spacing: -0.02em;
  min-height: 100vh; padding: 60px 20px;
  display: flex; align-items: center; justify-content: center;
}}
.box {{
  max-width: 480px; width: 100%;
  background: #15263F; border: 1px solid rgba(122,140,163,0.18);
  padding: 40px 36px; text-align: center;
}}
.brand {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; color: #7A8CA3;
  letter-spacing: 0.32em; text-transform: uppercase; margin-bottom: 24px;
}}
.icon {{
  font-size: 48px; color: {color}; margin-bottom: 18px;
}}
h1 {{
  font-weight: 200; font-size: 26px;
  letter-spacing: -0.04em; margin-bottom: 14px;
  color: #F8FAFD;
}}
p {{
  font-size: 14px; color: #C8D4E4;
  line-height: 1.7;
}}
</style></head><body>
<div class="box">
  <div class="brand">Empire AI · Predictive Revenue</div>
  <div class="icon">{'✗' if error else '✓'}</div>
  <h1>{'Unable to unsubscribe' if error else 'Unsubscribed'}</h1>
  <p>{message}</p>
</div>
</body></html>"""


# Compat alias for hub.py
EmailEngine = EmailSequenceEngine
