"""
Empire AI · Dispatch Invoicing
================================

Pay-per-lead billing for outreach events. Each contractor dispatch
(non-subscribers primarily) creates an invoice. Contractor pays via
the existing /pay/dispatch/<id> page.

Flow:
  1. Outreach fires (call, sms, email) to a contractor
  2. scripts/invoice_dispatch.py or /api/v1/dispatch/charge creates invoice
  3. Contractor sees "you owe $X USDC for this lead" + pay link
  4. Payment verified via Helius (same pattern as subscription)
  5. Invoice marked paid, contractor unlocked for future outreach

Standard pricing:
  - Roofing:    $35 USDC per outbound call/SMS/email
  - HVAC:       $40 USDC
  - Legal:      $75 USDC (higher value, higher CAC)
  - Insurance:  $60 USDC
"""
import os
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from solana.rpc.async_api import AsyncClient
from supabase import create_client

log = logging.getLogger("dispatch_invoice")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VAULT_WALLET = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
RPC_URL = os.environ.get("HELIUS_RPC_URL", "https://api.mainnet.helius-rpc.com")
RPC_KEY = os.environ.get("HELIUS_API_KEY", "")

# Pricing per outreach event by niche
NICHE_PRICING = {
    "roofing": 35,
    "hvac": 40,
    "legal": 75,
    "insurance": 60,
    "life insurance agent": 60,
    "debt consolidation": 50,
    "medicare advantage agent": 55,
    "final expense insurance": 50,
    "personal injury lawyer": 80,
    "workers comp lawyer": 75,
    "medical malpractice lawyer": 85,
    "class action lawyer": 80,
    "mass tort": 100,
}


def price_for_dispatch(niche: str, outreach_type: str = "call") -> float:
    base = NICHE_PRICING.get(niche.lower(), 30)
    # Email is cheaper, call is full price, SMS is mid
    if outreach_type == "email":
        return base * 0.4
    if outreach_type == "sms":
        return base * 0.6
    return base


