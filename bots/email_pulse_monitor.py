"""
EMPIRE V49 · EMAIL PULSE MONITOR
=================================
Lightweight background loop that periodically checks the email pipeline
health and logs notable events. Designed to run as a PM2 service.

Checks every N minutes:
  1. Dispatch queue — overdue sequence count, recently dispatched
  2. Lead nurture tracking — new opens/clicks since last check
  3. Converter backlog — blocked/pending outreach counts
  4. Key event detection — when target emails finally get dispatched
"""

import os
import sys
import json
import asyncio
import logging
import time
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.email_pulse")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [email-pulse] %(message)s",
)

# ── CONFIG ────────────────────────────────────────────────────────────────
INTERVAL_MINUTES = int(os.environ.get("EMAIL_PULSE_INTERVAL_MINUTES", "15"))

# Emails to watch for dispatch events
WATCHED_EMAILS = [
    "info@utility.com",
    "info@vopak.com",
    "info@cj.com",
]

AGENT_NAME = "email_pulse_monitor"


def _sb():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


# ── CHECKS ────────────────────────────────────────────────────────────────

async def check_dispatch_queue(sb, last_state: dict) -> dict:
    """Check overdue sequence count and recently dispatched sequences."""
    now_iso = datetime.now(timezone.utc).isoformat()
    result = {"overdue_count": 0, "recently_dispatched": [], "new_dispatch_events": []}

    try:
        # Overdue count
        r = sb.table("email_sequences").select("id", count="exact") \
            .eq("status", "active") \
            .lte("next_send_at", now_iso) \
            .execute()
        result["overdue_count"] = r.count
    except Exception as e:
        log.warning(f"[check] overdue count failed: {e}")

    # Check watched emails
    for email in WATCHED_EMAILS:
        try:
            r = sb.table("email_sequences").select("email,current_step,status,last_sent_at,next_send_at,sequence_type") \
                .eq("email", email).execute()
            for s in (r.data or []):
                was_dispatched = last_state.get(email, {}).get("dispatched", False)
                now_dispatched = s.get("last_sent_at") is not None

                entry = {
                    "email": s["email"],
                    "step": s["current_step"],
                    "status": s["status"],
                    "last_sent_at": str(s.get("last_sent_at", ""))[:19],
                    "next_send_at": str(s.get("next_send_at", ""))[:19],
                    "dispatched": now_dispatched,
                }

                result["recently_dispatched"].append(entry)

                if now_dispatched and not was_dispatched:
                    result["new_dispatch_events"].append(entry)
                    log.info(f"🎯 {email} DISPATCHED! step={s['current_step']}")

                last_state[email] = {"dispatched": now_dispatched, "step": s.get("current_step", 0)}
        except Exception as e:
            log.debug(f"[check] {email} query failed: {e}")

    return result


async def check_tracking(sb, last_check_iso: str) -> dict:
    """Check for new email tracking events (opens/clicks) since last check.
    Uses created_at timestamp filtering to avoid UUID comparison issues."""
    result = {"new_opens": 0, "new_clicks": 0, "events": [], "last_check_iso": datetime.now(timezone.utc).isoformat()}

    try:
        r = sb.table("email_tracking").select("created_at,email,event,step,sequence_type") \
            .gte("created_at", last_check_iso) \
            .order("created_at", desc=True) \
            .limit(20).execute()

        for t in (r.data or []):
            ts = str(t.get("created_at", ""))[:19]
            ev = t.get("event", "?")
            email = t.get("email", "?")
            step = t.get("step", "?")
            seq = t.get("sequence_type", "?")

            # Only log lead_nurture or interesting events
            if seq == "lead_nurture" or ev == "click":
                result["events"].append({
                    "ts": ts, "event": ev, "email": email,
                    "step": step, "sequence_type": seq,
                })
                if ev == "open":
                    result["new_opens"] += 1
                elif ev == "click":
                    result["new_clicks"] += 1

    except Exception as e:
        log.debug(f"[check] tracking query failed: {e}")

    return result


async def check_converter_backlog(sb) -> dict:
    """Check counts of leads that still need processing."""
    result = {"blocked_with_email": 0, "pending_outreach": 0}

    try:
        r = sb.table("enriched_leads").select("id", count="exact") \
            .eq("status", "blocked").not_.is_("email", "null").execute()
        result["blocked_with_email"] = r.count

        r = sb.table("enriched_leads").select("id", count="exact") \
            .eq("status", "pending_outreach").not_.is_("email", "null").execute()
        result["pending_outreach"] = r.count
    except Exception as e:
        log.debug(f"[check] converter backlog query failed: {e}")

    return result


