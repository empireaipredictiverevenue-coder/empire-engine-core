"""
EMPIRE V49 · BOUNTY TRACKER
============================
Automatically marks contractor referral bounties as 'earned' when the
referred contractor's first fee_event is created.

FLOW
  1. A fee_event is created (via webhook, operator, or carrier)
  2. check_bounty_eligible() is called with the fee_event
  3. Looks up contractor_referrals where referred_contractor_id matches
     AND bounty_status = 'pending'
  4. Checks if this is the referred contractor's FIRST fee_event
  5. If both conditions are met:
     a. Updates contractor_referrals: bounty_status = 'earned',
        bounty_paid_at = now()
     b. Creates a referral_payouts record with status = 'earned'
     c. Sends an ntfy notification to the referrer
     d. Returns the reward payload

BACKGROUND LOOP (optional, for catching missed events):
  python bots/bounty_tracker.py --catchup
  Scans fee_events created in the last N hours that haven't triggered
  a bounty check, and runs check_bounty_eligible for each.

WIRE-UP IN HUB:
  from bots.bounty_tracker import check_bounty_eligible
  # Called inside fee event creation endpoints
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.bounty_tracker")

# ── BOUNTY CONFIG ─────────────────────────────────────────────────────
DEFAULT_BOUNTY_AMOUNT = 500.00
BOUNTY_NOTE = "Auto-earned on referred contractor's first settled claim"

# ── NTFY HELPER ──────────────────────────────────────────────────────


async def _push_ntfy(title: str, message: str, tags: str = "money-bag") -> None:
    """Push an ntfy notification. Silent if NTFY_TOPIC not configured."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    token = os.getenv("NTFY_TOKEN", "").strip() if os.getenv("NTFY_TOKEN") else ""
    if not topic:
        log.debug("[bounty_tracker] NTFY_TOPIC not set — skipping ntfy notification")
        return
    try:
        import httpx
        headers = {"Title": title[:200], "Tags": tags, "Priority": "5"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://ntfy.sh/{topic}",
                content=message[:1500],
                headers=headers,
            )
            log.info(f"[bounty_tracker] ntfy push sent: {title}")
    except Exception as e:
        log.warning(f"[bounty_tracker] ntfy push failed: {e}")


async def _send_referrer_sms(phone: str, referrer_name: str, bounty_amount: float) -> None:
    """Send a follow-up SMS to the referrer when their bounty is earned.
    Silent if Vonage env vars are not configured."""
    if not phone:
        return
    try:
        import httpx
        vonage_key = os.getenv("VONAGE_API_KEY", "").strip()
        vonage_secret = os.getenv("VONAGE_API_SECRET", "").strip()
        vonage_from = os.environ.get("VONAGE_NUMBER", "").strip()
        if not (vonage_key and vonage_secret and vonage_from):
            log.debug("[bounty_tracker] Vonage not configured — skipping referrer SMS")
            return

        sms_text = (
            f"Empire AI: The contractor you referred just closed their first deal! "
            f"Your ${bounty_amount:,.0f} referral bounty has been earned. "
            f"We'll process your payout within 30 days after you request it from your dashboard. "
            f"Reply STOP to opt out."
        )
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://rest.nexmo.com/sms/json",
                data={
                    "api_key": vonage_key,
                    "api_secret": vonage_secret,
                    "from": vonage_from,
                    "to": phone,
                    "text": sms_text[:1600],
                },
            )
            log.info(f"[bounty_tracker] referrer SMS sent to {phone}: ${bounty_amount:,.0f} bounty earned")
    except Exception as e:
        log.warning(f"[bounty_tracker] referrer SMS failed: {e}")


# ── CORE BOUNTY CHECK ────────────────────────────────────────────────


