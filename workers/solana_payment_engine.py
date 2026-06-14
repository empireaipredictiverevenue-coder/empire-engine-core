"""
Empire AI · Solana USDC Revenue Tracker
========================================
On-chain listener that verifies USDC transfers to the Empire vault wallet
and logs them to the empire_revenue_ledger table.

ARCHITECTURE
────────────
Two deployment modes:

  1. Standalone service (port 8070) — run via deploy_payments.sh
     → uvicorn workers.solana_payment_engine:app --host 0.0.0.0 --port 8070

  2. Hub-integrated route — hub.py imports and calls register_solana_routes()
     → POST /api/v1/payments/verify-usdc becomes available on the main API.

Both modes share the same verification logic. The standalone mode is useful
for isolating RPC traffic; the hub mode keeps the fleet unified.

FLOW
────
  1. Client sends {signature_hash, campaign_memo_id} to /verify-usdc
  2. Engine queries Solana RPC via getTransaction (JSON-RPC)
  3. Parses preTokenBalances / postTokenBalances for USDC mint
  4. Computes delta → verified amount
  5. Writes row to empire_revenue_ledger in Supabase

ENV VARS
────────
  SUPABASE_URL             Supabase project URL
  SUPABASE_SERVICE_ROLE_KEY  Service role key (NOT anon key)
  SOLANA_RPC_URL           Solana JSON-RPC endpoint (Helius, public, etc.)
  EMPIRE_VAULT_WALLET      The Empire vault wallet address (receiving USDC)
  EMPIRE_USDC_MINT         USDC SPL token mint address (optional, defaults to mainnet)
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, Field

log = logging.getLogger("empire.solana.revenue")

# ── Constants ────────────────────────────────────────────────────
# Mainnet USDC SPL token mint (used if EMPIRE_USDC_MINT is not set)
_USDC_MINT_MAINNET = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


# ── Pydantic models ──────────────────────────────────────────────

class TxnPayload(BaseModel):
    """Incoming payment verification request."""
    signature_hash: str = Field(..., min_length=32, max_length=128,
                                description="Solana transaction signature")
    campaign_memo_id: str = Field(default="", max_length=256,
                                  description="Campaign or lead link ID for attribution")


class PaymentResult(BaseModel):
    """Response returned after successful verification."""
    status: str
    signature: str
    amount_usdc: float
    campaign_assigned: str


# ── The Engine ────────────────────────────────────────────────────

class SolanaRevenueEngine:
    """
    Verifies on-chain USDC transfers to the Empire vault wallet and logs
    them to the empire_revenue_ledger table.
    """

    def __init__(
        self,
        get_db: Callable,
        supabase_url: str = "",
        supabase_key: str = "",
        solana_rpc_url: str = "https://api.mainnet-beta.solana.com",
        empire_vault_wallet: str = "",
        usdc_mint: str = "",
    ):
        self.get_db = get_db
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.solana_rpc_url = solana_rpc_url
        self.vault_wallet = empire_vault_wallet
        self.usdc_mint = usdc_mint or os.environ.get("EMPIRE_USDC_MINT", _USDC_MINT_MAINNET)

        self.stats = {
            "transactions_verified": 0,
            "transactions_failed": 0,
            "total_usdc_logged": 0.0,
            "last_verified": None,
        }

        # ── Payment-verified callbacks ────────────────────────────
        # List of async callables fired when a payment is successfully
        # verified and logged. Each receives a single dict argument:
        #   {signature, amount_usdc, sender, campaign, timestamp}
        self.on_payment_verified: list = []

    async def verify_solana_transaction(self, tx_hash: str) -> dict:
        """Query the live Solana blockchain via JSON-RPC for transaction details."""
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                tx_hash,
                {"encoding": "json", "maxSupportedTransactionVersion": 0},
            ],
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.solana_rpc_url, json=rpc_payload, timeout=15.0
                )
                if response.status_code == 200:
                    return response.json()
                log.warning(
                    f"[solana.revenue] RPC returned {response.status_code}: "
                    f"{response.text[:200]}"
                )
            except httpx.TimeoutException:
                log.warning("[solana.revenue] RPC timeout")
            except Exception as e:
                log.warning(f"[solana.revenue] RPC error: {e}")
        return {}

    async def log_payment_to_supabase(
        self,
        tx_hash: str,
        sender: str,
        destination: str,
        amount: float,
        memo: str,
        block_time: Optional[str] = None,
    ) -> bool:
        """Write a verified on-chain transfer record into the Supabase ledger.

        Uses the REST API directly (not the supabase-py client) to keep this
        module dependency-light for standalone deployment.
        """
        if not self.supabase_url or not self.supabase_key:
            # Fall back to supabase-py client if available
            try:
                db = self.get_db()
                db.table("empire_revenue_ledger").insert({
                    "transaction_signature": tx_hash,
                    "sender_address": sender,
                    "destination_address": destination,
                    "usdc_amount": amount,
                    "tracking_memo": memo,
                    "block_time_stamp": block_time,
                    "meta": {"source": "solana_payment_engine"},
                }).execute()
                return True
            except Exception as e:
                log.error(f"[solana.revenue] DB insert failed: {e}")
                return False

        # REST API path (for standalone mode)
        headers = {
            "ApiKey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        payload = {
            "transaction_signature": tx_hash,
            "sender_address": sender,
            "destination_address": destination,
            "usdc_amount": amount,
            "tracking_memo": memo,
            "block_time_stamp": block_time,
            "meta": {"source": "solana_payment_engine"},
        }
        url = f"{self.supabase_url}/rest/v1/empire_revenue_ledger"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(url, headers=headers, json=payload, timeout=10.0)
                if res.status_code >= 400:
                    log.error(
                        f"[solana.revenue] Supabase insert failed ({res.status_code}): "
                        f"{res.text[:200]}"
                    )
                    return False
                return True
        except Exception as e:
            log.error(f"[solana.revenue] Supabase POST error: {e}")
            return False

    async def verify_and_log_payment(
        self,
        signature_hash: str,
        campaign_memo_id: str = "",
    ) -> dict:
        """
        Full verification pipeline:
          1. Fetch transaction from Solana RPC
          2. Validate transaction exists and has no errors
          3. Parse token balances to find USDC transfers to vault wallet
          4. Log to Supabase empire_revenue_ledger
          5. Return verified amount + status
        """
        # Step 1: Fetch from RPC
        tx_data = await self.verify_solana_transaction(signature_hash)
        result = tx_data.get("result")

        if not result:
            raise HTTPException(
                status_code=400,
                detail="Transaction signature not found on-chain. It may still be pending or the signature is invalid.",
            )

        # Step 2: Validate
        meta = result.get("meta", {})
        if meta.get("err"):
            raise HTTPException(
                status_code=400,
                detail="Transaction is flagged as a failed chain event (has an error).",
            )

        # Step 3: Parse token balances for USDC mint
        pre_token_balances = meta.get("preTokenBalances", [])
        post_token_balances = meta.get("postTokenBalances", [])

        usdc_transfer_found = False
        extracted_amount = 0.0
        detected_sender = "UNKNOWN"
        block_time = result.get("blockTime")
        block_time_iso = (
            datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat()
            if block_time
            else None
        )

        # Build a lookup: accountIndex → pre-token amount
        pre_by_index = {}
        for pre in pre_token_balances:
            if pre.get("mint") == self.usdc_mint:
                idx = pre.get("accountIndex")
                pre_by_index[idx] = float(pre.get("uiTokenAmount", {}).get("amount", 0))

        # Scan post balances to find our vault wallet
        for post in post_token_balances:
            if post.get("mint") != self.usdc_mint:
                continue
            owner = post.get("owner", "")
            if owner == self.vault_wallet:
                account_index = post.get("accountIndex")
                pre_amount = pre_by_index.get(account_index, 0.0)
                post_amount = float(post.get("uiTokenAmount", {}).get("amount", 0))

                # USDC has 6 decimal places on Solana
                delta = (post_amount - pre_amount) / 1_000_000.0
                if delta > 0:
                    extracted_amount = delta
                    usdc_transfer_found = True
                    # Find sender: look at pre-balance for a non-vault owner of this mint
                    for pre in pre_token_balances:
                        if (pre.get("mint") == self.usdc_mint
                                and pre.get("owner", "") != self.vault_wallet
                                and pre.get("accountIndex") != account_index):
                            # Check if this account's balance decreased
                            pre_idx = pre.get("accountIndex")
                            pre_amt = pre_by_index.get(pre_idx, 0.0)
                            post_amt = 0.0
                            for p in post_token_balances:
                                if p.get("accountIndex") == pre_idx:
                                    post_amt = float(p.get("uiTokenAmount", {}).get("amount", 0))
                                    break
                            if pre_amt > post_amt:
                                detected_sender = pre.get("owner", "UNKNOWN")
                                break
                    if detected_sender == "UNKNOWN":
                        # Fallback: check transaction message for fee payer
                        tx_json = result.get("transaction", {})
                        msg = tx_json.get("message", {})
                        accts = msg.get("accountKeys", [])
                        if accts:
                            detected_sender = accts[0] if isinstance(accts[0], str) else accts[0].get("pubkey", "UNKNOWN")
                    break

        if not usdc_transfer_found:
            self.stats["transactions_failed"] += 1
            raise HTTPException(
                status_code=422,
                detail="Transaction does not contain a valid USDC transfer to the Empire vault wallet.",
            )

        # Step 4: Log to Supabase
        logged = await self.log_payment_to_supabase(
            tx_hash=signature_hash,
            sender=detected_sender,
            destination=self.vault_wallet,
            amount=extracted_amount,
            memo=campaign_memo_id,
            block_time=block_time_iso,
        )

        # Update stats
        self.stats["transactions_verified"] += 1
        self.stats["total_usdc_logged"] += extracted_amount
        self.stats["last_verified"] = {
            "signature": signature_hash,
            "amount": extracted_amount,
            "campaign": campaign_memo_id,
            "logged": logged,
            "at": datetime.now(timezone.utc).isoformat(),
        }

        log.info(
            f"[solana.revenue] VERIFIED: {extracted_amount} USDC "
            f"from {detected_sender[:8]}... "
            f"sig={signature_hash[:16]}... "
            f"logged={logged}"
        )

        # Fire payment-verified callbacks (non-blocking, each runs
        # as a separate task so a slow handler never delays the API response)
        if self.on_payment_verified and logged:
            payment_event = {
                "signature": signature_hash,
                "amount_usdc": extracted_amount,
                "sender": detected_sender,
                "campaign": campaign_memo_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            import asyncio as _pay_asyncio
            for cb in self.on_payment_verified:
                try:
                    _pay_asyncio.ensure_future(cb(payment_event))
                except Exception as _cb_err:
                    log.warning(f"[solana.revenue] callback error: {_cb_err}")

        return {
            "status": "REVENUE_VERIFIED_AND_LOCKED",
            "signature": signature_hash,
            "amount_usdc": extracted_amount,
            "campaign_assigned": campaign_memo_id,
            "sender": detected_sender,
            "logged_to_supabase": logged,
        }


# ── Standalone FastAPI App ───────────────────────────────────────

app = FastAPI(
    title="Empire AI · Solana Revenue Engine",
    version="1.0.0",
    description="On-chain USDC payment verification for the Empire AI revenue ledger.",
)

# Engine singleton for standalone mode
_standalone_engine: Optional[SolanaRevenueEngine] = None


def _get_standalone_engine() -> SolanaRevenueEngine:
    """Lazy-init the engine for standalone (non-hub) deployment."""
    global _standalone_engine
    if _standalone_engine is None:
        _standalone_engine = SolanaRevenueEngine(
            get_db=lambda: (_ for _ in ()).throw(
                RuntimeError("Standalone mode — use hub for DB access")
            ),
            supabase_url=os.environ.get("SUPABASE_URL", ""),
            supabase_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            solana_rpc_url=os.environ.get(
                "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
            ),
            empire_vault_wallet=os.environ.get("EMPIRE_VAULT_WALLET", ""),
        )
        log.info(
            "[solana.revenue] Standalone engine initialized "
            f"(vault={_standalone_engine.vault_wallet[:8]}...)"
        )
    return _standalone_engine


@app.get("/health")
async def health():
    """Health check for the standalone service."""
    engine = _get_standalone_engine()
    return {
        "status": "operational",
        "vault": engine.vault_wallet[:8] + "..." if engine.vault_wallet else "not configured",
        "transactions_verified": engine.stats["transactions_verified"],
        "total_usdc_logged": engine.stats["total_usdc_logged"],
    }


@app.post(
    "/api/v1/payments/verify-usdc",
    status_code=status.HTTP_201_CREATED,
    summary="Verify and log an on-chain USDC payment",
    description=(
        "Queries the Solana blockchain for a given transaction signature, "
        "validates it contains a USDC transfer to the Empire vault wallet, "
        "and logs the verified amount to the empire_revenue_ledger table."
    ),
)
async def process_incoming_onchain_payment(payload: TxnPayload):
    """Production gateway endpoint to verify USDC transfers.

    Accepts a transaction signature and optional campaign memo ID,
    queries the live Solana RPC node, parses the token balances,
    and commits the verified record to Supabase.
    """
    engine = _get_standalone_engine()
    result = await engine.verify_and_log_payment(
        signature_hash=payload.signature_hash,
        campaign_memo_id=payload.campaign_memo_id,
    )
    return result


@app.get("/api/v1/payments/stats")
async def payment_stats():
    """Return current engine statistics."""
    engine = _get_standalone_engine()
    return engine.stats


# ── Hub Registration Function ────────────────────────────────────

def register_solana_routes(
    app: FastAPI,
    engine: SolanaRevenueEngine,
    require_auth: Optional[Callable] = None,
):
    """Register the payment verification routes on the hub FastAPI app.

    Usage in hub.py:
        from workers.solana_payment_engine import SolanaRevenueEngine, register_solana_routes

        solana_revenue_engine = SolanaRevenueEngine(
            get_db=get_db,
            solana_rpc_url=SOLANA_RPC_URL,
            empire_vault_wallet=EMPIRE_VAULT_WALLET,
        )
        register_solana_routes(app, engine=solana_revenue_engine, require_auth=require_auth)
    """
    # Use require_auth if provided, otherwise no auth (public endpoint)
    _dep = Depends(require_auth) if require_auth else None

    route_auth = {"dependencies": [_dep]} if _dep else {}

    @app.post(
        "/api/v1/payments/verify-usdc",
        status_code=status.HTTP_201_CREATED,
        **route_auth,
    )
    async def hub_verify_usdc(payload: TxnPayload):
        """Verify an on-chain USDC payment via the hub.

        Same logic as the standalone endpoint but uses the hub's engine
        instance (which has DB access via get_db).
        """
        result = await engine.verify_and_log_payment(
            signature_hash=payload.signature_hash,
            campaign_memo_id=payload.campaign_memo_id,
        )
        return result

    @app.get("/api/v1/payments/stats", **route_auth)
    async def hub_payment_stats():
        """Return current Solana revenue engine statistics."""
        return engine.stats

    log.info("[solana.revenue] Routes registered on hub: /api/v1/payments/{verify-usdc,stats}")
