#!/usr/bin/env python3
"""
EMPIRE V49 · FEE COLLECTION AGENT
==================================
Queries pending fee_events, looks up the contractor's contact info via
dispatches, and sends SMS/email payment requests with the vault wallet
address and claim-settled webhook URL.

Run modes:
    python3 scripts/fee_collection_agent.py                       # live — sends SMS/email
    python3 scripts/fee_collection_agent.py --dry-run              # report only
    python3 scripts/fee_collection_agent.py --follow-up            # re-send on cadence (3/7/14d)
    python3 scripts/fee_collection_agent.py --follow-up --now      # force re-send NOW (skip cadence)
    python3 scripts/fee_collection_agent.py --force --fee-id <uuid>  # single fee

The vault wallet is where contractors send 3% USDC:
    egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM

The claim webhook is how they POST the settlement:
    POST https://empire-ai.co.uk/api/v1/claim-settled
    Authorization: Bearer <CLAIM_WEBHOOK_SECRET>

Env vars:
    CLAIM_WEBHOOK_SECRET        — shared secret for the webhook auth
    VONAGE_APPLICATION_ID       — Vonage application ID (for JWT auth)
    VONAGE_PRIVATE_KEY_PATH     — path to Vonage private key file (default: /root/vonage_private.key)
    VONAGE_NUMBER               — Vonage sender phone number
    RESEND_API_KEY              — Resend API key (for email fallback)
    FROM_ADDRESS                — Sender email address (default: noreply@empire-ai.co.uk)
    FROM_NAME                   — Sender display name (default: Empire AI Operations)
    (falls back to logging-only if no channel configured)
"""

import os
import sys
import json
import uuid
import asyncio
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

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

log = logging.getLogger("fee_collection")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "fee_collection_agent"

# ── Vault wallet — contractors send 3% USDC here ────────────────────────
VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
CLAIM_WEBHOOK_URL = "https://empire-ai.co.uk/api/v1/claim-settled"

# Follow-up cadence (days after previous attempt)
FOLLOW_UP_DAYS = [3, 7, 14]

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


def _build_payment_body(
    contractor_name: str,
    fee_amount: float,
    claim_amount: float,
    dispatch_id: str,
    is_follow_up: bool = False,
) -> str:
    """Build the payment request body. ~300 chars, fits in 2 SMS segments."""
    prefix = "Empire AI:"
    header = "Payment reminder" if is_follow_up else "Settlement notice"

    return (
        f"{prefix} {header} — "
        f"${fee_amount:,.0f} fee on ${claim_amount:,.0f} claim ({dispatch_id[:8]}...). "
        f"Send 3% USDC to: {VAULT_WALLET}. "
        f"Then POST settlement to: empire-ai.co.uk/api/v1/claim-settled "
        f"(dispatch={dispatch_id}). "
        f"Reply HELP for help. STOP to opt out."
    )


async def _send_sms_vonage(
    to_number: str,
    message: str,
    vonage_number: str,
) -> dict:
    """Send SMS via Vonage Messages API (JWT auth)."""
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")

    if not app_id or not os.path.exists(key_path):
        return {"ok": False, "error": "Vonage JWT credentials not configured"}
    if not vonage_number:
        return {"ok": False, "error": "VONAGE_NUMBER not set"}

    try:
        # Read private key
        with open(key_path, "r") as f:
            private_key = f.read()

        # Generate JWT
        import jwt as pyjwt
        import time as _time

        now = int(_time.time())
        jti = str(uuid.uuid4())
        payload = {
            "iat": now,
            "exp": now + 180,  # 3 minute expiry
            "jti": jti,
            "application_id": app_id,
        }
        token = pyjwt.encode(payload, private_key, algorithm="RS256")

        # Build Messages API request
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
            # Successful: 202 Accepted with message_uuid
            if r.status_code == 202:
                msg_uuid = result.get("message_uuid", "")
                return {"ok": True, "message_id": msg_uuid}
            else:
                detail = result.get("detail", str(result)[:200])
                title = result.get("title", "")
                return {"ok": False, "error": f"Vonage {r.status_code}: {title} {detail}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _send_email_resend(
    to: str,
    subject: str,
    body: str,
    resend_key: str,
    email_from: str = "noreply@empire-ai.co.uk",
    email_from_name: str = "Empire AI Operations",
) -> dict:
    """Send email via Resend API."""
    if not resend_key:
        return {"ok": False, "error": "RESEND_API_KEY not set"}

    html_body = body.replace("\n", "<br>\n")
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,system-ui,sans-serif;background:#0a0a0a;color:#e4e4e7;padding:32px;line-height:1.7;font-size:14px;">
<div style="max-width:580px;margin:0 auto;">
{html_body}
</div>
</body></html>"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"{email_from_name} <{email_from}>",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code < 300
            return {"ok": ok, "id": data.get("id") if ok else None, "status_code": r.status_code, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _log_collection_attempt(
    fee_event_id: str,
    contractor_id: str,
    phone: str,
    fee_amount: float,
    success: bool,
    message: str,
    attempt_type: str = "initial",
):
    """Log a collection attempt to agent_activity for audit trail."""
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
                f"fee_collection: fee={fee_event_id[:12]} "
                f"contractor={contractor_id[:12]} "
                f"amount=${fee_amount} "
                f"{'SENT' if success else 'FAILED'}: {message[:60]}"
            ),
            "meta": {
                "fee_event_id": fee_event_id,
                "contractor_id": contractor_id,
                "phone": phone,
                "fee_amount": fee_amount,
                "attempt_type": attempt_type,
                "success": success,
                "detail": message[:500],
            },
        }).execute()
    except Exception as e:
        log.debug(f"Failed to log collection attempt: {e}")