async def check_bounty_eligible(
    fee_event: dict,
    *,
    db: Optional[object] = None,
    get_db: Optional[Callable] = None,
) -> dict:
    """
    Called after a fee_event is created. Checks if the contractor who
    earned the fee was referred by another contractor, and if this is
    their FIRST fee_event. If so, marks the bounty as earned.

    Args:
        fee_event: The fee_event dict that was just inserted (must have
                   contractor_id and id)
        db: Optional supabase client (if already open)
        get_db: Optional callable to create a supabase client

    Returns:
        {"ok": True, "bounty_earned": True, ...} if bounty was triggered
        {"ok": True, "bounty_earned": False} if no bounty was due
        {"ok": False, "error": "..."} on failure
    """
    contractor_id = fee_event.get("contractor_id")
    fee_event_id = fee_event.get("id")

    if not contractor_id:
        return {"ok": True, "bounty_earned": False,
                "reason": "no contractor_id on fee_event"}

    # Get DB handle
    if db is None:
        if get_db is not None:
            db = get_db()
        if db is None:
            try:
                from supabase import create_client
                db = create_client(
                    os.environ.get("SUPABASE_URL", ""),
                    os.getenv("SUPABASE_SERVICE_KEY", ""),
                )
            except Exception as e:
                log.error(f"[bounty_tracker] db unavailable: {e}")
                return {"ok": False, "error": "db_unavailable"}

    try:
        # ── Step 1: Find pending referrals where this contractor was referred ──
        # Use the contractor_referral_view (has referrer_name from JOIN) rather
        # than the raw table, which doesn't have a referrer_name column.
        referrals = (
            db.table("contractor_referral_view")
            .select("id,referrer_contractor_id,referrer_phone,bounty_amount,referral_code,referrer_name")
            .eq("referred_contractor_id", contractor_id)
            .eq("bounty_status", "pending")
            .limit(5)
            .execute()
        )

        if not referrals.data:
            return {"ok": True, "bounty_earned": False,
                    "reason": "no pending referrals for this contractor"}

        # ── Step 2: Check if this is the contractor's FIRST fee_event ─────
        prior_res = (
            db.table("fee_events")
            .select("id")
            .eq("contractor_id", contractor_id)
            .neq("id", fee_event_id)
            .limit(1)
            .execute()
        )
        has_prior = bool(prior_res.data)

        if has_prior:
            return {"ok": True, "bounty_earned": False,
                    "reason": "contractor has prior fee_events (not first)"}

        # ── Step 3: This is their first — mark bounty as earned ──────────
        earned_records = []
        for ref in referrals.data:
            ref_id = ref["id"]
            referrer_id = ref.get("referrer_contractor_id")
            referrer_phone = ref.get("referrer_phone", "")
            bounty_amount = float(ref.get("bounty_amount", DEFAULT_BOUNTY_AMOUNT))
            ref_code = ref.get("referral_code", "")

            # Update contractor_referrals row
            db.table("contractor_referrals").update({
                "bounty_status": "earned",
                "bounty_paid_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", ref_id).execute()

            # Create referral_payouts record
            payout_payload = {
                "contractor_referral_id": ref_id,
                "referrer_contractor_id": referrer_id,
                "bounty_amount": bounty_amount,
                "status": "earned",
                "notes": BOUNTY_NOTE,
            }
            payout_res = db.table("referral_payouts").insert(payout_payload).execute()
            payout_id = payout_res.data[0]["id"] if payout_res.data else None

            # ── Step 4: Send ntfy notification ────────────────────────────
            referrer_name = ref.get("referrer_name") or ref.get("referrer_phone") or "a contractor"
            fee_amount = fee_event.get("fee_amount", 0)
            claim_amount = fee_event.get("claim_amount", 0)

            ntfy_title = f"💰 ${bounty_amount:,.0f} Bounty Earned!"
            ntfy_msg = (
                f"Contractor you referred ({referrer_phone}) just closed their "
                f"first settled claim (${float(claim_amount):,.2f}). "
                f"Your ${bounty_amount:,.0f} referral bounty has been marked as earned. "
                f"Fee earned: ${float(fee_amount):,.2f}. "
                f"Referral code: {ref_code or '—'}. "
                f"Reference: {ref_id[:8] if isinstance(ref_id, str) else ref_id}..."
            )

            # Fire-and-forget the ntfy push
            asyncio.create_task(_push_ntfy(ntfy_title, ntfy_msg))

            # Fire-and-forget SMS to referrer
            if referrer_phone:
                asyncio.create_task(_send_referrer_sms(
                    phone=referrer_phone,
                    referrer_name=referrer_name,
                    bounty_amount=bounty_amount,
                ))

            earned_records.append({
                "referral_id": ref_id,
                "referrer_contractor_id": referrer_id,
                "referrer_phone": referrer_phone,
                "referrer_name": referrer_name,
                "bounty_amount": bounty_amount,
                "payout_id": payout_id,
                "fee_event_id": fee_event_id,
            })

            # Log bounty earned in referral_log for audit trail
            try:
                db.table("referral_log").insert({
                    "event_type": "bounty_earned",
                    "referral_code": ref_code,
                    "referrer_contractor_id": referrer_id,
                    "referred_contractor_id": contractor_id,
                    "contractor_referral_id": ref_id,
                    "meta": {"bounty_amount": bounty_amount, "fee_event_id": fee_event_id, "payout_id": payout_id},
                }).execute()
            except Exception:
                pass

            log.info(
                f"[bounty_tracker] Bounty earned! referral={ref_id} "
                f"contractor={contractor_id} referrer={referrer_phone} "
                f"bounty=${bounty_amount:,.2f} fee_event={fee_event_id}"
            )

        return {
            "ok": True,
            "bounty_earned": True,
            "earned_records": earned_records,
        }

    except Exception as e:
        log.error(f"[bounty_tracker] check failed: {e}")
        return {"ok": False, "error": str(e)}


# ── SYNC WRAPPER (for calling from sync contexts) ─────────────────────


def check_bounty_eligible_sync(fee_event: dict, **kwargs) -> dict:
    """Synchronous wrapper for check_bounty_eligible. Creates a new event
    loop, runs the async check, returns the result."""
    try:
        return asyncio.run(check_bounty_eligible(fee_event, **kwargs))
    except RuntimeError:
        # If we're already in an event loop, create a new one
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                check_bounty_eligible(fee_event, **kwargs)
            )
        finally:
            loop.close()


