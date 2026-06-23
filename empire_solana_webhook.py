"""
EMPIRE V49 · SOLANA WEBHOOK (Helius)
======================================
Receives Helius enhanced-transaction webhooks when USDC arrives at the
Empire vault wallet and routes them to the PayoutEngine.

Helius sends POST requests to /api/v1/webhooks/solana with an array of
enhanced transaction objects. This handler:

  1. Validates the request via HELIUS_WEBHOOK_SECRET (header or query)
  2. For each transaction, checks if it contains USDC token transfers
     to the vault wallet
  3. Calls payout_engine.on_settlement_detected() for each matching
     transfer
  4. Logs verified payments to empire_revenue_ledger
  5. Broadcasts via live_broadcaster for real-time dashboards

WEBHOOK SETUP IN HELIUS
───────────────────────
  1. Go to https://dashboard.helius.dev/webhooks
  2. Create a new webhook with:
     - Webhook URL: https://empire-ai.co.uk/api/v1/webhooks/solana
     - Transaction type: Enhanced (token transfers)
     - Account: <your vault wallet address>
     - Webhook header: Authorization: Bearer <HELIUS_WEBHOOK_SECRET>
  3. Save and verify with a test USDC transfer

Returns 200 with {ok: true, processed: N} on success.
Returns 401 on auth failure, 400 on bad payload.
"""

import os
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException

log = logging.getLogger("empire.solana_webhook")


# ── USDC MINT (configurable via EMPIRE_USDC_MINT env var) ───────────
# Defaults to mainnet USDC mint. Override with EMPIRE_USDC_MINT env var
# for devnet testing (4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU).
_DEFAULT_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


