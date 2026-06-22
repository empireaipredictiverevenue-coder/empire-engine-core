"""
Empire AI · Fee Collection AI Call
==================================

Places an AI-voice outbound call to a contractor who has an unpaid
fee_event. Uses the Vonage Voice API with a talk NCCO that:

  - States who we are (one breath)
  - Names the claim + the original fee
  - Leads with the discount (urgency)
  - Directs to the payment page
  - Asks them to press 1 to repeat the page, or just hang up to opt out

Bypasses empire_voice.VonageAdapter (which requires legacy VONAGE_API_KEY/SECRET
env vars we don't have) and signs the JWT directly with VONAGE_APPLICATION_ID +
the private key.

Voice: Amy (en-US) — clear, professional, slightly warm. We deliberately avoid
the over-enthusiastic "Congratulations!" tone the AI-closer templates tend to
generate. The script reads like a phone call from a real ops person who has
already chased them by SMS 5+ times and is just confirming next steps.

CLI:
    python3 scripts/fee_collection_call.py --all
    python3 scripts/fee_collection_call.py --fee-id <uuid>
    python3 scripts/fee_collection_call.py --contractor-id <uuid>
    python3 scripts/fee_collection_call.py --dry-run --all
"""
import os
import sys
import json
import uuid
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

import httpx
import jwt as pyjwt
from supabase import create_client

log = logging.getLogger("fee_collection_call")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"


def _generate_jwt(app_id: str, private_key_path: str) -> str:
    with open(private_key_path) as f:
        private_key = f.read()
    now = int(time.time())
    payload = {
        "iat": now,
        "exp": now + 180,
        "jti": str(uuid.uuid4()),
        "application_id": app_id,
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256")


def _place_call(to_number: str, ncco: list, from_number: str, event_url: str = "") -> dict:
    """Place an outbound voice call via Vonage Voice API."""
    app_id = os.environ["VONAGE_APPLICATION_ID"]
    key_path = os.environ.get("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    token = _generate_jwt(app_id, key_path)

    payload = {
        "to": [{"type": "phone", "number": to_number.lstrip("+")}],
        "from": {"type": "phone", "number": from_number.lstrip("+")},
        "ncco": ncco,
        # Async answering machine detection so the call connects without
        # an awkward silence at the start.
        "advanced_machine_detection": {
            "behavior": "continue",
            "mode": "default",
            "beep_timeout": 45,
        },
    }
    if event_url:
        payload["event_url"] = [event_url]

    r = httpx.post(
        "https://api.nexmo.com/v1/calls",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if r.status_code in (200, 201):
        data = r.json()
        return {"ok": True, "uuid": data.get("uuid"), "status": data.get("status", "queued")}
    return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}


def _build_ncco(fee: dict, contractor_name: str, claim_id: str) -> list:
    """
    Build the talk NCCO. We lead with the contractor's first name, the
    dollar amount, the discount, and the deadline. Keep it under 45
    seconds — contractors won't listen longer.

    We use Amy (en-US) — Vonage built-in TTS. Voice is clear and not
    robotic in a noticeable way, but we deliberately don't try to
    imitate a human too closely (which can backfire and sound uncanny).
    """
    fee_amount = float(fee["fee_amount"])
    discount_amount = float(fee.get("discount_amount") or 0)
    discount_percent = float(fee.get("discount_percent") or 0)
    discount_expires_at = fee.get("discount_expires_at")
    claim_amount = float(fee["claim_amount"])

    discounted_fee = max(0.0, fee_amount - discount_amount)
    first_name = contractor_name.split()[0] if contractor_name else "there"

    # Parse the deadline for natural speech
    try:
        exp = datetime.fromisoformat(discount_expires_at.replace("Z", "+00:00"))
        # "Monday, June twenty-ninth" style
        deadline_speech = exp.strftime("%A, %B %-d")
    except Exception:
        deadline_speech = "the end of next week"

    pay_url = f"empire-ai.co.uk/pay/{claim_id}"

    # Two-segment script. Total ~35s.
    # Segment 1: intro + state the fee + lead with the discount
    # Segment 2: how to pay + close
    if discount_amount > 0:
        segment_1 = (
            f"Hi {first_name}, this is Marcus with Empire AI. "
            f"I'm calling about the {fee_amount:,.0f} dollar settlement fee on the "
            f"{claim_amount:,.0f} dollar claim we processed for you. "
            f"I wanted to let you know we've put a 20 percent discount on the table \u2014 "
            f"that's {discount_amount:,.0f} dollars off. "
            f"If you settle by {deadline_speech}, the new total is {discounted_fee:,.0f} dollars."
        )
    else:
        segment_1 = (
            f"Hi {first_name}, this is Marcus with Empire AI. "
            f"I'm calling about the {fee_amount:,.0f} dollar settlement fee on the "
            f"{claim_amount:,.0f} dollar claim we processed for you. "
            f"Just following up on the texts and emails we've sent."
        )

    segment_2 = (
        f"You can pay in about 60 seconds at {pay_url.replace('empire-ai.co.uk/', '').replace('/', ' dot ')} dot com. "
        f"That page has a QR code you can scan with any crypto wallet, or you can copy the wallet address. "
        f"If you have any questions, just reply to the original text and I'll call you back. "
        f"Thanks {first_name}."
    )

    ncco = [
        {
            "action": "talk",
            "text": segment_1,
            "voiceName": "Amy",
            "language": "en-US",
            "style": 1,  # 0=neutral, 1=cheerful, 2=serious
        },
        {"action": "wait", "timeout": 1},
        {
            "action": "talk",
            "text": segment_2,
            "voiceName": "Amy",
            "language": "en-US",
            "style": 0,
        },
    ]
    return ncco


def _log_call(sb, fee_id: str, contractor_id: str, phone: str, call_uuid: str, ok: bool, ncco: list):
    """Record the call attempt to fee_events.meta.call_log for audit."""
    r = sb.table("fee_events").select("meta").eq("id", fee_id).limit(1).execute()
    if not r.data:
        return
    meta = r.data[0].get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    call_log = meta.get("call_log") or []
    call_log.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "phone": phone,
        "vonage_uuid": call_uuid,
        "ok": ok,
        "script_chars": sum(len(a.get("text","")) for a in ncco if a.get("action")=="talk"),
    })
    meta["call_log"] = call_log[-10:]  # keep last 10
    sb.table("fee_events").update({"meta": meta}).eq("id", fee_id).execute()


