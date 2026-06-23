"""
Empire AI · Vault Watcher
=========================

Polls the Helius RPC for incoming USDC transfers to the Empire AI
vault wallet. When a transfer matches a pending fee_event amount,
the fee is auto-marked as paid and the contractor gets a thank-you
SMS (and operator Telegram ping).

This is the missing link — without it, the first contractor to
pay has their tx on-chain but the fee_events row stays "pending"
until a human notices. With this loop, payment = automatic.

Match strategy:
  - Pull last 7 days of USDC transfers to the vault (Helius enhanced)
  - For each pending fee_event with discount, check if any tx amount
    matches the discounted_fee (in USDC smallest units, 6 decimals)
  - On match: mark paid + send thank-you SMS + log to fee_events.meta

Run modes:
  python3 scripts/vault_watcher.py               # one poll, exits
  python3 scripts/vault_watcher.py --loop        # poll every 5min forever
  python3 scripts/vault_watcher.py --since 24h   # look back 24h (default 7d)

Env:
  HELIUS_API_KEY              — RPC key (already in /root/.env)
  VAULT_WALLET                — receiver (already in scripts/vault_monitor.py)
  TELEGRAM_BOT_TOKEN          — optional, for operator ping on payment
  TELEGRAM_CHAT_ID            — optional, for operator ping on payment
  VONAGE_APPLICATION_ID       — for thank-you SMS via Vonage
"""
import os
import sys
import json
import time
import uuid
import argparse
import logging
import urllib.request
import urllib.parse
import re
from pathlib import Path
from datetime import datetime, timezone

REPO = Path("/root/empire-v49")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

from supabase import create_client