# ── BACKGROUND CATCHUP LOOP ──────────────────────────────────────────
# Scans fee_events in the last N hours that may not have triggered
# a bounty check (e.g. if the bounty_tracker wasn't wired yet when
# the fee_event was created). Idempotent: will skip already-earned
# bounties because check_bounty_eligible checks bounty_status='pending'.


async def run_catchup(hours_back: int = 72, batch_size: int = 50):
    """
    Scan fee_events created in the last `hours_back` hours and run
    check_bounty_eligible on each one that has a contractor_id.

    Idempotent — already-earned bounties are skipped because the
    check queries bounty_status='pending'.
    """
    log.info(f"[bounty_tracker] Catchup scan: looking back {hours_back}h")
    try:
        from supabase import create_client
        db = create_client(
            os.environ.get("SUPABASE_URL", ""),
            os.getenv("SUPABASE_SERVICE_KEY", ""),
        )

        since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
        res = (
            db.table("fee_events")
            .select("id,contractor_id,claim_amount,fee_amount,claim_id,source")
            .not_.is_("contractor_id", "null")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(batch_size)
            .execute()
        )

        events = res.data or []
        log.info(f"[bounty_tracker] Catchup: found {len(events)} fee_events to check")

        earned_count = 0
        for ev in events:
            result = await check_bounty_eligible(ev, db=db)
            if result.get("bounty_earned"):
                earned_count += 1
                log.info(
                    f"[bounty_tracker] Catchup: bounty earned for fee_event "
                    f"{ev.get('id', '?')[:8]} contractor={ev.get('contractor_id', '?')[:8]}"
                )

        log.info(f"[bounty_tracker] Catchup complete: {earned_count} bounties earned")
        return {"checked": len(events), "earned": earned_count}

    except Exception as e:
        log.error(f"[bounty_tracker] Catchup error: {e}")
        return {"error": str(e)}