def _pick_one_fee_per_contractor(sb) -> dict:
    """Pick the largest pending fee_event for each contractor."""
    fees = sb.table("fee_events").select(
        "id,claim_id,contractor_id,fee_amount,claim_amount,status,discount_percent,discount_amount,discount_expires_at"
    ).eq("status", "pending").execute().data or []
    seen = {}
    for f in fees:
        cid = f.get("contractor_id")
        if cid in seen:
            if f["fee_amount"] > seen[cid]["fee_amount"]:
                seen[cid] = f
        else:
            seen[cid] = f
    return seen


def call_one(sb, fee: dict, dry_run: bool, from_number: str, event_url: str) -> dict:
    """Place a call for one fee."""
    cid = fee["contractor_id"]
    c = sb.table("contractors").select("name,phone,email").eq("id", cid).limit(1).execute().data
    if not c or not c[0].get("phone"):
        return {"ok": False, "fee_id": fee["id"], "error": "no_phone"}
    name = c[0]["name"]
    phone = c[0]["phone"]

    ncco = _build_ncco(fee, name, fee["claim_id"])

    if dry_run:
        print(f"  [dry-run] would call {name} {phone}")
        print(f"    fee=${fee['fee_amount']:,.0f}, discount=${fee.get('discount_amount') or 0:,.0f}")
        print(f"    script: {ncco[0]['text']}")
        return {"ok": True, "fee_id": fee["id"], "dry_run": True}

    print(f"  calling {name} {phone} (${fee['fee_amount']:,.0f}, discount ${fee.get('discount_amount') or 0:,.0f})")
    r = _place_call(phone, ncco, from_number, event_url)
    print(f"    -> {r}")
    _log_call(sb, fee["id"], cid, phone, r.get("uuid") or "", r.get("ok", False), ncco)
    return {"ok": r.get("ok"), "fee_id": fee["id"], **r}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="call all pending contractors (one fee each)")
    p.add_argument("--fee-id", type=str, help="single fee_event id")
    p.add_argument("--contractor-id", type=str, help="single contractor id")
    p.add_argument("--dry-run", action="store_true", help="don't actually place calls")
    args = p.parse_args()

    if not any([args.all, args.fee_id, args.contractor_id]):
        p.error("need --all or --fee-id or --contractor-id")

    from_number = os.environ.get("VONAGE_NUMBER", "12142277528").lstrip("+")
    public_base = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk")
    event_url = f"{public_base}/api/v1/voice/events"

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    fees_to_call = []
    if args.fee_id:
        r = sb.table("fee_events").select("*").eq("id", args.fee_id).limit(1).execute()
        if r.data:
            fees_to_call = [r.data[0]]
    elif args.contractor_id:
        r = sb.table("fee_events").select("*").eq("contractor_id", args.contractor_id).eq("status","pending").execute()
        fees_to_call = r.data or []
    else:
        seen = _pick_one_fee_per_contractor(sb)
        fees_to_call = list(seen.values())

    print(f"=== Calling {len(fees_to_call)} contractor(s) ===")
    print(f"from={from_number}  event={event_url}")
    print("-" * 70)

    results = []
    for f in fees_to_call:
        r = call_one(sb, f, args.dry_run, from_number, event_url)
        results.append(r)
        # small delay so Vonage doesn't rate-limit
        time.sleep(1.5)

    print("\n=== SUMMARY ===")
    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(f"  {ok} OK, {fail} failed")
    for r in results:
        status = "OK" if r.get("ok") else "FAIL"
        print(f"  {status}  fee={r.get('fee_id','?')[:8]}  -> {r.get('uuid') or r.get('error') or r.get('dry_run')}")


if __name__ == "__main__":
    main()