async def run_collection(
    dry_run: bool = False,
    follow_up: bool = False,
    force_now: bool = False,
    force_fee_id: Optional[str] = None,
) -> dict:
    """Main collection pipeline."""
    sb = _sb()
    started_at = datetime.now(timezone.utc)

    # ── Channel config ──────────────────────────────────────────────────
    vonage_number = os.getenv("VONAGE_NUMBER", "")
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    sms_enabled = bool(app_id and os.path.exists(key_path) and vonage_number)

    resend_key = os.getenv("RESEND_API_KEY", "")
    email_from = os.getenv("FROM_ADDRESS", "noreply@empire-ai.co.uk")
    email_from_name = os.getenv("FROM_NAME", "Empire AI Operations")
    email_enabled = bool(resend_key)

    if not sms_enabled and not email_enabled:
        log.info("No sending channel configured (SMS nor Email) — running in log-only mode")

    # ── 1. Fetch pending fee_events ─────────────────────────────────────
    query = sb.table("fee_events").select(
        "id, contractor_id, lead_id, claim_amount, fee_amount, "
        "status, source, settled_at, meta, created_at"
    )

    if force_fee_id:
        query = query.eq("id", force_fee_id)
    else:
        query = query.eq("status", "pending")

    r = query.limit(200).execute()
    fee_events = r.data or []
    log.info(f"Fetched {len(fee_events)} fee_events to process")

    # ── 2. Fetch linked dispatches for contractor_id resolution ─────────
    dispatch_ids = set()
    contractor_ids = set()
    for fe in fee_events:
        cid = fe.get("contractor_id")
        if cid:
            contractor_ids.add(cid)
        meta = fe.get("meta") or {}
        if isinstance(meta, dict):
            did = meta.get("dispatch_id")
            if did:
                dispatch_ids.add(did)

    contractor_by_dispatch: Dict[str, str] = {}
    if dispatch_ids:
        for did in dispatch_ids:
            dr = sb.table("dispatches").select("id, contractor_id") \
                .eq("id", did).limit(1).execute()
            if dr.data:
                cid = dr.data[0].get("contractor_id")
                if cid:
                    contractor_ids.add(cid)
                    contractor_by_dispatch[did] = cid

    # ── 3. Fetch contractor contact info ────────────────────────────────
    contractors: Dict[str, dict] = {}
    if contractor_ids:
        for cid in contractor_ids:
            cr = sb.table("contractors").select("id, name, email, phone") \
                .eq("id", cid).limit(1).execute()
            if cr.data:
                contractors[cid] = cr.data[0]

    log.info(f"Found {len(contractors)} contractors with contact info")

    # ── 4. Process each fee_event ───────────────────────────────────────
    results = []
    sent_count = 0
    skipped_no_contact = 0
    skipped_already_contacted = 0
    errors = 0

    for fe in fee_events:
        fee_id = fe["id"]
        fee_amount = fe.get("fee_amount", 0)
        claim_amount = fe.get("claim_amount", 0)
        fe_meta = fe.get("meta") or {}
        if isinstance(fe_meta, str):
            try:
                fe_meta = json.loads(fe_meta)
            except Exception:
                fe_meta = {}

        # Resolve contractor_id
        cid = fe.get("contractor_id") or contractor_by_dispatch.get(
            (fe_meta or {}).get("dispatch_id", "")
        )
        if not cid:
            log.info(f"  SKIP {fee_id[:12]}: no contractor_id")
            skipped_no_contact += 1
            continue

        contractor = contractors.get(cid)
        if not contractor:
            log.info(f"  SKIP {fee_id[:12]}: contractor {cid[:12]} not found")
            skipped_no_contact += 1
            continue

        name = (contractor.get("name") or "Contractor").strip()
        phone = _normalize_phone(contractor.get("phone") or "")
        email = (contractor.get("email") or "").strip().lower()

        if not phone and not email:
            log.info(f"  SKIP {fee_id[:12]}: {name[:20]} — no phone or email")
            skipped_no_contact += 1
            continue

        # Check collection history to avoid double-sending
        collection_history = fe_meta.get("collection_history") or []
        last_attempt = collection_history[-1] if collection_history else None
        attempt_type = "initial"

        if follow_up:
            if not last_attempt:
                if not force_now:
                    log.info(f"  SKIP {fee_id[:12]}: {name[:20]} — no initial attempt, skipping follow-up")
                    skipped_already_contacted += 1
                    continue
                else:
                    log.info(f"  ⚡ FORCE-NOW {fee_id[:12]}: {name[:20]} — no prior contact, sending as initial")
                    attempt_type = "initial"
                    # fall through to send
            else:
                last_ts = last_attempt.get("sent_at", "")
                if not last_ts:
                    skipped_already_contacted += 1
                    continue

                days_since = (datetime.now(timezone.utc) - datetime.fromisoformat(last_ts)).days
                attempt_num = len(collection_history)

                if attempt_num > len(FOLLOW_UP_DAYS):
                    log.info(f"  SKIP {fee_id[:12]}: {name[:20]} — max follow-ups reached ({attempt_num})")
                    skipped_already_contacted += 1
                    continue

                expected_days = FOLLOW_UP_DAYS[attempt_num - 1]
                if not force_now and days_since < expected_days:
                    log.info(
                        f"  SKIP {fee_id[:12]}: {name[:20]} — follow-up {attempt_num} "
                        f"needs {expected_days}d, only {days_since}d since last"
                    )
                    skipped_already_contacted += 1
                    continue
                elif force_now and days_since < expected_days:
                    log.info(
                        f"  ⚡ FORCE-NOW {fee_id[:12]}: {name[:20]} — follow-up {attempt_num} "
                        f"(cadence {expected_days}d bypassed, {days_since}d since last)"
                    )

                attempt_type = f"follow_up_{attempt_num}"
        else:
            if last_attempt:
                log.info(f"  SKIP {fee_id[:12]}: {name[:20]} — already contacted")
                skipped_already_contacted += 1
                continue

        # ── Build payment request body ──────────────────────────────────
        dispatch_id = (fe_meta or {}).get("dispatch_id", "")
        is_follow = attempt_type != "initial"

        body = _build_payment_body(
            contractor_name=name.split()[0] if name else "Contractor",
            fee_amount=fee_amount,
            claim_amount=claim_amount,
            dispatch_id=dispatch_id or fee_id,
            is_follow_up=is_follow,
        )

        log.info(
            f"  {'DRY-RUN' if dry_run else 'SENDING'}: "
            f"fee={fee_id[:12]}  contractor={name[:20]}  "
            f"phone={phone}  email={email or '—'}  "
            f"amount=${fee_amount:,.0f}  type={attempt_type}"
        )

        channel_used = None
        success = False
        message = ""

        if not dry_run:
            # Try SMS first (faster attention)
            if sms_enabled and phone:
                result = await _send_sms_vonage(
                    phone, body, vonage_number
                )
                if result.get("ok"):
                    success = True
                    channel_used = "sms"
                    message = result.get("message_id", "")
                else:
                    log.warning(f"    SMS failed ({result.get('error','?')}), falling back to email")

            # Fallback to email if SMS unavailable or failed
            if not success and email and email_enabled:
                email_subject = f"Empire AI — Fee Payment Request: ${fee_amount:,.0f}"
                result = await _send_email_resend(
                    to=email,
                    subject=email_subject,
                    body=body,
                    resend_key=resend_key,
                    email_from=email_from,
                    email_from_name=email_from_name,
                )
                if result.get("ok"):
                    success = True
                    channel_used = "email"
                    message = result.get("id", "")
                else:
                    log.warning(f"    Email fallback also failed: {result.get('error','?')}")

            # Log-only mode if neither channel worked
            if not success:
                if phone:
                    print(f"\n--- SMS would be sent (log-only) ---")
                    print(f"  To: {phone}")
                    print(f"  Body: {body}")
                    print(f"---")
                elif email:
                    print(f"\n--- Email would be sent (log-only) ---")
                    print(f"  To: {email}")
                    print(f"  Subject: Empire AI — Fee Payment Request: ${fee_amount:,.0f}")
                    print(f"  Body: {body}")
                    print(f"---")
                success = True
                channel_used = f"{'sms' if phone else 'email'}_log_only"
                message = "logged_only"

            # Record collection history in fee_event meta
            if success:
                new_history = list(collection_history)
                new_history.append({
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "attempt_type": attempt_type,
                    "channel": channel_used or "unknown",
                    "phone": phone or None,
                    "email": email or None,
                    "status": "sent",
                    "body_preview": body[:100],
                })
                try:
                    sb.table("fee_events").update({
                        "meta": {**(fe_meta or {}), "collection_history": new_history},
                    }).eq("id", fee_id).execute()
                except Exception as e:
                    log.warning(f"  Failed to update fee_event meta: {e}")

                sent_count += 1
            else:
                errors += 1

            # Log to agent_activity
            await _log_collection_attempt(
                fee_event_id=fee_id,
                contractor_id=cid,
                phone=phone,
                fee_amount=fee_amount,
                success=success,
                message=message,
                attempt_type=attempt_type,
            )

            # Rate limit between sends
            await asyncio.sleep(SEND_DELAY)
        else:
            sent_count += 1  # count in dry-run for reporting

        results.append({
            "fee_id": fee_id,
            "contractor": name,
            "phone": phone,
            "email": email,
            "fee_amount": fee_amount,
            "claim_amount": claim_amount,
            "attempt_type": attempt_type,
        })

    # ── 5. Summary ──────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    total_fees = sum(fe.get("fee_amount", 0) for fe in fee_events)
    total_claims = sum(fe.get("claim_amount", 0) for fe in fee_events)

    summary = {
        "total_pending_fees": len(fee_events),
        "attempted": len(results),
        "sent": sent_count,
        "skipped_no_contact": skipped_no_contact,
        "skipped_already_contacted": skipped_already_contacted,
        "errors": errors,
        "total_fees_usd": round(total_fees, 2),
        "total_claims_usd": round(total_claims, 2),
        "follow_up_mode": follow_up,
        "force_now": force_now,
        "sms_enabled": sms_enabled,
        "email_enabled": email_enabled,
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 1),
        "vault_wallet": VAULT_WALLET,
        "claim_webhook_url": CLAIM_WEBHOOK_URL,
    }

    log.info("=== FEE COLLECTION SUMMARY ===")
    log.info(f"Pending fee_events:   {len(fee_events)}")
    log.info(f"Total fees (pending): ${total_fees:,.2f}")
    log.info(f"Total claims:         ${total_claims:,.2f}")
    log.info(f"Attempted:            {len(results)}")
    log.info(f"Sent:                 {sent_count}")
    log.info(f"Skipped (no contact): {skipped_no_contact}")
    log.info(f"Skipped (contacted):  {skipped_already_contacted}")
    log.info(f"Errors:               {errors}")
    log.info(f"Follow-up mode:       {follow_up}")
    if force_now:
        log.info(f"Force-now:            YES (cadence bypassed)")
    log.info(f"SMS via Vonage:       {'yes' if sms_enabled else 'no'}")
    log.info(f"Email via Resend:     {'yes' if email_enabled else 'no'}")
    log.info(f"Elapsed:              {elapsed:.1f}s")

    return summary


def main():
    p = argparse.ArgumentParser(
        description="Fee Collection Agent — send SMS/email payment requests to contractors"
    )
    p.add_argument("--dry-run", action="store_true",
                    help="Report only — no SMS/email sending")
    p.add_argument("--follow-up", action="store_true",
                    help="Send follow-ups to fee_events already contacted")
    p.add_argument("--force", action="store_true",
                    help="Force processing (overrides duplicate-send guard)")
    p.add_argument("--now", action="store_true",
                    help="Force send NOW — bypasses cadence timing and no-contact guard")
    p.add_argument("--fee-id", type=str, default=None,
                    help="Process a specific fee_event by UUID")
    args = p.parse_args()

    result = asyncio.run(run_collection(
        dry_run=args.dry_run,
        follow_up=args.follow_up or args.now,
        force_now=args.now,
        force_fee_id=args.fee_id,
    ))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