async def run_loop(interval_minutes: int = 15):
    """
    Background loop: run catchup scan every N minutes.
    Configure via BOUNTY_TRACKER_INTERVAL env var (default 15 min).
    """
    if interval_minutes is None:
        try:
            interval_minutes = int(os.environ.get("BOUNTY_TRACKER_INTERVAL", "15"))
        except (ValueError, TypeError):
            interval_minutes = 15

    log.info(f"[bounty_tracker] Background loop ONLINE · interval={interval_minutes}m")

    # Heartbeat to agent registry
    async def heartbeat():
        try:
            from supabase import create_client
            sb = create_client(
                os.environ.get("SUPABASE_URL", ""),
                os.getenv("SUPABASE_SERVICE_KEY", ""),
            )
            sb.table("agent_registry").upsert({
                "agent_name": "bounty_tracker",
                "role_name": "bounty_specialist",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "track_referral_bounties", "auto_earn_bounties",
                    "notify_referrers", "catchup_scan",
                ],
                "task_types": ["bounty.check", "bounty.catchup"],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    await heartbeat()

    while True:
        try:
            await run_catchup(hours_back=72)
            await heartbeat()
        except Exception as e:
            log.error(f"[bounty_tracker] Cycle error: {e}")

        await asyncio.sleep(interval_minutes * 60)


# ── FASTAPI ROUTES ───────────────────────────────────────────────────


def register_bounty_tracker_routes(app, *, require_auth: Callable):
    """Wire bounty tracker API routes on the hub."""

    from fastapi import Depends

    @app.get("/api/v1/bounty/stats")
    async def bounty_stats(auth: bool = Depends(require_auth)):
        """Return bounty program stats."""
        try:
            from supabase import create_client
            db = create_client(
                os.environ.get("SUPABASE_URL", ""),
                os.getenv("SUPABASE_SERVICE_KEY", ""),
            )
            total_pending = 0
            total_earned = 0
            total_paid = 0
            earning_sum = 0.0

            try:
                r = db.table("contractor_referrals").select("bounty_status,bounty_amount").limit(5000).execute()
                for row in (r.data or []):
                    s = row.get("bounty_status", "")
                    amt = float(row.get("bounty_amount", 0) or 0)
                    if s == "pending":
                        total_pending += 1
                    elif s == "earned":
                        total_earned += 1
                        earning_sum += amt
                    elif s == "paid":
                        total_paid += 1
                        earning_sum += amt
            except Exception:
                pass

            return {
                "ok": True,
                "pending_bounties": total_pending,
                "earned_bounties": total_earned,
                "paid_bounties": total_paid,
                "total_earned_usd": round(earning_sum, 2),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    @app.post("/api/v1/bounty/catchup")
    async def bounty_catchup(auth: bool = Depends(require_auth)):
        """Manually trigger a catchup scan."""
        result = await run_catchup(hours_back=168)
        return {"ok": True, "result": result}

    log.info("[bounty_tracker] Routes registered: GET /api/v1/bounty/stats, POST /api/v1/bounty/catchup")


# ── STANDALONE CLI ───────────────────────────────────────────────────


def run():
    """Sync entry point for PM2 / main.py agent loop compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    if "--catchup" in sys.argv:
        result = asyncio.run(run_catchup(hours_back=168))
        print(json.dumps(result, indent=2, default=str))
    elif "--stats" in sys.argv:
        import json as _json
        try:
            from supabase import create_client
            sb = create_client(
                os.environ.get("SUPABASE_URL", ""),
                os.getenv("SUPABASE_SERVICE_KEY", ""),
            )
            pr = sb.table("contractor_referrals").select("bounty_status").limit(5000).execute()
            rows = pr.data or []
            from collections import Counter
            counts = Counter(r.get("bounty_status", "?") for r in rows)
            print(_json.dumps(dict(counts), indent=2))
        except Exception as e:
            print(f"Error: {e}")
        sys.exit(0)
    else:
        asyncio.run(run_loop())