# ─────────────────────────────────────────────────────────────────────
# WEBHOOK HANDLER
# ─────────────────────────────────────────────────────────────────────
def register_solana_webhook_routes(
    app: FastAPI,
    *,
    payout_engine,
    vault_wallet: str,
    get_db,
    broadcaster=None,
    crypto_payment_engine=None,
):
    """
    Wire the Helius webhook endpoint and a health-check GET route.

    Args:
        payout_engine: PayoutEngine instance (for on_settlement_detected)
        vault_wallet:  The vault wallet address to filter incoming USDC for
        get_db:        Callable returning a Supabase client
        broadcaster:   Optional LiveBroadcaster for real-time dashboards
        crypto_payment_engine: Optional CryptoPaymentEngine for self-hosted
                               USDC checkout → subscription activation
    """

    # Resolve the USDC mint from env var (allows devnet testing)
    usdc_mint = os.environ.get("EMPIRE_USDC_MINT", _DEFAULT_USDC_MINT)

    # ── Public webhook endpoint (no auth — validated via HELIUS_WEBHOOK_SECRET) ──
    @app.post("/api/v1/webhooks/solana")
    async def solana_webhook(request: Request):
        """
        Receive Helius enhanced-transaction webhook.

        Validates via HELIUS_WEBHOOK_SECRET (sent as Authorization:
        Bearer <secret> by Helius config).

        Body: array of enhanced transaction objects.
        """
        webhook_secret = os.environ.get("HELIUS_WEBHOOK_SECRET", "")
        if webhook_secret:
            # Validate via Authorization header
            auth_header = request.headers.get("Authorization", "")
            expected = f"Bearer {webhook_secret}"

            # Also allow passing as ?secret= query param for testing
            query_secret = request.query_params.get("secret", "")
            if query_secret and query_secret == webhook_secret:
                log.warning(
                    "[solana-webhook] query-param auth used (less secure) — "
                    "use Authorization header in production"
                )

            if auth_header != expected and query_secret != webhook_secret:
                log.warning(
                    f"[solana-webhook] auth failed: "
                    f"header={auth_header[:20] if auth_header else '(none)'}"
                )
                raise HTTPException(401, "Invalid webhook secret")

        # Parse body
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        if not isinstance(body, list):
            raise HTTPException(400, "Expected array of transactions")

        # Process transactions
        processed = 0
        skipped = 0
        errors = 0

        for tx in body:
            if not isinstance(tx, dict):
                skipped += 1
                continue

            tx_sig = tx.get("signature", "")
            if not tx_sig:
                skipped += 1
                continue

            # Check for USDC token transfers to our vault
            token_transfers = tx.get("tokenTransfers") or []
            if not token_transfers:
                skipped += 1
                continue

            vault_matches = []
            for transfer in token_transfers:
                mint = transfer.get("mint", "")
                to_addr = transfer.get("toUserAccount", "")

                # Filter: must be USDC mint and going to our vault wallet
                if mint != usdc_mint:
                    continue
                if to_addr != vault_wallet:
                    continue

                amount = float(transfer.get("tokenAmount", 0))
                if amount <= 0:
                    continue

                vault_matches.append({
                    "from": transfer.get("fromUserAccount", ""),
                    "amount": amount,
                    "memo": tx.get("description", ""),
                })

            if not vault_matches:
                skipped += 1
                continue

            # Log to revenue ledger
            timestamp = tx.get("timestamp")
            if timestamp:
                try:
                    block_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except Exception:
                    block_time = datetime.now(timezone.utc)
            else:
                block_time = datetime.now(timezone.utc)

            try:
                db = get_db()

                for match in vault_matches:
                    # Insert revenue ledger row
                    db.table("empire_revenue_ledger").upsert({
                        "status": "settled",
                        "transaction_signature": tx_sig,
                        "sender_address": match["from"],
                        "destination_address": vault_wallet,
                        "usdc_amount": match["amount"],
                        "tracking_memo": match["memo"][:500] if match["memo"] else "",
                        "block_time_stamp": block_time.isoformat(),
                        "meta": {
                            "slot": tx.get("slot"),
                            "fee": tx.get("fee"),
                            "type": tx.get("type", ""),
                            "source": "helius_webhook",
                        },
                    }, on_conflict="transaction_signature").execute()

                # ── Route each vault match to the correct engine ────
                # Crypto engine claims subscription payments (by memo).
                # Payout engine handles settlement fee splits.
                # They are mutually exclusive: if crypto claims it,
                # we skip the payout engine for that transfer.
                for match in vault_matches:
                    # Try crypto matching first
                    claimed_by_crypto = False
                    if crypto_payment_engine:
                        try:
                            pmt = await crypto_payment_engine.match_payment(
                                sender_address=match["from"],
                                amount_usdc=match["amount"],
                                tx_signature=tx_sig,
                                memo=match.get("memo", ""),
                            )
                            if pmt.get("claimed"):
                                claimed_by_crypto = True
                                log.info(
                                    f"[solana-webhook] crypto claimed: "
                                    f"{pmt.get('payment_id', '?')[:8]}... · "
                                    f"${match['amount']:.2f} USDC"
                                )
                            elif pmt.get("matched"):
                                log.info(
                                    f"[solana-webhook] crypto matched: "
                                    f"{pmt.get('payment_id', '?')[:8]}... · "
                                    f"${match['amount']:.2f} USDC"
                                )
                        except Exception as e:
                            log.warning(
                                f"[solana-webhook] crypto match error: {e}"
                            )

                    # Only route to payout engine if crypto didn't claim it
                    if not claimed_by_crypto:
                        try:
                            await payout_engine.on_settlement_detected(
                                amount_usdc=match["amount"],
                                tx_signature=tx_sig,
                                memo=match.get("memo", ""),
                            )
                        except Exception as e:
                            log.error(
                                f"[solana-webhook] payout_engine failed for "
                                f"{tx_sig[:16]}...: {e}"
                            )
                            errors += 1

                processed += len(vault_matches)

                # Broadcast to live dashboards
                if broadcaster:
                    try:
                        for match in vault_matches:
                            await broadcaster.broadcast({
                                "type": "solana_payment_received",
                                "tx_signature": tx_sig,
                                "amount_usdc": match["amount"],
                                "from": match["from"][:8] + "...",
                                "block_time": block_time.isoformat(),
                            })
                    except Exception:
                        pass

                log.info(
                    f"[solana-webhook] processed {len(vault_matches)} USDC "
                    f"payments · tx={tx_sig[:16]}... · "
                    f"total=${sum(m['amount'] for m in vault_matches):.2f}"
                )

            except Exception as e:
                log.error(f"[solana-webhook] DB/payout error for {tx_sig[:16]}...: {e}")
                errors += 1

        return {
            "ok": True,
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
        }

    # ── Health/status endpoint ─────────────────────────────────────
    @app.get("/api/v1/webhooks/solana/status")
    async def solana_webhook_status():
        """Return webhook configuration status for operator review."""
        has_secret = bool(os.environ.get("HELIUS_WEBHOOK_SECRET", ""))
        vault = vault_wallet or "(not configured)"
        crypto_enabled = crypto_payment_engine is not None
        return {
            "webhook": "/api/v1/webhooks/solana",
            "vault_wallet": vault[:8] + "..." if len(vault) > 20 else vault,
            "usdc_mint": usdc_mint,
            "helius_secret_configured": has_secret,
            "payout_engine_enabled": getattr(payout_engine, "execution_enabled", False),
            "crypto_payment_engine": crypto_enabled,
        }

    log.info("[solana-webhook] Routes registered · /api/v1/webhooks/{solana, solana/status}")
