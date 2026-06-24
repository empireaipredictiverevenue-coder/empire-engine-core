"""
Empire AI · Subscription Tier Manager
======================================

Manages contractor subscriptions via monthly USDC payments to the vault
("Streamflow-style" — recurring on-chain transfers).

Flow:
  1. Contractor hits POST /api/v1/subscribe/activate with wallet + tier
  2. We create contractor_subscriptions row with status=pending
  3. Contractor sends X USDC to vault (any wallet: Phantom, Solflare, etc)
  4. We poll Helius for incoming USDC txs from that wallet
  5. On match: status=active, last_payment_at=now, expires_at=+30d
  6. Cron: when expires_at passes, status=lapsed (unless renewed)

Run:
  POST /api/v1/subscribe/activate  → start a subscription
  POST /api/v1/subscribe/cancel    → cancel (status=cancelled)
  GET  /api/v1/subscribe/me        → current tier + expiry
  POST /api/v1/subscribe/verify    → trigger payment verification now
"""
import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature
from supabase import create_client

log = logging.getLogger("subscription")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC on mainnet
RPC_URL = os.environ.get("HELIUS_RPC_URL", "https://api.mainnet.helius-rpc.com")
RPC_KEY = os.environ.get("HELIUS_API_KEY", "")


async def verify_wallet_payment(wallet: str, min_amount_usdc: float, since_ts: int) -> dict:
    """Check if `wallet` sent >= min_amount_usdc USDC to the vault since since_ts.

    Returns {"verified": bool, "amount_usdc": float, "tx_sig": str|None, "ts": int|None}
    """
    if not RPC_KEY:
        return {"verified": False, "amount_usdc": 0.0, "tx_sig": None, "ts": None,
                "error": "HELIUS_API_KEY not set"}

    rpc_url = f"{RPC_URL}?api-key={RPC_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "verify",
        "method": "getSignaturesForAddress",
        "params": [
            VAULT_WALLET,
            {"limit": 50, "commitment": "confirmed"}
        ]
    }
    try:
        async with AsyncClient(rpc_url) as client:
            r = await client._provider.make_request(payload, timeout=20)
            sigs = r.value if hasattr(r, "value") else r.get("result", [])
    except Exception as e:
        return {"verified": False, "amount_usdc": 0.0, "tx_sig": None, "ts": None,
                "error": f"rpc: {e}"}

    if not sigs:
        return {"verified": False, "amount_usdc": 0.0, "tx_sig": None, "ts": None}

    # Filter to txs after since_ts, then look up each to find USDC transfers from `wallet`
    candidate_sigs = []
    for s in sigs[:30]:
        block_time = s.get("blockTime", 0) if isinstance(s, dict) else getattr(s, "block_time", 0) or 0
        if block_time >= since_ts:
            sig_str = s.get("signature") if isinstance(s, dict) else str(s.signature)
            candidate_sigs.append((sig_str, block_time))

    if not candidate_sigs:
        return {"verified": False, "amount_usdc": 0.0, "tx_sig": None, "ts": None}

    # Parse each transaction looking for USDC transfer from `wallet` to VAULT_WALLET
    total_usdc = 0.0
    matched_sig = None
    matched_ts = None
    target_wallet = wallet.strip()
    for sig_str, block_time in candidate_sigs[:10]:  # limit lookups
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "tx",
                "method": "getTransaction",
                "params": [sig_str, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }
            async with AsyncClient(rpc_url) as client:
                r = await client._provider.make_request(payload, timeout=15)
                tx = r.value if hasattr(r, "value") else r.get("result")
            if not tx:
                continue
            meta = tx.get("meta") if isinstance(tx, dict) else None
            if not meta:
                continue
            inner = meta.get("innerInstructions") or []
            for group in inner:
                for ix in group.get("instructions", []):
                    parsed = ix.get("parsed") or {}
                    info = parsed.get("info") or {}
                    if (info.get("source") == target_wallet
                            and info.get("destination") == VAULT_WALLET
                            and info.get("mint") == USDC_MINT):
                        amt = float(info.get("tokenAmount", {}).get("uiAmount") or 0)
                        if amt >= min_amount_usdc:
                            return {"verified": True, "amount_usdc": amt,
                                    "tx_sig": sig_str, "ts": block_time}
                    # also check top-level instructions for SOL transfers (vault config might allow SOL)
            message = tx.get("transaction", {}).get("message", {})
            for ix in message.get("instructions", []):
                parsed = ix.get("parsed") or {}
                info = parsed.get("info") or {}
                if (info.get("source") == target_wallet
                        and info.get("destination") == VAULT_WALLET
                        and info.get("mint") == USDC_MINT):
                    amt = float(info.get("tokenAmount", {}).get("uiAmount") or 0)
                    total_usdc += amt
                    if amt >= min_amount_usdc and matched_sig is None:
                        matched_sig = sig_str
                        matched_ts = block_time
        except Exception as e:
            log.debug(f"tx parse {sig_str[:8]}... failed: {e}")

    if total_usdc >= min_amount_usdc:
        return {"verified": True, "amount_usdc": total_usdc,
                "tx_sig": matched_sig, "ts": matched_ts}
    return {"verified": False, "amount_usdc": total_usdc,
            "tx_sig": None, "ts": None}