# ── LOGGING ───────────────────────────────────────────────────────────────

def log_summary(queue: dict, tracking: dict, backlog: dict):
    """Log a concise summary of the email pipeline state."""
    lines = []

    # Queue
    overdue = queue.get("overdue_count", 0)
    new_dispatches = queue.get("new_dispatch_events", [])
    lines.append(f"📬 queue: {overdue} overdue")
    if new_dispatches:
        for ev in new_dispatches:
            lines.append(f"   🎯 {ev['email']} → step {ev['step']}")
    for entry in queue.get("recently_dispatched", []):
        if entry["dispatched"]:
            icon = "✅"
            lines.append(f"   {icon} {entry['email']:35s} step={entry['step']}  next={entry['next_send_at']}")
        else:
            lines.append(f"   ⏳ {entry['email']:35s} step={entry['step']}  next={entry['next_send_at']}")

    # Tracking
    opens = tracking.get("new_opens", 0)
    clicks = tracking.get("new_clicks", 0)
    if opens or clicks:
        lines.append(f"📊 tracking: {opens} new opens, {clicks} new clicks")
        for ev in tracking.get("events", []):
            icon = "👁️" if ev["event"] == "open" else "🔵"
            lines.append(f"   {icon} {ev['email']:35s} {ev['event']} step={ev['step']} ({ev['sequence_type']})")

    # Backlog
    blocked = backlog.get("blocked_with_email", 0)
    pending = backlog.get("pending_outreach", 0)
    if blocked or pending:
        lines.append(f"📋 leads: {pending} pending, {blocked} blocked w/ email")

    if lines:
        log.info(" | ".join(lines))
    else:
        log.info("[cycle] no notable changes")


# ── BACKGROUND LOOP ───────────────────────────────────────────────────────

async def run_loop(interval_minutes: int = None):
    """Background loop: check email pipeline health every N minutes."""
    if interval_minutes is None:
        interval_minutes = INTERVAL_MINUTES

    log.info(f"🟢 Email Pulse Monitor ONLINE · interval={interval_minutes}m")
    sb = _sb()

    # State tracking across cycles
    last_state: dict = {}  # email -> {dispatched, step}
    last_event_id: int = 0

    # Initial state: capture current dispatch status
    try:
        r = sb.table("email_sequences").select("email,current_step,last_sent_at") \
            .in_("email", WATCHED_EMAILS).execute()
        for s in (r.data or []):
            last_state[s["email"]] = {
                "dispatched": s.get("last_sent_at") is not None,
                "step": s.get("current_step", 0),
            }
    except Exception:
        pass

    last_check_iso = datetime.now(timezone.utc).isoformat()

    cycles = 0
    while True:
        try:
            queue = await check_dispatch_queue(sb, last_state)
            tracking_result = await check_tracking(sb, last_check_iso)
            last_check_iso = tracking_result.get("last_check_iso", last_check_iso)
            backlog = await check_converter_backlog(sb)

            # Log heartbeat
            log_summary(queue, tracking_result, backlog)

            # Log to agent_activity
            try:
                new_dispatch_count = len(queue.get("new_dispatch_events", []))
                new_tracking_count = tracking_result.get("new_opens", 0) + tracking_result.get("new_clicks", 0)
                sb.table("agent_activity").insert({
                    "agent_name": AGENT_NAME,
                    "run_id": str(_uuid.uuid4()),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "ok",
                    "rows_seen": queue.get("overdue_count", 0),
                    "rows_processed": new_dispatch_count + new_tracking_count,
                    "rows_errored": 0,
                    "summary": f"{queue['overdue_count']} overdue, {new_dispatch_count} new dispatches, {new_tracking_count} new events",
                }).execute()
            except Exception as e:
                log.warning(f"agent_activity insert failed: {e}")

            cycles += 1
        except Exception as e:
            log.error(f"[cycle] error: {e}")

        await asyncio.sleep(interval_minutes * 60)


# ── STANDALONE CLI ────────────────────────────────────────────────────────

def run():
    """Sync entry point for PM2 / main.py compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Empire Email Pulse Monitor")
    p.add_argument("--interval", type=int, default=15, help="Polling interval in minutes")
    args = p.parse_args()
    asyncio.run(run_loop(args.interval))
