#!/usr/bin/env python3
"""
EMPIRE V49 · VAULT MONITOR
===========================
Checks the Solana vault wallet for USDC balance and alerts via Telegram
when new deposits arrive. Tracks last known balance in a local state file
so it only fires alerts for new deposits, not every check.

Run modes:
    python3 scripts/vault_monitor.py              # full check + alert
    python3 scripts/vault_monitor.py --quiet       # silent check (log only)
    python3 scripts/vault_monitor.py --force       # re-alert even if balance unchanged
    python3 scripts/vault_monitor.py --loop        # continuous PM2 mode (checks every 60s)
    python3 scripts/vault_monitor.py --loop --interval 30  # custom interval (seconds)
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timezone

import httpx

log = logging.getLogger("vault_monitor")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)

# ── Vault wallet ──────────────────────────────────────────────────
VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# ── Local state tracking ─────────────────────────────────────────
STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "vault_monitor_state.json"
)

# ── Telegram ──────────────────────────────────────────────────────
def _tg_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")

def _tg_chat() -> str:
    return os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "808657420")


def _load_state() -> dict:
    """Load last-known balance from state file."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load state file: {e}")
    return {"last_usdc": 0.0, "last_seen": None}


def _save_state(usdc: float):
    """Persist last-known balance to state file."""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "last_usdc": round(usdc, 2),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)
    except Exception as e:
        log.warning(f"Failed to save state file: {e}")


async def _send_telegram(message: str) -> bool:
    """Send a Telegram alert to the operator."""
    token = _tg_token()
    chat_id = _tg_chat()
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN not set — skipping alert")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if r.status_code == 200:
                return True
            else:
                log.warning(f"Telegram API error {r.status_code}: {r.text[:200]}")
                return False
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


async def check_vault(quiet: bool = False, force: bool = False) -> dict:
    """Check vault wallet USDC balance and alert if new deposits found."""
    state = _load_state()
    last_usdc = state.get("last_usdc", 0.0)

    # Query SOL balance
    sol_balance = 0.0
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(SOLANA_RPC, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getBalance",
                "params": [VAULT_WALLET],
            })
            data = r.json()
            if "result" in data:
                sol_balance = data["result"]["value"] / 1e9
    except Exception as e:
        log.error(f"SOL balance check failed: {e}")

    # Query USDC token balance
    current_usdc = 0.0
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(SOLANA_RPC, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    VAULT_WALLET,
                    {"mint": USDC_MINT},
                    {"encoding": "jsonParsed"},
                ],
            })
            data = r.json()
            if "result" in data:
                accounts = data["result"]["value"]
                for acc in accounts:
                    amount = (
                        acc.get("account", {})
                        .get("data", {})
                        .get("parsed", {})
                        .get("info", {})
                        .get("tokenAmount", {})
                        .get("uiAmount", 0)
                    )
                    current_usdc += amount or 0
    except Exception as e:
        log.error(f"USDC balance check failed: {e}")

    current_usdc = round(current_usdc, 2)

    # Determine if a new deposit arrived
    new_deposit = False
    deposit_amount = 0.0
    if current_usdc > last_usdc:
        deposit_amount = round(current_usdc - last_usdc, 2)
        new_deposit = True

    # Persist new state
    if new_deposit or force:
        _save_state(current_usdc)

    # Build summary
    summary = {
        "sol": sol_balance,
        "usdc": current_usdc,
        "last_usdc": last_usdc,
        "new_deposit": new_deposit,
        "deposit_amount": deposit_amount,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    # Log
    if new_deposit:
        log.info(
            f"💰 NEW DEPOSIT: ${deposit_amount:,.2f} USDC "
            f"(was ${last_usdc:,.2f}, now ${current_usdc:,.2f})"
        )
    else:
        log.info(
            f"Checked vault: ${current_usdc:,.2f} USDC | "
            f"{sol_balance:.6f} SOL | no change"
        )

    # Telegram alert
    if new_deposit and not quiet:
        message = (
            f"💰 <b>Vault Deposit Received</b>\n\n"
            f"Amount: <b>${deposit_amount:,.2f} USDC</b>\n"
            f"New Balance: <b>${current_usdc:,.2f} USDC</b>\n"
            f"SOL: {sol_balance:.6f}\n\n"
            f"Wallet: <code>{VAULT_WALLET}</code>\n"
            f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n\n"
            f"Run fee report: <code>python3 scripts/link_fee_events.py</code>"
        )
        sent = await _send_telegram(message)
        summary["telegram_alerted"] = sent
        if sent:
            log.info("Telegram alert sent")
    elif force and not quiet:
        message = (
            f"🔍 <b>Vault Balance Check</b>\n\n"
            f"Balance: <b>${current_usdc:,.2f} USDC</b>\n"
            f"SOL: {sol_balance:.6f}\n\n"
            f"Wallet: <code>{VAULT_WALLET}</code>"
        )
        sent = await _send_telegram(message)
        summary["telegram_alerted"] = sent

    return summary


def main():
    # Load env
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.expanduser("~/.env"))
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Solana vault wallet monitor")
    p.add_argument("--quiet", action="store_true", help="No Telegram alert")
    p.add_argument("--force", action="store_true", help="Force re-alert")
    p.add_argument("--loop", action="store_true", help="Run continuously (PM2 mode)")
    p.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
    args = p.parse_args()

    import asyncio

    if args.loop:
        log.info(f"Vault monitor starting in loop mode (interval={args.interval}s)")
        while True:
            try:
                result = asyncio.run(check_vault(quiet=args.quiet, force=args.force))
                print(json.dumps(result, indent=2, default=str))
            except Exception as e:
                log.error(f"Loop iteration failed: {e}")
            time.sleep(args.interval)
    else:
        result = asyncio.run(check_vault(quiet=args.quiet, force=args.force))
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
