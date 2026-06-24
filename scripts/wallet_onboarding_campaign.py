"""
Empire AI · Wallet Onboarding SMS Campaign
============================================
One-shot SMS campaign: asks contractors to reply with their Solana wallet
address. The wallet is automatically saved to their profile when they
reply — the handle_inbound() method in empire_sms.py detects Solana
wallet patterns via regex and saves them.

Prerequisite: the wallet detection in empire_sms.py's handle_inbound()
must be deployed (the SOLANA_WALLET_RE regex check + contractor save
logic). Deploy via: pm2 restart empire-hub

Run:
  python3 scripts/wallet_onboarding_campaign.py              # live send
  python3 scripts/wallet_onboarding_campaign.py --dry-run    # preview
  python3 scripts/wallet_onboarding_campaign.py --limit 10   # first 10
"""

import os
import re
import sys
import json
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

log = logging.getLogger("wallet_onboarding")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VONAGE_API_KEY = os.environ.get("VONAGE_API_KEY", "")
VONAGE_API_SECRET = os.environ.get("VONAGE_API_SECRET", "")
VONAGE_NUMBER = os.environ.get("VONAGE_NUMBER", "")

CAMPAIGN_NAME = "wallet_onboarding_2026-06-23"
PRICING_URL = "https://empire-ai.co.uk/for-contractors"

# Solana wallet regex (mirrors the one in empire_sms.py)
SOLANA_WALLET_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _first_name(name: str) -> str:
    if not name:
        return "there"
    return name.split()[0].strip().title()


def _normalize_phone(phone: str) -> str:
    """Normalize to E.164 +1XXXXXXXXXX format."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if phone and phone.startswith("+"):
        return f"+{digits}"
    return ""


def _send_sms(to: str, body: str) -> dict:
    """Send SMS via Vonage. Returns {ok, message_uuid} or {ok, error}."""
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
            r = c.post("https://rest.nexmo.com/sms/json", json=payload)
            data = r.json()
            ok = r.status_code < 400 and data.get("messages", [{}])[0].get("status") == "0"
            msg_uuid = data.get("messages", [{}])[0].get("message-id") if ok else None
            return {"ok": ok, "message_uuid": msg_uuid, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _already_sent(sb, contractor_id: str) -> bool:
    """Check if this contractor already received this campaign."""
    try:
        r = sb.table("contractor_outreach").select("id") \
            .eq("contractor_id", contractor_id) \
            .eq("sequence", CAMPAIGN_NAME) \
            .limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


def _log_send(sb, contractor_id: str, status: str, detail: str = "") -> None:
    """Log the campaign send to contractor_outreach table."""
    try:
        sb.table("contractor_outreach").insert({
            "contractor_id": contractor_id,
            "sequence": CAMPAIGN_NAME,
            "step": 1,
            "status": status,
            "notes": f"wallet_onboarding_sms: {detail[:280]}",
            "last_sent_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning(f"log insert failed for {contractor_id}: {e}")


def build_sms_body(first: str) -> str:
    """Build the SMS (≤160 chars) asking the contractor to reply with their wallet."""
    return (
        f"Empire AI: Hi {first}, reply with your Solana wallet address and we'll "
        f"save it. Then visit {PRICING_URL} to activate. Reply STOP to opt out."
    )


def run(dry_run: bool = False, limit: int = 0) -> dict:
    """Main campaign run."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    started = datetime.now(timezone.utc)

    # 1) Fetch active contractors with phone + email, no wallet yet
    r = sb.table("contractors").select("id,name,phone,email,metro") \
        .eq("active", True) \
        .not_.is_("phone", "null") \
        .not_.is_("email", "null") \
        .is_("solana_wallet", "null") \
        .limit(7000).execute()
    candidates = r.data or []
    log.info(f"Found {len(candidates)} contractors with phone + no wallet")

    if limit and limit < len(candidates):
        candidates = candidates[:limit]
        log.info(f"Limited to {limit}")

    sent = 0
    skipped = 0
    errors = 0
    already = 0

    for c in candidates:
        cid = c["id"]
        first = _first_name(c.get("name", ""))
        phone_raw = c.get("phone", "")
        phone = _normalize_phone(phone_raw)

        if not phone:
            skipped += 1
            continue

        # Skip if already got this campaign
        if _already_sent(sb, cid):
            already += 1
            continue

        if dry_run:
            log.info(f"[DRY-RUN] Would SMS {phone} ({first})")
            sent += 1
            continue

        # Send SMS
        body = build_sms_body(first)
        s_res = _send_sms(phone, body)

        if s_res.get("ok"):
            sent += 1
            _log_send(sb, cid, "sent", f"sms_sent: {s_res.get('message_uuid','')}")
            log.info(f"[SMS] ✓ {phone} ({first})")
        else:
            errors += 1
            _log_send(sb, cid, "failed", f"sms_error: {s_res.get('error','')}")
            log.warning(f"[SMS] ✗ {phone}: {s_res.get('error','unknown')}")

        # Rate limit: 6 SMS/min per Vonage long code
        import time as _time
        _time.sleep(10)

    # Log to agent_activity
    summary = (
        f"campaign={CAMPAIGN_NAME} "
        f"candidates={len(candidates)} "
        f"sms_sent={sent} "
        f"already_sent={already} "
        f"skipped={skipped} "
        f"errors={errors} "
        f"dry_run={'yes' if dry_run else 'no'}"
    )
    try:
        sb.table("agent_activity").insert({
            "agent_name": CAMPAIGN_NAME,
            "run_id": str(uuid.uuid4()),
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok" if errors == 0 else "warn",
            "rows_seen": len(candidates),
            "rows_processed": sent,
            "rows_errored": errors,
            "summary": summary,
        }).execute()
    except Exception as e:
        log.warning(f"agent_activity insert failed: {e}")

    result = {
        "campaign": CAMPAIGN_NAME,
        "candidates": len(candidates),
        "sms_sent": sent,
        "already_sent": already,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
    }
    log.info(f"Done: {summary}")
    return result


def main():
    p = argparse.ArgumentParser(description="Wallet Onboarding SMS Campaign")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no sends")
    p.add_argument("--limit", type=int, default=0, help="Max contractors to process (0 = all)")
    args = p.parse_args()

    import time as _t
    import random as _r
    campaign_id = f"{CAMPAIGN_NAME}_{int(_t.time())}_{_r.randint(100, 999)}"

    if args.dry_run:
        log.info("=== DRY RUN MODE ===")

    result = run(dry_run=args.dry_run, limit=args.limit)

    print(f"\n{'Dry run' if args.dry_run else 'Live send'} summary:")
    print(f"  Campaign:     {CAMPAIGN_NAME}")
    print(f"  Candidates:   {result['candidates']}")
    print(f"  SMS sent:     {result['sms_sent']}")
    print(f"  Already sent: {result['already_sent']}")
    print(f"  Skipped:      {result['skipped']}")
    print(f"  Errors:       {result['errors']}")

    if not args.dry_run and result['sms_sent'] > 0:
        print()
        print("Next: contractors will reply with their SOL addresses.")
        print("The SMS handler (empire_sms.py handle_inbound) auto-detects")
        print("wallet patterns and saves them to their profile.")
        print("Then they can visit /for-contractors to activate a subscription.")

    sys.exit(0 if result["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