def activate_subscription(contractor_id: str, wallet: str, tier: str) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    tier_row = sb.table("subscription_tiers").select("*").eq("id", tier).limit(1).execute().data
    if not tier_row:
        return {"ok": False, "error": f"unknown tier: {tier}"}
    monthly = float(tier_row[0]["monthly_usdc"])
    if monthly == 0:
        return {"ok": False, "error": "free tier — no subscription needed"}
    # Upsert (allow tier change)
    row = {
        "contractor_id": contractor_id,
        "tier": tier,
        "monthly_amount_usdc": monthly,
        "status": "pending",
        "wallet_address": wallet,
        "next_payment_due_at": datetime.now(timezone.utc).isoformat(),
        "notes": f"Activated {datetime.now(timezone.utc).isoformat()}",
    }
    sb.table("contractor_subscriptions").upsert(row, on_conflict="contractor_id").execute()
    return {"ok": True, "monthly_usdc": monthly,
            "vault_wallet": VAULT_WALLET,
            "memo": f"empire-{tier}-{contractor_id[:8]}"}


async def verify_subscription(contractor_id: str) -> dict:
    """Poll on-chain for that wallet's most recent payment >= tier monthly_usdc."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    sub = sb.table("contractor_subscriptions").select("*").eq("contractor_id", contractor_id).limit(1).execute().data
    if not sub:
        return {"ok": False, "error": "no subscription"}
    sub = sub[0]
    if sub["status"] == "cancelled":
        return {"ok": False, "error": "cancelled"}
    if not sub.get("wallet_address"):
        return {"ok": False, "error": "no wallet"}
    tier_row = sb.table("subscription_tiers").select("monthly_usdc").eq("id", sub["tier"]).limit(1).execute().data
    monthly = float(tier_row[0]["monthly_usdc"]) if tier_row else float(sub["monthly_amount_usdc"])
    # Look back 35 days
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=35)).timestamp())
    result = await verify_wallet_payment(sub["wallet_address"], monthly, since_ts)
    if result.get("verified"):
        new_expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        sb.table("contractor_subscriptions").update({
            "status": "active",
            "started_at": sub.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "expires_at": new_expires,
            "next_payment_due_at": new_expires,
            "last_payment_at": datetime.fromtimestamp(result["ts"], timezone.utc).isoformat() if result.get("ts") else None,
            "last_payment_tx_sig": result.get("tx_sig"),
        }).eq("id", sub["id"]).execute()
        return {"ok": True, "verified": True, "amount_usdc": result["amount_usdc"], "tx_sig": result.get("tx_sig")}
    return {"ok": True, "verified": False, "amount_usdc": result.get("amount_usdc", 0)}


def cancel_subscription(contractor_id: str) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    sb.table("contractor_subscriptions").update({
        "status": "cancelled",
        "notes": f"Cancelled {datetime.now(timezone.utc).isoformat()}",
    }).eq("contractor_id", contractor_id).execute()
    return {"ok": True}


def get_subscription(contractor_id: str) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    sub = sb.table("contractor_subscriptions").select("*").eq("contractor_id", contractor_id).limit(1).execute().data
    if not sub:
        return {"tier": "free", "status": "free", "monthly_usdc": 0, "expires_at": None}
    sub = sub[0]
    return {
        "tier": sub["tier"],
        "status": sub["status"],
        "monthly_usdc": float(sub["monthly_amount_usdc"]),
        "wallet_address": sub.get("wallet_address"),
        "started_at": sub.get("started_at"),
        "expires_at": sub.get("expires_at"),
        "last_payment_at": sub.get("last_payment_at"),
        "last_payment_tx_sig": sub.get("last_payment_tx_sig"),
    }


def expire_lapsed() -> dict:
    """Cron: any sub past expires_at → status=lapsed."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    now = datetime.now(timezone.utc).isoformat()
    r = sb.table("contractor_subscriptions").update({"status": "lapsed"}).eq("status", "active").lt("expires_at", now).execute()
    return {"expired": len(r.data or [])}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: subscription.py [verify-all|expire-lapsed|<contractor_id> verify]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "verify-all":
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        subs = sb.table("contractor_subscriptions").select("contractor_id,wallet_address,tier,monthly_amount_usdc").in_("status", ["pending", "active", "lapsed"]).execute().data
        verified = 0
        for s in subs or []:
            r = asyncio.run(verify_subscription(s["contractor_id"]))
            if r.get("verified"):
                verified += 1
                print(f"  ✅ {s['contractor_id'][:8]} {s['tier']} ${s['monthly_amount_usdc']}/mo → verified")
            else:
                print(f"  ⏳ {s['contractor_id'][:8]} {s['tier']} ${s['monthly_amount_usdc']}/mo → not yet (${r.get('amount_usdc', 0)})")
        print(f"\nresult: {verified}/{len(subs)} verified")
    elif cmd == "expire-lapsed":
        r = expire_lapsed()
        print(f"expired: {r['expired']}")
    elif cmd.endswith("verify"):
        cid = cmd[:-7].rstrip()
        r = asyncio.run(verify_subscription(cid))
        print(r)