log = logging.getLogger("vault_watcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VAULT_WALLET = os.environ.get("VAULT_WALLET", "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM")
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6
HELIUS_KEY = os.environ.get("HELIUS_API_KEY", "")


def _fetch_recent_usdc_transfers(vault: str, since_unix: int) -> list:
    """Use Helius enhanced transactions API to pull recent USDC transfers."""
    if not HELIUS_KEY:
        log.warning("[watcher] HELIUS_API_KEY missing — falling back to RPC stub")
        return []
    url = f"https://api.helius.xyz/v0/addresses/{vault}/transactions"
    params = {
        "api-key": HELIUS_KEY,
        "limit": 100,
        "type": "TRANSFER",
    }
    req = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "Empire-AI-VaultWatcher/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txs = json.loads(r.read())
    except Exception as e:
        log.warning(f"[watcher] helius fetch failed: {e}")
        return []

    matched = []
    for tx in txs or []:
        ts = tx.get("timestamp", 0)
        if ts < since_unix:
            continue
        sig = tx.get("signature", "")
        # Token transfers (USDC SPL)
        for tt in tx.get("tokenTransfers", []) or []:
            if tt.get("toUserAccount") == vault and tt.get("mint") == USDC_MINT:
                amount_raw = tt.get("tokenAmount", {}).get("amount")
                try:
                    amount_ui = float(amount_raw) / (10 ** USDC_DECIMALS) if amount_raw else 0
                except Exception:
                    amount_ui = 0
                matched.append({
                    "sig": sig,
                    "ts": ts,
                    "amount": amount_ui,
                    "from": tt.get("fromUserAccount", ""),
                    "kind": "usdc_spl",
                })
        # Native SOL transfer fallback (in case contractor sent SOL — note as such)
        for nt in tx.get("nativeTransfers", []) or []:
            if nt.get("toUserAccount") == vault:
                sol_amt = float(nt.get("amount", 0)) / 1e9
                if sol_amt > 0:
                    matched.append({
                        "sig": sig,
                        "ts": ts,
                        "amount": sol_amt,
                        "from": nt.get("fromUserAccount", ""),
                        "kind": "sol_native",
                    })
    return matched


def _send_thank_you_sms(phone: str, name: str, amount: float, claim_id: str) -> dict:
    """Send a thank-you SMS via Vonage."""
    try:
        import jwt as pyjwt
        import httpx
    except ImportError:
        return {"ok": False, "error": "deps missing"}

    app_id = os.environ.get("VONAGE_APPLICATION_ID", "")
    key_path = os.environ.get("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    from_number = os.environ.get("VONAGE_NUMBER", "12142277528").lstrip("+")
    if not (app_id and os.path.exists(key_path)):
        return {"ok": False, "error": "vonage creds missing"}

    with open(key_path) as f:
        private_key = f.read()
    now = int(time.time())
    token = pyjwt.encode(
        {"iat": now, "exp": now + 180, "jti": str(uuid.uuid4()), "application_id": app_id},
        private_key, algorithm="RS256",
    )

    first = name.split()[0] if name else "there"
    body = (
        f"Empire AI: {first}, we got your ${amount:,.2f} payment \u2014 thanks. "
        f"Your account's settled. Reply STOP to opt out."
    )
    msg = {
        "from": from_number,
        "to": phone.lstrip("+"),
        "message_type": "text",
        "text": body[:1000],
        "channel": "sms",
    }
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                "https://api.nexmo.com/v1/messages",
                json=msg,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        return {"ok": r.status_code < 400, "status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _ping_telegram(text: str) -> bool:
    """Best-effort Telegram notification."""
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (bot and chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def _mark_paid(sb, fee: dict, tx_sig: str, tx_kind: str, tx_amount: float):
    """Mark a fee_event as paid + record tx details."""
    upd = {
        "status": "paid",
        "meta": {
            **(fee.get("meta") or {}),
            "paid_via": "vault_watcher",
            "tx_signature": tx_sig,
            "tx_kind": tx_kind,
            "tx_amount_usd": tx_amount,
            "paid_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    sb.table("fee_events").update(upd).eq("id", fee["id"]).execute()


def _is_already_paid_tx(sb, tx_sig: str) -> bool:
    """Check if a tx sig has already been recorded (idempotency)."""
    r = sb.table("fee_events").select("id").filter("meta->>tx_signature", "eq", tx_sig).limit(1).execute()
    return bool(r.data)


def run_poll(sb, since_hours: int = 168) -> dict:
    """One poll cycle. Returns counts."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    since_unix = int(time.time()) - since_hours * 3600

    pending = sb.table("fee_events").select(
        "id,claim_id,contractor_id,fee_amount,discount_amount,status,meta"
    ).eq("status", "pending").execute().data or []

    pending_count = len(pending)

    # ── Fetch transfers BEFORE the unmatched-insert loop ──────────
    # Always fetch transfers (even when no pending fees) so the ledger
    # captures ALL on-chain activity regardless of fee_event state.
    transfers = _fetch_recent_usdc_transfers(VAULT_WALLET, since_unix)
    log.info(f"[watcher] fetched {len(transfers)} transfers")

    # ── Upsert ALL USDC transfers as settled rows ──────────
    # This ensures the ledger is a complete record of on-chain activity
    # even for transfers unmatched to fee_events (manual attribution later).
    for tx in transfers:
        if tx["kind"] != "usdc_spl":
            continue
        try:
            # Idempotent: on_conflict on transaction_signature prevents duplicates.
            # No pre-check needed — the upsert itself is the guard.
            sb.table("empire_revenue_ledger").upsert({
                "status": "settled",
                "transaction_signature": tx["sig"],
                "sender_address": tx["from"],
                "destination_address": VAULT_WALLET,
                "usdc_amount": tx["amount"],
                "tracking_memo": "vault_watcher_poll | unmatched",
                "block_time_stamp": datetime.fromtimestamp(tx["ts"], tz=timezone.utc).isoformat(),
                "meta": {"source": "vault_watcher", "unmatched": True},
            }, on_conflict="transaction_signature").execute()
        except Exception as e:
            log.warning(f"[watcher] unmatched ledger upsert failed for {tx['sig'][:12]}: {e}")

    if not pending:
        log.info("[watcher] no pending fees — nothing to match against")
        result = {"pending": 0, "transfers": len(transfers), "matched": 0, "marked": 0}
        _log_activity(sb, run_id, started_at, result, pending_count)
        return result

    # (transfers already fetched above — reuse the same list)
    if not transfers:
        result = {"pending": pending_count, "transfers": 0, "matched": 0, "marked": 0}
        _log_activity(sb, run_id, started_at, result, pending_count)
        return result

    matched = 0
    marked = 0
    errors = 0
    for fee in pending:
        # Effective amount = original - discount
        original = float(fee["fee_amount"])
        disc = float(fee.get("discount_amount") or 0)
        expected = round(max(0.0, original - disc), 2)
        if expected <= 0:
            continue

        # Match within $0.05 tolerance (USDC rounding)
        for tx in transfers:
            if tx["kind"] != "usdc_spl":
                continue
            if abs(tx["amount"] - expected) > 0.05:
                continue
            if _is_already_paid_tx(sb, tx["sig"]):
                continue

            log.info(
                f"[watcher] MATCH: fee={fee['claim_id'][:24]} ${expected:,.2f} "
                f"<= tx {tx['sig'][:12]} ${tx['amount']:,.2f}"
            )
            try:
                _mark_paid(sb, fee, tx["sig"], tx["kind"], tx["amount"])
                matched += 1
                marked += 1
            except Exception as e:
                log.warning(f"[watcher] mark_paid failed for {fee['claim_id'][:24]}: {e}")
                errors += 1

            # ── Upsert into empire_revenue_ledger with status='settled' ──
            # This is the critical link: every detected on-chain USDC transfer
            # gets a settled row in the ledger so the dashboard/reports show
            # real on-chain activity distinct from accrued book entries.
            try:
                sb.table("empire_revenue_ledger").upsert({
                    "status": "settled",
                    "transaction_signature": tx["sig"],
                    "sender_address": tx["from"],
                    "destination_address": VAULT_WALLET,
                    "usdc_amount": tx["amount"],
                    "tracking_memo": f"vault_watcher_poll | fee_event={fee['claim_id'][:24]}",
                    "block_time_stamp": datetime.fromtimestamp(tx["ts"], tz=timezone.utc).isoformat(),
                    "meta": {"source": "vault_watcher", "fee_event_id": fee["id"]},
                }, on_conflict="transaction_signature").execute()
                log.info(f"[watcher] ledger upserted SETTLED: {tx['sig'][:12]}... ${tx['amount']:,.2f}")
            except Exception as e:
                log.warning(f"[watcher] ledger upsert failed for {tx['sig'][:12]}: {e}")

            # Thank-you SMS + Telegram ping
            cid = fee.get("contractor_id")
            if cid:
                c = sb.table("contractors").select("name,phone").eq("id", cid).limit(1).execute().data
                if c and c[0].get("phone"):
                    try:
                        r = _send_thank_you_sms(c[0]["phone"], c[0].get("name", "Contractor"), expected, fee["claim_id"])
                        log.info(f"[watcher] thank-you SMS: {r}")
                    except Exception as e:
                        log.warning(f"[watcher] thank-you SMS failed: {e}")

            _ping_telegram(
                f"\U0001F4B0 Payment received!\n"
                f"Fee: ${expected:,.2f} (was ${original:,.2f})\n"
                f"Claim: {fee['claim_id']}\n"
                f"TX: {tx['sig'][:24]}..."
            )
            break  # one tx per fee

    result = {
        "pending": pending_count,
        "transfers": len(transfers),
        "matched": matched,
        "marked": marked,
    }
    _log_activity(sb, run_id, started_at, result, pending_count, errors)
    return result


def _log_activity(sb, run_id: str, started_at: str, result: dict, pending_count: int, errors: int = 0):
    """Log a vault watcher poll cycle to the agent_activity table for audit trail."""
    status = "ok" if errors == 0 else "error"
    summary_parts = [
        f"pending_fees={result['pending']}",
        f"transfers_fetched={result['transfers']}",
        f"matched={result['matched']}",
        f"marked_paid={result['marked']}",
    ]
    if errors:
        summary_parts.append(f"errors={errors}")
    try:
        sb.table("agent_activity").insert({
            "agent_name": "vault_watcher",
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_seen": pending_count,
            "rows_processed": result["transfers"],
            "rows_errored": errors,
            "summary": " ".join(summary_parts),
            "meta": result,
        }).execute()
        log.info(f"[watcher] agent_activity logged: {' '.join(summary_parts)}")
    except Exception as e:
        log.debug(f"[watcher] agent_activity insert failed: {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--loop", action="store_true", help="poll every N seconds (default 300)")
    p.add_argument("--interval", type=int, default=300, help="seconds between polls (default 300)")
    p.add_argument("--since", type=int, default=168, help="lookback hours (default 168 = 7d)")
    args = p.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    if not args.loop:
        result = run_poll(sb, args.since)
        print(json.dumps(result, indent=2))
        return

    log.info(f"[watcher] starting loop — every {args.interval}s, lookback {args.since}h")
    while True:
        try:
            r = run_poll(sb, args.since)
            log.info(f"[watcher] cycle: {r}")
        except KeyboardInterrupt:
            log.info("[watcher] interrupted")
            break
        except Exception as e:
            log.warning(f"[watcher] cycle error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()