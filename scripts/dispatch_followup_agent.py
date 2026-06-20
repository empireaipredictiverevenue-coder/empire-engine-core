#!/usr/bin/env python3
"""
EMPIRE V49 · DISPATCH FOLLOW-UP AGENT
======================================
Queries dispatches where status='sent' and meta->>'follow_up_due' < now(),
sends SMS reminders to contractors on a cadence.

Cadences after initial dispatch:
    24h  → follow_up_1  (gentle nudge)
    72h  → follow_up_2  (urgency reminder)
    7d   → follow_up_3  (final notice)
    After 3 follow-ups: mark dispatch as 'expired' (contractor unresponsive)

Run modes:
    python3 scripts/dispatch_followup_agent.py                # live — sends SMS
    python3 scripts/dispatch_followup_agent.py --dry-run       # report only
    python3 scripts/dispatch_followup_agent.py --now           # force-send NOW (skip due check)

Tracks every follow-up in dispatches.meta.follow_up_history for audit trail.
"""

import os
import sys
import json
import uuid
import asyncio
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client
import httpx

log = logging.getLogger("dispatch_followup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "dispatch_followup_agent"

# ── Follow-up cadence: hours after DISPATCH (not from last follow-up) ──
# Index 0 (24h) is the initial delay set in empire_matching.py.
# Indices 1+ are the cadence milestones for follow-up_1, follow-up_2, etc.
# After each follow-up, next_due = dispatch.created_at + FOLLOW_UP_HOURS[follow_up_num]
FOLLOW_UP_HOURS = [24, 72, 168]  # dispatch+24h (init), +72h, +168h (7d)
MAX_FOLLOW_UPS = len(FOLLOW_UP_HOURS)  # 3 follow-ups: 24h, 72h, 168h from dispatch

# Rate limit between sends (seconds)
SEND_DELAY = 0.5


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _normalize_phone(phone: str) -> str:
    """Strip to E.164 +1XXXXXXXXXX format."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return phone if phone.startswith("+") else f"+1{digits}" if digits else ""


def _extract_first_name(name: str) -> str:
    """Safe first-name extraction."""
    if not name:
        return "Contractor"
    return name.strip().split()[0]


async def _send_sms_vonage(to_number: str, message: str, vonage_number: str) -> dict:
    """Send SMS via Vonage Messages API (JWT auth)."""
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")

    if not app_id or not os.path.exists(key_path):
        return {"ok": False, "error": "Vonage JWT credentials not configured"}
    if not vonage_number:
        return {"ok": False, "error": "VONAGE_NUMBER not set"}

    try:
        with open(key_path, "r") as f:
            private_key = f.read()

        import jwt as pyjwt
        import time as _time

        now = int(_time.time())
        payload = {
            "iat": now,
            "exp": now + 180,
            "jti": str(uuid.uuid4()),
            "application_id": app_id,
        }
        token = pyjwt.encode(payload, private_key, algorithm="RS256")

        number = vonage_number.lstrip("+")
        payload = {
            "from": number,
            "to": to_number.lstrip("+"),
            "message_type": "text",
            "text": message[:1000],
            "channel": "sms",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.nexmo.com/v1/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            result = r.json()
            if r.status_code == 202:
                return {"ok": True, "message_id": result.get("message_uuid", "")}
            else:
                detail = result.get("detail", str(result)[:200])
                title = result.get("title", "")
                return {"ok": False, "error": f"Vonage {r.status_code}: {title} {detail}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _build_followup_body(
    first_name: str,
    lead_city: str,
    lead_addr: str,
    urgency: int,
    follow_up_num: int,
    accept_link: str,
) -> str:
    """Build the follow-up SMS body. Tone escalates with follow-up #."""
    city = lead_city or "your area"
    addr = lead_addr or "a property"

    if follow_up_num == 1:
        # Gentle nudge — 24h
        return (
            f"{first_name}, quick reminder — the {city} lead at "
            f"{addr} is still available. First to accept wins. "
            f"Accept: {accept_link[:180]} STOP to opt out"
        )
    elif follow_up_num == 2:
        # Urgency push — 72h
        return (
            f"{first_name}, {city} lead at {addr} expiring soon. "
            f"72hr insurance window closing. "
            f"Accept: {accept_link[:180]} STOP to opt out"
        )
    else:
        # Final notice — 7d
        return (
            f"{first_name}, final notice — {city} lead at {addr} "
            f"will be released to the next contractor. "
            f"Accept now: {accept_link[:180]} STOP to opt out"
        )


async def _log_followup_attempt(
    dispatch_id: str,
    contractor_id: str,
    contractor_name: str,
    phone: str,
    follow_up_num: int,
    success: bool,
    message: str,
):
    """Log a follow-up attempt to agent_activity."""
    try:
        sb = _sb()
        sb.table("agent_activity").insert({
            "agent_name": AGENT_NAME,
            "run_id": str(uuid.uuid4()),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok" if success else "error",
            "rows_seen": 1,
            "rows_processed": 1 if success else 0,
            "rows_errored": 0 if success else 1,
            "summary": (
                f"dispatch_followup: dispatch={dispatch_id[:12]} "
                f"contractor={contractor_name[:20]} "
                f"follow_up=#{follow_up_num} "
                f"{'SENT' if success else 'FAILED'}: {message[:60]}"
            ),
            "meta": {
                "dispatch_id": dispatch_id,
                "contractor_id": contractor_id,
                "contractor_name": contractor_name,
                "phone": phone,
                "follow_up_num": follow_up_num,
                "success": success,
                "detail": message[:500],
            },
        }).execute()
    except Exception as e:
        log.debug(f"Failed to log follow-up attempt: {e}")


async def run_followups(
    dry_run: bool = False,
    force_now: bool = False,
    force_dispatch_id: Optional[str] = None,
) -> dict:
    """Main follow-up pipeline."""
    sb = _sb()
    started_at = datetime.now(timezone.utc)
    now_iso = started_at.isoformat()

    # ── Channel config ──────────────────────────────────────────────────
    vonage_number = os.getenv("VONAGE_NUMBER", "")
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    sms_enabled = bool(app_id and os.path.exists(key_path) and vonage_number)

    if not sms_enabled:
        log.info("SMS not configured — running in log-only mode")

    # ── 1. Fetch dispatches due for follow-up ───────────────────────────
    # Query: status='sent' and (meta->>'follow_up_due' < now() or force_now)

    if force_dispatch_id:
        r = sb.table("dispatches").select(
            "id, created_at, contractor_id, lead_id, match_score, "
            "token, status, meta"
        ).eq("id", force_dispatch_id).eq("status", "sent").limit(1).execute()
    else:
        # PostgREST can't do JSON path filtering on meta->>'follow_up_due' < time
        # So we pull all 'sent' dispatches and filter in Python
        r = sb.table("dispatches").select(
            "id, created_at, contractor_id, lead_id, match_score, "
            "token, status, meta"
        ).eq("status", "sent").order("created_at", desc=True).limit(500).execute()

    all_sent = r.data or []
    log.info(f"Fetched {len(all_sent)} dispatches with status='sent'")

    # Filter to those with follow_up_due in the past (or force_now)
    due = []
    for d in all_sent:
        meta = d.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        follow_up_due = meta.get("follow_up_due", "")
        follow_up_history = meta.get("follow_up_history") or []

        if not follow_up_due and not force_now:
            continue  # no due date set, not forced — skip

        is_due = False
        if force_now:
            is_due = True
        elif follow_up_due:
            try:
                due_dt = datetime.fromisoformat(follow_up_due.replace("Z", "+00:00"))
                is_due = due_dt <= datetime.now(timezone.utc)
            except Exception:
                is_due = False

        if not is_due:
            continue

        # Check max follow-ups
        if len(follow_up_history) >= MAX_FOLLOW_UPS:
            continue  # already maxed out

        due.append(d)

    log.info(f"Due for follow-up: {len(due)} (of {len(all_sent)} sent)")

    # ── 2. Batch-fetch contractors + leads ──────────────────────────────
    contractor_ids = list(set(d.get("contractor_id") for d in due if d.get("contractor_id")))
    lead_ids = list(set(d.get("lead_id") for d in due if d.get("lead_id")))

    contractors: dict = {}
    if contractor_ids:
        # Batch query — single IN query instead of N individual queries
        cr = sb.table("contractors").select("id, name, phone, email") \
            .in_("id", contractor_ids).limit(500).execute()
        for row in (cr.data or []):
            contractors[row["id"]] = row

    leads: dict = {}
    if lead_ids:
        # Batch query — single IN query instead of N individual queries
        lr = sb.table("radar_targets").select("id, address, city, damage_severity") \
            .in_("id", lead_ids).limit(500).execute()
        for row in (lr.data or []):
            leads[row["id"]] = row

    # ── 3. Build the public base URL for accept links ───────────────────
    public_base_url = os.getenv("PUBLIC_BASE_URL", "https://empire-ai.co.uk").rstrip("/")

    # ── 4. Process each due dispatch ────────────────────────────────────
    results = []
    sent_count = 0
    expired_count = 0
    skipped_no_phone = 0
    errors = 0

    for dispatch in due:
        did = dispatch["id"]
        cid = dispatch.get("contractor_id")
        lid = dispatch.get("lead_id")
        token = dispatch.get("token", "")
        meta = dispatch.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        follow_up_history = meta.get("follow_up_history") or []
        follow_up_num = len(follow_up_history) + 1  # 1-indexed

        contractor = contractors.get(cid) if cid else None
        lead = leads.get(lid) if lid else None

        if not contractor:
            log.info(f"  SKIP {did[:12]}: contractor {cid[:12] if cid else '?'} not found")
            skipped_no_phone += 1
            continue

        name = (contractor.get("name") or "Contractor").strip()
        phone = _normalize_phone(contractor.get("phone") or "")
        first_name = _extract_first_name(name)

        if not phone:
            log.info(f"  SKIP {did[:12]}: {name[:20]} — no phone, expiring dispatch")
            skipped_no_phone += 1
            # Expire immediately — unreachable, no point keeping it open
            try:
                sb.table("dispatches").update({
                    "status": "expired",
                    "meta": {
                        **meta,
                        "expired_reason": "unreachable_no_phone",
                        "follow_up_history": follow_up_history,
                    },
                }).eq("id", did).execute()
                expired_count += 1
                log.info(f"  EXPIRED {did[:12]}: {name[:20]} — unreachable, no phone")
            except Exception as e:
                log.warning(f"  Failed to expire {did[:12]}: {e}")
            continue

        # Build accept link from token
        token_val = token
        # Handle case where token is a dict (already decoded)
        if isinstance(token_val, dict):
            token_val = token_val.get("token", "")
        accept_link = f"{public_base_url}/dispatch/accept?t={token_val}" if token_val else ""

        # Get lead context
        lead_city = lead.get("city", "") if lead else meta.get("lead_metro", "")
        lead_addr = lead.get("address", "") if lead else meta.get("lead_addr", "")
        urgency = int(meta.get("urgency", 7))

        # Build follow-up body
        sms_body = _build_followup_body(
            first_name=first_name,
            lead_city=lead_city,
            lead_addr=lead_addr,
            urgency=urgency,
            follow_up_num=follow_up_num,
            accept_link=accept_link,
        )

        log.info(
            f"  {'DRY-RUN' if dry_run else 'SENDING'}: "
            f"dispatch={did[:12]}  contractor={name[:20]}  "
            f"phone={phone}  follow_up=#{follow_up_num}"
        )

        if not dry_run and sms_enabled:
            result = await _send_sms_vonage(phone, sms_body, vonage_number)
            success = result.get("ok", False)
            message_id = result.get("message_id", "")

            if success:
                sent_count += 1

                # Record in sms_log
                try:
                    sb.table("sms_log").insert({
                        "phone": phone,
                        "direction": "outbound",
                        "body": sms_body,
                        "step": follow_up_num,
                        "message_uuid": message_id,
                        "delivered": True,
                    }).execute()
                except Exception as e:
                    log.debug(f"  sms_log insert failed: {e}")

                # Update dispatch meta: set next follow_up_due, append to history
                new_history = list(follow_up_history)
                new_history.append({
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "follow_up_num": follow_up_num,
                    "channel": "sms",
                    "phone": phone,
                    "status": "sent",
                    "body_preview": sms_body[:100],
                    "message_id": message_id or None,
                })

                if follow_up_num < MAX_FOLLOW_UPS:
                    # Compute next due from dispatch time (not from now) so cadence
                    # is relative to the original dispatch, not the last follow-up.
                    # follow_up_num is 1-indexed; FOLLOW_UP_HOURS[0] = 24h is the
                    # initial delay set in empire_matching.py, so follow_up_1 →
                    # index 1 = 72h, follow_up_2 → index 2 = 168h.
                    next_hours = FOLLOW_UP_HOURS[follow_up_num]
                    dispatch_created = dispatch.get("created_at", "")
                    if dispatch_created:
                        try:
                            dispatch_dt = datetime.fromisoformat(dispatch_created.replace("Z", "+00:00"))
                            next_due = (dispatch_dt + timedelta(hours=next_hours)).isoformat()
                        except Exception:
                            next_due = (datetime.now(timezone.utc) + timedelta(hours=next_hours)).isoformat()
                    else:
                        next_due = (datetime.now(timezone.utc) + timedelta(hours=next_hours)).isoformat()
                else:
                    next_due = None  # last follow-up — no more due dates

                update_meta = {
                    **meta,
                    "follow_up_history": new_history,
                }
                if next_due:
                    update_meta["follow_up_due"] = next_due

                try:
                    sb.table("dispatches").update({
                        "meta": update_meta,
                    }).eq("id", did).execute()
                    log.info(f"    ✅ Sent follow_up #{follow_up_num}, next due: {next_due or 'N/A (max)'}")
                except Exception as e:
                    log.warning(f"  Failed to update dispatch meta: {e}")

                # If this was the last follow-up, expire the dispatch
                if follow_up_num >= MAX_FOLLOW_UPS:
                    try:
                        sb.table("dispatches").update({
                            "status": "expired",
                            "meta": update_meta,
                        }).eq("id", did).execute()
                        expired_count += 1
                        log.info(f"    🏁 EXPIRED {did[:12]}: {name[:20]} — max follow-ups reached")
                    except Exception as e:
                        log.warning(f"  Failed to expire dispatch: {e}")
            else:
                errors += 1
                log.warning(f"    ❌ SMS failed: {result.get('error', 'unknown')}")

            # Log to agent_activity
            await _log_followup_attempt(
                dispatch_id=did,
                contractor_id=cid,
                contractor_name=name,
                phone=phone,
                follow_up_num=follow_up_num,
                success=success,
                message=message_id or result.get("error", ""),
            )

            # Rate limit
            await asyncio.sleep(SEND_DELAY)
        else:
            # Dry-run or log-only
            if dry_run:
                sent_count += 1  # count for reporting
            else:
                print(f"\n--- SMS would be sent (log-only) ---")
                print(f"  To: {phone}")
                print(f"  Body: {sms_body}")
                print(f"---")
                sent_count += 1

        results.append({
            "dispatch_id": did,
            "contractor": name,
            "phone": phone,
            "lead_city": lead_city,
            "lead_addr": lead_addr,
            "follow_up_num": follow_up_num,
        })

    # ── 5. Summary ──────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "total_sent_dispatches": len(all_sent),
        "due_for_follow_up": len(due),
        "processed": len(results),
        "sent": sent_count,
        "expired": expired_count,
        "skipped_no_phone": skipped_no_phone,
        "errors": errors,
        "force_now": force_now,
        "sms_enabled": sms_enabled,
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 1),
    }

    log.info("=== DISPATCH FOLLOW-UP SUMMARY ===")
    log.info(f"Sent dispatches:       {len(all_sent)}")
    log.info(f"Due for follow-up:     {len(due)}")
    log.info(f"Processed:             {len(results)}")
    log.info(f"Follow-ups sent:       {sent_count}")
    log.info(f"Expired (max reached): {expired_count}")
    log.info(f"Skipped (no phone):    {skipped_no_phone}")
    log.info(f"Errors:                {errors}")
    if force_now:
        log.info(f"Force-now:             YES (due check bypassed)")
    log.info(f"Elapsed:               {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Dispatch Follow-Up Agent — send SMS reminders for unaccepted dispatches"
    )
    p.add_argument("--dry-run", action="store_true",
                    help="Report only — no SMS sending")
    p.add_argument("--now", action="store_true",
                    help="Force send NOW — bypasses follow_up_due timing check")
    p.add_argument("--dispatch-id", type=str, default=None,
                    help="Process a specific dispatch by UUID")
    args = p.parse_args()

    result = asyncio.run(run_followups(
        dry_run=args.dry_run,
        force_now=args.now,
        force_dispatch_id=args.dispatch_id,
    ))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