def create_invoice(contractor_id: str, dispatch_id: str, niche: str,
                   outreach_type: str = "call", memo: str = None) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    amount = price_for_dispatch(niche, outreach_type)
    # Skip invoice if contractor is active subscriber (tier-gated)
    sub = sb.table("contractor_subscriptions").select("tier,status,monthly_amount_usdc").eq("contractor_id", contractor_id).limit(1).execute().data
    if sub and sub[0].get("status") == "active":
        return {"ok": True, "skipped": True, "reason": f"active {sub[0]['tier']} subscriber"}
    row = {
        "contractor_id": contractor_id,
        "dispatch_id": dispatch_id,
        "amount_usdc": amount,
        "status": "unpaid",
        "memo": memo or f"{niche} {outreach_type} outreach",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    r = sb.table("dispatch_invoices").insert(row).execute()
    return {"ok": True, "invoice_id": r.data[0]["id"] if r.data else None,
            "amount_usdc": amount, "vault_wallet": VAULT_WALLET,
            "memo": row["memo"], "expires_at": row["expires_at"]}


async def check_invoice_payment(wallet: str, amount_usdc: float, since_ts: int) -> dict:
    """Check if `wallet` sent >= amount_usdc USDC to the vault since since_ts."""
    if not RPC_KEY:
        return {"verified": False, "amount_usdc": 0.0, "tx_sig": None,
                "error": "HELIUS_API_KEY not set"}
    rpc_url = f"{RPC_URL}?api-key={RPC_KEY}"
    payload = {
        "jsonrpc": "2.0", "id": "v", "method": "getSignaturesForAddress",
        "params": [VAULT_WALLET, {"limit": 30, "commitment": "confirmed"}]
    }
    try:
        async with AsyncClient(rpc_url) as client:
            r = await client._provider.make_request(payload, timeout=20)
            sigs = r.value if hasattr(r, "value") else r.get("result", [])
    except Exception as e:
        return {"verified": False, "amount_usdc": 0.0, "tx_sig": None, "error": f"rpc: {e}"}

    target_wallet = wallet.strip()
    for s in (sigs or [])[:15]:
        block_time = s.get("blockTime", 0) if isinstance(s, dict) else getattr(s, "block_time", 0) or 0
        if block_time < since_ts:
            continue
        sig_str = s.get("signature") if isinstance(s, dict) else str(s.signature)
        try:
            payload = {
                "jsonrpc": "2.0", "id": "t", "method": "getTransaction",
                "params": [sig_str, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }
            async with AsyncClient(rpc_url) as client:
                r = await client._provider.make_request(payload, timeout=15)
                tx = r.value if hasattr(r, "value") else r.get("result")
            if not tx:
                continue
            # Inspect token transfers in meta
            meta = tx.get("meta", {}) if isinstance(tx, dict) else {}
            pre = meta.get("preTokenBalances", []) or []
            post = meta.get("postTokenBalances", []) or []
            # Match: source wallet, destination vault, USDC mint, amount >= target
            for pre_b, post_b in zip(pre, post):
                if (pre_b.get("owner") == target_wallet
                        and post_b.get("owner") == VAULT_WALLET
                        and pre_b.get("mint") == USDC_MINT):
                    pre_amt = float(pre_b.get("uiTokenAmount", {}).get("uiAmount") or 0)
                    post_amt = float(post_b.get("uiTokenAmount", {}).get("uiAmount") or 0)
                    sent = pre_amt - post_amt
                    if sent >= amount_usdc * 0.95:  # 5% tolerance for dust
                        return {"verified": True, "amount_usdc": sent,
                                "tx_sig": sig_str, "ts": block_time}
            # Also check inner instructions for SPL transfers
            for group in (meta.get("innerInstructions") or []):
                for ix in group.get("instructions", []):
                    info = (ix.get("parsed") or {}).get("info") or {}
                    if (info.get("source") == target_wallet
                            and info.get("destination") == VAULT_WALLET
                            and info.get("mint") == USDC_MINT):
                        amt = float(info.get("tokenAmount", {}).get("uiAmount") or 0)
                        if amt >= amount_usdc * 0.95:
                            return {"verified": True, "amount_usdc": amt,
                                    "tx_sig": sig_str, "ts": block_time}
        except Exception as e:
            log.debug(f"tx parse {sig_str[:8]}... failed: {e}")
    return {"verified": False, "amount_usdc": 0.0, "tx_sig": None}


def mark_invoice_paid(invoice_id: str, tx_sig: str, amount: float) -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    sb.table("dispatch_invoices").update({
        "status": "paid",
        "paid_at": datetime.now(timezone.utc).isoformat(),
        "paid_tx_sig": tx_sig,
    }).eq("id", invoice_id).execute()
    return {"ok": True}


def check_all_unpaid() -> dict:
    """Cron: scan unpaid invoices, check on-chain, mark paid if found."""
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    unpaid = sb.table("dispatch_invoices").select(
        "id,contractor_id,amount_usdc,created_at,expires_at"
    ).eq("status", "unpaid").execute().data or []
    paid_count = 0
    for inv in unpaid:
        # Skip if expired
        if inv.get("expires_at") and inv["expires_at"] < datetime.now(timezone.utc).isoformat():
            sb.table("dispatch_invoices").update({"status": "expired"}).eq("id", inv["id"]).execute()
            continue
        # Get contractor wallet
        cont = sb.table("contractors").select("solana_wallet").eq("id", inv["contractor_id"]).limit(1).execute().data
        wallet = cont[0].get("solana_wallet") if cont else None
        if not wallet:
            continue
        # Look back 30 days
        since_ts = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        r = asyncio.run(check_invoice_payment(wallet, float(inv["amount_usdc"]), since_ts))
        if r.get("verified"):
            mark_invoice_paid(inv["id"], r["tx_sig"], r["amount_usdc"])
            paid_count += 1
            log.info(f"  ✅ {inv['id'][:8]} ${inv['amount_usdc']} paid by {wallet[:8]}...")
    return {"scanned": len(unpaid), "paid": paid_count}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: dispatch_invoice.py [check-all|<contractor_id> <dispatch_id> <niche> [outreach_type]]")
        sys.exit(1)
    if sys.argv[1] == "check-all":
        r = check_all_unpaid()
        print(f"scanned: {r['scanned']}, paid: {r['paid']}")
    elif len(sys.argv) >= 4:
        contractor_id = sys.argv[1]
        dispatch_id = sys.argv[2]
        niche = sys.argv[3]
        outreach = sys.argv[4] if len(sys.argv) > 4 else "call"
        r = create_invoice(contractor_id, dispatch_id, niche, outreach)
        print(r)