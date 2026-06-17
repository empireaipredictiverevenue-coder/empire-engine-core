"""
EMPIRE V49 · CRYPTO PAYMENTS ENGINE
=====================================
Self-hosted Solana USDC payment processing for product subscriptions.

FLOW
----
  1. User clicks "Buy" on pricing page → POST /api/v1/crypto/pay
  2. Engine creates a payment request with exact USDC amount + unique memo
  3. Returns: {payment_id, vault_wallet, amount_usdc, memo, instructions}
  4. User sends exact USDC + memo from their wallet to the vault
  5. Helius webhook fires → engine.match_payment() matches by memo first
  6. Engine activates subscription via SuiteGuard / direct DB
  7. Payment request transitions: pending → activation_pending → completed

MEMO MATCHING (the safe path)
-----------------------------
Every payment request generates a unique memo (EMP-XXXXXX). The user
must include this memo in their Solana transaction. The webhook handler
matches by exact memo first, falling back to sender+amount proximity
only for backward compatibility with payments that lack a memo.

STATE MACHINE
-------------
  pending ──(payment detected)──→ activation_pending ──(success)──→ completed
                                                      ──(failure)──→ activation_failed

The activation_pending state prevents the race where payment is marked
complete before the subscription is actually activated. If activation
fails, the request stays in activation_failed for operator review.

SUPABASE TABLE: crypto_payment_requests (migration 046)

ROUTES
------
  POST /api/v1/crypto/pay           — create payment request for a product
  GET  /api/v1/crypto/pay/{id}       — check payment status
  POST /api/v1/crypto/pay/{id}/check — force-check a payment request (operator)
"""

import asyncio
import logging
import os
import secrets
import uuid
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

from fastapi import FastAPI, HTTPException, Depends, Query

log = logging.getLogger("empire.crypto_payments")


# ── TIER → PRICE MAPPING (fallback if product_metadata unavailable) ──
TIER_PRICES_USDC = {
    # Suite Products (from pricing page)
    "ROUTER_SaaS":             499.00,
    "DATA_ENTERPRISE":         799.00,
    "SPY_DATA":               1499.00,
    "ALL_ACCESS":             2499.00,
    # Advanced Products
    "OMNI_BRIDGE":             999.00,
    "AGENT_ORCHESTRATOR":     1999.00,
    "B2B_PRO":                2999.00,
    # Strike Packs
    "STRIKE_STANDARD":         499.00,
    "STRIKE_COMBO":            999.00,
    "STRIKE_WHALE":           2999.00,
    "STRIKE_ENTERPRISE":      7999.00,
    # SEO products
    "SEO_STARTER":             299.00,
    "SEO_GROWTH":              599.00,
    "SEO_PRO":                1199.00,
    # Standalone products
    "LEADSCORE_STARTER":       199.00,
    "LEADSCORE_GROWTH":        499.00,
    "LEADSCORE_ENTERPRISE":   1499.00,
    "COMPLIANT_STARTER":       299.00,
    "COMPLIANT_GROWTH":        699.00,
    "COMPLIANT_ENTERPRISE":   1999.00,
    "STRIKE_STARTER":          399.00,
    "STRIKE_GROWTH":           899.00,
    "FORECAST_LITE":           199.00,
    "FORECAST_PRO":            499.00,
    "FORECAST_ENTERPRISE":    1499.00,
    "MARKET_EYE_STARTER":      399.00,
    "MARKET_EYE_GROWTH":       999.00,
    "MARKET_EYE_ENTERPRISE":  2999.00,
    "CONTENT_PULSE_STARTER":   199.00,
    "CONTENT_PULSE_GROWTH":    499.00,
    "CONTENT_PULSE_ENTERPRISE": 1499.00,
    "CONTRACTOR_EXCHANGE_STARTER": 199.00,
    "CONTRACTOR_EXCHANGE_GROWTH":  499.00,
    "CONTRACTOR_EXCHANGE_ENTERPRISE": 1999.00,
    "HEXSTRIKE_STARTER":       299.00,
    "HEXSTRIKE_GROWTH":        799.00,
    "HEXSTRIKE_ENTERPRISE":   2499.00,
    "ANALYZER_LITE":           199.00,
    "ANALYZER_GROWTH":         499.00,
    "ANALYZER_ENTERPRISE":    1499.00,
}


# ── RATE LIMITING ───────────────────────────────────────────────────
# In-memory IP-based rate limiter for POST /api/v1/crypto/pay.
# 3 requests per IP per hour. Cleaned periodically on access.
_RATE_LIMIT_BUCKET: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 3
_RATE_LIMIT_WINDOW_SEC = 3600


def _check_rate_limit(ip: str) -> bool:
    """Return True if the IP is allowed to create another payment request."""
    now = _time.time()
    timestamps = _RATE_LIMIT_BUCKET.get(ip, [])
    # Prune expired entries
    timestamps = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW_SEC]
    _RATE_LIMIT_BUCKET[ip] = timestamps
    return len(timestamps) < _RATE_LIMIT_MAX


def _record_rate_limit(ip: str):
    """Record a request from this IP."""
    now = _time.time()
    if ip not in _RATE_LIMIT_BUCKET:
        _RATE_LIMIT_BUCKET[ip] = []
    _RATE_LIMIT_BUCKET[ip].append(now)
    # Periodic cleanup of stale entries to prevent memory leak
    if len(_RATE_LIMIT_BUCKET) > 500:
        cutoff = now - _RATE_LIMIT_WINDOW_SEC
        stale = [k for k, v in _RATE_LIMIT_BUCKET.items() if all(t < cutoff for t in v)]
        for k in stale:
            del _RATE_LIMIT_BUCKET[k]


def _generate_memo() -> str:
    """Generate a unique payment memo: EMP-XXXXXX (6 uppercase alphanumeric chars)."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 to avoid confusion
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"EMP-{suffix}"


class CryptoPaymentEngine:
    """
    Self-hosted Solana USDC payment engine.

    Manages the full lifecycle: payment request creation → user sends
    USDC → Helius webhook match → subscription activation.

    Fail-fast: raises RuntimeError if vault_wallet is empty.
    """

    def __init__(
        self,
        *,
        get_db: Callable,
        vault_wallet: str = "",
        subscription_engine=None,
        guard=None,
        broadcaster=None,
    ):
        if not vault_wallet or not vault_wallet.strip():
            raise RuntimeError(
                "CryptoPaymentEngine requires EMPIRE_VAULT_WALLET to be set. "
                "Crypto payments cannot operate without a vault wallet address."
            )
        self._get_db = get_db
        self.vault_wallet = vault_wallet
        self.subscription_engine = subscription_engine
        self.guard = guard
        self.broadcaster = broadcaster

        # In-memory counters (hot-path convenience; may reset on restart).
        # Use get_db_stats() for durable, DB-backed numbers.
        self.stats = {
            "requests_created": 0,
            "payments_matched": 0,
            "subscriptions_activated": 0,
            "errors": 0,
        }

    # ── PUBLIC API ──────────────────────────────────────────────────

    async def create_payment_request(
        self,
        *,
        customer_email: str,
        customer_account_id: str,
        tier_level: str,
        product_slug: str = "",
        created_by: str = "self-serve",
    ) -> dict:
        """
        Create a payment request for a product subscription.

        Generates a unique memo (EMP-XXXXXX) that the user must include
        in their Solana transaction for reliable matching.

        Looks up the price from product_metadata first, then falls back
        to TIER_PRICES_USDC. Returns the payment request details
        including the vault wallet address, exact USDC amount, and memo.
        """
        tier = tier_level.strip()
        product = product_slug.strip().lower() if product_slug else ""

        # Look up price
        amount = await self._lookup_price(tier, product)
        if amount is None:
            return {
                "ok": False,
                "error": f"Unknown tier '{tier_level}'. Available: {', '.join(sorted(TIER_PRICES_USDC.keys()))}",
            }

        # Generate unique memo for this payment
        memo = _generate_memo()

        # Create the payment request record
        try:
            db = self._get_db()
            request_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

            db.table("crypto_payment_requests").insert({
                "id": request_id,
                "customer_email": customer_email.strip(),
                "customer_account_id": customer_account_id.strip(),
                "product_slug": product,
                "tier_level": tier,
                "amount_usdc": amount,
                "status": "pending",
                "memo": memo,
                "created_by": created_by,
                "created_at": now,
                "updated_at": now,
                "expires_at": expires,
            }).execute()

            self.stats["requests_created"] += 1

            log.info(
                f"[crypto] payment request {request_id[:8]}... created: "
                f"{customer_email} · {tier} · ${amount:.2f} USDC · memo={memo}"
            )

            return {
                "ok": True,
                "payment_id": request_id,
                "vault_wallet": self.vault_wallet,
                "amount_usdc": amount,
                "memo": memo,
                "tier_level": tier,
                "product_slug": product,
                "customer_email": customer_email,
                "expires_at": expires,
                "status_url": f"/api/v1/crypto/pay/{request_id}",
                "instructions": (
                    f"Send exactly ${amount:.2f} USDC (Solana) to "
                    f"{self.vault_wallet}. "
                    f"IMPORTANT: Include memo \"{memo}\" in your transaction. "
                    f"Your subscription will activate automatically once "
                    f"the payment is confirmed."
                ),
            }
        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[crypto] create_payment_request error: {e}")
            return {"ok": False, "error": str(e)[:200]}

    def get_payment_status(self, payment_id: str) -> dict:
        """
        Check the status of a payment request.

        Also auto-expires stale pending requests older than 24h.
        """
        try:
            db = self._get_db()
            r = db.table("crypto_payment_requests") \
                .select("*") \
                .eq("id", payment_id) \
                .limit(1) \
                .execute()
            if not r.data:
                return {"ok": False, "error": "Payment request not found"}

            req = r.data[0]

            # Auto-expire if stale
            if req.get("status") == "pending":
                expires = req.get("expires_at")
                if expires:
                    try:
                        exp = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                        if datetime.now(timezone.utc) > exp:
                            db.table("crypto_payment_requests") \
                                .update({"status": "expired", "updated_at": datetime.now(timezone.utc).isoformat()}) \
                                .eq("id", payment_id) \
                                .execute()
                            req["status"] = "expired"
                    except (ValueError, TypeError):
                        pass

            return {
                "ok": True,
                "payment_id": req["id"],
                "status": req["status"],
                "amount_usdc": float(req.get("amount_usdc", 0)),
                "paid_amount_usdc": float(req["paid_amount_usdc"]) if req.get("paid_amount_usdc") else None,
                "memo": req.get("memo", ""),
                "tier_level": req["tier_level"],
                "product_slug": req.get("product_slug", ""),
                "customer_email": req["customer_email"],
                "transaction_signature": req.get("transaction_signature"),
                "created_at": req.get("created_at"),
                "expires_at": req.get("expires_at"),
                "paid_at": req.get("paid_at"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def list_pending_requests(self, limit: int = 50) -> list:
        """Return pending payment requests, oldest first."""
        try:
            db = self._get_db()
            r = db.table("crypto_payment_requests") \
                .select("*") \
                .eq("status", "pending") \
                .order("created_at", desc=False) \
                .limit(limit) \
                .execute()
            return r.data or []
        except Exception as e:
            log.warning(f"[crypto] list_pending error: {e}")
            return []

    def list_activation_failed(self, limit: int = 20) -> list:
        """Return activation_failed payments, newest first, for operator review."""
        try:
            db = self._get_db()
            r = db.table("crypto_payment_requests") \
                .select("*") \
                .eq("status", "activation_failed") \
                .order("updated_at", desc=True) \
                .limit(limit) \
                .execute()
            return r.data or []
        except Exception as e:
            log.warning(f"[crypto] list_activation_failed error: {e}")
            return []

    def get_db_stats(self) -> dict:
        """
        Return DB-backed stats (COUNT queries by status).
        These survive restarts and horizontal scale-out.
        """
        try:
            db = self._get_db()
            counts = {}
            for status in ("pending", "activation_pending", "completed",
                           "expired", "activation_failed"):
                r = db.table("crypto_payment_requests") \
                    .select("id", count="exact") \
                    .eq("status", status) \
                    .execute()
                counts[status] = r.count if r.count is not None else 0
            return {
                "pending": counts.get("pending", 0),
                "activation_pending": counts.get("activation_pending", 0),
                "completed": counts.get("completed", 0),
                "expired": counts.get("expired", 0),
                "activation_failed": counts.get("activation_failed", 0),
            }
        except Exception as e:
            log.warning(f"[crypto] get_db_stats error: {e}")
            return {}

    # ── PAYMENT MATCHING (called by Helius webhook) ────────────────

    async def match_payment(
        self,
        *,
        sender_address: str,
        amount_usdc: float,
        tx_signature: str,
        memo: str = "",
    ) -> dict:
        """
        Match an incoming USDC payment to a pending payment request.

        Called by the Helius webhook handler when USDC arrives at the
        vault. Matching priority:
          1. Exact memo match (EMP-XXXXXX) — the safe, unambiguous path
          2. Sender address match (same wallet that paid before)
          3. Amount proximity fallback (within $0.50, backward compat)

        State transitions:
          pending → activation_pending (payment detected atomically)
          activation_pending → completed (activation succeeded)
          activation_pending → activation_failed (activation failed)

        Returns {matched: True/False, claimed: True/False, ...}.
        `claimed` is True when this engine successfully consumed the
        payment — the caller should NOT route it to other engines.
        """
        try:
            db = self._get_db()
            cleaned_memo = (memo or "").strip()

            # ── Phase 1: find the best candidate ─────────────────
            match = None

            # Strategy 1: Exact memo match (preferred, unambiguous)
            if cleaned_memo:
                r = db.table("crypto_payment_requests") \
                    .select("*") \
                    .eq("status", "pending") \
                    .eq("memo", cleaned_memo) \
                    .limit(1) \
                    .execute()
                if r.data:
                    match = r.data[0]
                    log.info(
                        f"[crypto] memo match: {cleaned_memo} → "
                        f"{match['id'][:8]}... · {match['customer_email']}"
                    )

            # Strategy 2: Sender address match (same wallet paid before)
            if not match:
                tolerance = 0.01
                lower = amount_usdc * (1 - tolerance)
                upper = amount_usdc * (1 + tolerance)

                r = db.table("crypto_payment_requests") \
                    .select("*") \
                    .eq("status", "pending") \
                    .gte("amount_usdc", lower) \
                    .lte("amount_usdc", upper) \
                    .order("created_at", desc=False) \
                    .execute()

                candidates = r.data or []
                for c in candidates:
                    existing_sender = c.get("sender_address")
                    if existing_sender and existing_sender == sender_address:
                        match = c
                        log.info(
                            f"[crypto] sender match: {sender_address[:8]}... → "
                            f"{match['id'][:8]}..."
                        )
                        break

            # Strategy 3: Amount proximity (backward compat, last resort)
            if not match and candidates:
                best = min(
                    candidates,
                    key=lambda c: abs(float(c["amount_usdc"]) - amount_usdc),
                )
                diff = abs(float(best["amount_usdc"]) - amount_usdc)
                if diff < 0.50:
                    db.table("crypto_payment_requests") \
                        .update({"sender_address": sender_address}) \
                        .eq("id", best["id"]) \
                        .execute()
                    match = best
                    log.info(
                        f"[crypto] proximity match: ${amount_usdc:.2f} → "
                        f"{match['id'][:8]}... (diff=${diff:.2f})"
                    )

            if not match:
                log.info(
                    f"[crypto] no match for {sender_address[:8]}... "
                    f"· ${amount_usdc:.2f} · memo={cleaned_memo or '(none)'}"
                )
                return {
                    "matched": False,
                    "claimed": False,
                    "reason": "no_match",
                    "candidates": len(candidates) if candidates else 0,
                }

            # ── Phase 2: Atomically claim the request ─────────────
            # Transition pending → activation_pending with status guard.
            # Only one webhook call can win this race.
            now = datetime.now(timezone.utc).isoformat()
            claim_result = db.table("crypto_payment_requests") \
                .update({
                    "status": "activation_pending",
                    "transaction_signature": tx_signature,
                    "sender_address": sender_address,
                    "paid_at": now,
                    "paid_amount_usdc": amount_usdc,
                    "memo": cleaned_memo[:500] if cleaned_memo else match.get("memo", ""),
                    "updated_at": now,
                }) \
                .eq("id", match["id"]) \
                .eq("status", "pending") \
                .execute()

            self.stats["payments_matched"] += 1

            log.info(
                f"[crypto] payment CLAIMED: {match['id'][:8]}... · "
                f"{match['customer_email']} · {match['tier_level']} · "
                f"${amount_usdc:.2f} USDC · tx={tx_signature[:16]}..."
            )

            # ── Phase 3: Activate subscription ────────────────────
            activation = await self._activate_subscription(match)

            # ── Phase 4: Finalize status ──────────────────────────
            if activation.get("ok"):
                db.table("crypto_payment_requests") \
                    .update({
                        "status": "completed",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }) \
                    .eq("id", match["id"]) \
                    .execute()
                self.stats["subscriptions_activated"] += 1
                log.info(
                    f"[crypto] activation SUCCESS: {match['id'][:8]}... · "
                    f"{match['tier_level']} · method={activation.get('method')}"
                )
            else:
                db.table("crypto_payment_requests") \
                    .update({
                        "status": "activation_failed",
                        "notes": (
                            (match.get("notes") or "") +
                            f"\nActivation failed: {activation.get('error', 'unknown')[:300]}"
                        ).strip(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }) \
                    .eq("id", match["id"]) \
                    .execute()
                activation_error = activation.get('error', 'unknown')[:200]
                log.error(
                    f"[crypto] activation FAILED: {match['id'][:8]}... · "
                    f"{match['tier_level']} · {activation_error}"
                )
                # Notify operator via ntfy (fire-and-forget so webhook returns promptly)
                asyncio.create_task(
                    self._send_activation_failed_notification(
                        match, activation_error, tx_signature,
                    )
                )

            # ── Broadcast ─────────────────────────────────────────
            if self.broadcaster:
                try:
                    await self.broadcaster.broadcast({
                        "type": "crypto_payment_completed",
                        "payment_id": match["id"],
                        "customer_email": match["customer_email"],
                        "tier_level": match["tier_level"],
                        "amount_usdc": amount_usdc,
                        "tx_signature": tx_signature,
                        "subscription_activated": activation.get("ok", False),
                    })
                except Exception:
                    pass

            return {
                "matched": True,
                "claimed": True,
                "payment_id": match["id"],
                "customer_email": match["customer_email"],
                "tier_level": match["tier_level"],
                "amount_usdc": amount_usdc,
                "tx_signature": tx_signature,
                "subscription": activation,
            }

        except Exception as e:
            self.stats["errors"] += 1
            log.error(f"[crypto] match_payment error: {e}")
            return {"matched": False, "claimed": False, "error": str(e)[:200]}

    # ── SUBSCRIPTION ACTIVATION ────────────────────────────────────

    async def _activate_subscription(self, payment_request: dict) -> dict:
        """
        Activate a product subscription after payment is confirmed.

        Uses SuiteSubscriptionEngine — which writes to Supabase exclusively.
        Single source of truth: no duplicate Supabase insert path.
        """
        customer_account_id = payment_request["customer_account_id"]
        tier_level = payment_request["tier_level"]
        monthly_mrr = float(payment_request.get("amount_usdc", 0))

        if self.subscription_engine:
            try:
                result = self.subscription_engine.create_subscription(
                    customer_account_id=customer_account_id,
                    tier_level=tier_level,
                    monthly_recurring_revenue=monthly_mrr,
                    notes=f"Activated via crypto payment (USDC). Request: {payment_request['id']}",
                )
                if result.get("ok"):
                    log.info(
                        f"[crypto] subscription activated (suite) for "
                        f"{customer_account_id} · {tier_level} · ${monthly_mrr:.2f}/mo"
                    )
                    return {"ok": True, "method": "suite_engine", **result}
                # If "already has" error, mark it as still OK
                if "already has" in (result.get("error") or "").lower():
                    log.info(
                        f"[crypto] subscription already exists for "
                        f"{customer_account_id} · {tier_level} (payment confirmed)"
                    )
                    return {"ok": True, "method": "already_exists"}
                log.warning(f"[crypto] suite engine activation failed: {result}")
                return {"ok": False, "error": result.get("error", "Subscription activation failed")[:200]}
            except Exception as e:
                log.error(f"[crypto] suite engine error: {e}")
                return {"ok": False, "error": str(e)[:200]}

        log.error("[crypto] no subscription_engine configured — cannot activate")
        return {"ok": False, "error": "No subscription engine configured"}

    # ── NOTIFICATION ──────────────────────────────────────────────

    async def _send_activation_failed_notification(
        self,
        payment_request: dict,
        activation_error: str,
        tx_signature: str,
    ) -> None:
        """
        Push an ntfy.sh notification to the operator when a crypto
        payment's subscription activation fails.

        Non-blocking — failures are silently logged.
        Requires NTFY_TOPIC to be set in the environment.
        """
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic:
            log.debug("[crypto] NTFY_TOPIC not configured — skipping activation_failed notification")
            return
        try:
            import httpx
            token = os.environ.get("NTFY_TOKEN", "").strip()
            payment_id = payment_request.get("id", "?")
            email = payment_request.get("customer_email", "?")
            tier = payment_request.get("tier_level", "?")
            amount = float(payment_request.get("amount_usdc", 0))

            title = f"USDC Activation Failed: {tier}"
            body = (
                f"Payment received but subscription activation failed.\n\n"
                f"Payment:  {payment_id[:12]}...\n"
                f"Customer: {email}\n"
                f"Tier:     {tier}\n"
                f"Amount:   ${amount:.2f} USDC\n"
                f"TX:       {tx_signature[:24]}...\n"
                f"Error:    {activation_error[:300]}"
            )

            headers = {
                "Title": title[:200],
                "Tags": "warning,skull",
                "Priority": "4",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://ntfy.sh/{topic}",
                    content=body[:1000],
                    headers=headers,
                )
            log.info(f"[crypto] ntfy alert sent: activation_failed for {email} · {tier}")
        except Exception as e:
            log.warning(f"[crypto] ntfy notification failed: {e}")

    # ── PRICE LOOKUP ───────────────────────────────────────────────

    async def _lookup_price(self, tier: str, product_slug: str) -> Optional[float]:
        """
        Look up the price for a product tier.

        Priority:
          1. If product_slug is provided: product_metadata table in
             Supabase (monthly_price_usd) — allows disambiguation
             when the same tier key maps to different products
             (e.g. STRIKE_ENTERPRISE: Strike Pack $7999 vs standalone $2999).
          2. TIER_PRICES_USDC fallback dict — used for pricing page
             CTAs which don't pass a product_slug.
        """
        if product_slug:
            try:
                db = self._get_db()
                r = db.table("product_metadata") \
                    .select("monthly_price_usd") \
                    .eq("tier", tier) \
                    .eq("product_name", product_slug) \
                    .eq("is_active", True) \
                    .limit(1) \
                    .execute()
                if r.data and r.data[0].get("monthly_price_usd"):
                    return float(r.data[0]["monthly_price_usd"])
            except Exception:
                pass

        return TIER_PRICES_USDC.get(tier)


# ── ROUTE REGISTRATION ─────────────────────────────────────────────

def _checkout_page(tier: str, price: float, vault_wallet: str) -> str:
    """Render the crypto checkout page for a product tier."""
    from empire_tokens import empire_head

    checkout_css = """
    .co-wrap { max-width: 640px; margin: 0 auto; padding: 80px 32px; }
    .co-card { background: #14141e; border: 1px solid #1e293b; padding: 40px; }
    .co-title { font-size: 28px; font-weight: 200; color: #f8fafc; margin-bottom: 8px; letter-spacing: -0.02em; }
    .co-title em { color: #44E5B8; font-style: italic; font-weight: 500; }
    .co-sub { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #94a3b8; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 32px; }
    .co-row { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid #1e293b; }
    .co-label { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; }
    .co-value { font-family: 'SF Mono','Fira Code',monospace; font-size: 14px; color: #f8fafc; }
    .co-value.usdc { color: #44E5B8; font-size: 24px; font-weight: 600; }
    .co-wallet { font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; color: #94a3b8; word-break: break-all; background: #0a0a0f; padding: 14px 16px; border: 1px solid #1e293b; margin: 12px 0; }
    .co-memo { font-family: 'SF Mono','Fira Code',monospace; font-size: 16px; color: #FFB800; word-break: break-all; background: #0a0a0f; padding: 14px 16px; border: 1px solid #FFB800; margin: 12px 0; letter-spacing: 0.12em; text-align: center; }
    .co-memo-label { font-family: 'SF Mono','Fira Code',monospace; font-size: 9px; color: #FFB800; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 4px; }
    .co-steps { list-style: none; padding: 0; margin: 24px 0; }
    .co-steps li { padding: 10px 0; border-bottom: 1px solid #1e293b; font-size: 13px; color: #cbd5e1; line-height: 1.6; display: flex; gap: 12px; }
    .co-steps li::before { content: attr(data-step); color: #44E5B8; font-weight: 600; flex-shrink: 0; width: 20px; text-align: center; }
    .co-btn { display: inline-block; padding: 14px 28px; background: #44E5B8; color: #020617; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; text-decoration: none; font-weight: 600; border: none; cursor: pointer; transition: all 0.2s; margin-top: 24px; }
    .co-btn:hover { background: #3dd4a7; }
    .co-btn.secondary { background: transparent; border: 1px solid #44E5B8; color: #44E5B8; }
    .co-btn.secondary:hover { background: rgba(68,229,184,0.1); }
    .co-form-group { margin-bottom: 20px; }
    .co-form-group label { display: block; font-family: 'SF Mono','Fira Code',monospace; font-size: 9px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }
    .co-form-group input { width: 100%; padding: 12px 14px; background: #0a0a0f; border: 1px solid #1e293b; color: #f8fafc; font-family: 'SF Mono','Fira Code',monospace; font-size: 13px; outline: none; transition: border-color 0.2s; }
    .co-form-group input:focus { border-color: #44E5B8; }
    .co-error { color: #ff6b6b; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; padding: 8px 0; }
    .co-success { color: #44E5B8; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; padding: 8px 0; }
    .co-pay-status { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #94a3b8; margin-top: 16px; padding: 12px; background: #0a0a0f; border: 1px solid #1e293b; }
    .co-pay-status a { color: #44E5B8; }
    @media (max-width: 540px) { .co-wrap { padding: 40px 16px; } .co-card { padding: 24px; } }
    """

    head = empire_head(title=f"Empire AI · Checkout {tier}", extra=checkout_css)

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
<div class="co-wrap">
  <div class="co-card">
    <div class="co-title">Subscribe to <em>{tier}</em></div>
    <div class="co-sub">Pay with USDC (Solana)</div>

    <div id="co-flow">
      <!-- Step 1: Email form -->
      <div id="co-step-email">
        <div class="co-form-group">
          <label>Your email address</label>
          <input type="email" id="co-email" placeholder="you@example.com" />
          <div id="co-email-error" class="co-error" style="display:none"></div>
        </div>
        <div class="co-form-group">
          <label>Account ID</label>
          <input type="text" id="co-account" placeholder="your_account_id" value="" />
          <div style="font-size:10px;color:#64748b;margin-top:4px;">Use your email or a stable identifier</div>
        </div>
        <button class="co-btn" onclick="createPayment()">Create Payment Request</button>
      </div>

      <!-- Step 2: Payment details (shown after request created) -->
      <div id="co-step-pay" style="display:none">
        <div class="co-row">
          <span class="co-label">Amount</span>
          <span class="co-value usdc" id="co-amount">${price:.2f} USDC</span>
        </div>
        <div class="co-row">
          <span class="co-label">Network</span>
          <span class="co-value">Solana</span>
        </div>
        <div class="co-row" style="border:none;">
          <span class="co-label">Vault Wallet</span>
        </div>
        <div class="co-wallet" id="co-wallet">{vault_wallet}</div>

        <div class="co-memo-label">Memo (required — include this in your transaction)</div>
        <div class="co-memo" id="co-memo">EMP-XXXXXX</div>

        <ol class="co-steps">
          <li data-step="1">Open your Solana wallet (Phantom, Solflare, TokenPocket, etc.)</li>
          <li data-step="2">Send exactly <strong style="color:#44E5B8;">${price:.2f} USDC</strong> to the wallet address above on <strong>Solana</strong> network</li>
          <li data-step="3"><strong style="color:#FFB800;">Include the memo shown above</strong> — this identifies your payment</li>
          <li data-step="4">Wait for blockchain confirmation (~30 seconds)</li>
          <li data-step="5">Your subscription will activate automatically — check status below</li>
        </ol>

        <div id="co-status" class="co-pay-status">
          Waiting for payment...
          <br><br>
          <span id="co-check-link"></span>
        </div>

        <button class="co-btn secondary" onclick="checkStatus()" style="margin-top:12px;">
          Refresh Status
        </button>
      </div>
    </div>

    <div id="co-result" style="display:none">
      <div class="co-title" style="font-size:20px;">Payment <em>Requested</em></div>
      <div id="co-result-body"></div>
    </div>
  </div>
</div>

<script>
let currentPaymentId = null;

function createPayment() {{
  const email = document.getElementById('co-email').value.trim();
  const accountId = document.getElementById('co-account').value.trim() || email;
  const errEl = document.getElementById('co-email-error');

  if (!email || !email.includes('@')) {{
    errEl.textContent = 'Please enter a valid email address';
    errEl.style.display = 'block';
    return;
  }}
  errEl.style.display = 'none';

  fetch('/api/v1/crypto/pay', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ customer_email: email, customer_account_id: accountId, tier_level: '{tier}' }}),
  }})
  .then(r => r.json())
  .then(data => {{
    if (data.ok) {{
      currentPaymentId = data.payment_id;
      document.getElementById('co-step-email').style.display = 'none';
      document.getElementById('co-step-pay').style.display = 'block';
      document.getElementById('co-amount').textContent = '${{data.amount_usdc.toFixed(2)}} USDC';
      document.getElementById('co-wallet').textContent = data.vault_wallet;
      document.getElementById('co-memo').textContent = data.memo;
      document.getElementById('co-check-link').innerHTML =
        '<a href="/crypto/pay/' + data.payment_id + '" target="_blank">Payment status page</a>';
      startPolling(data.payment_id);
    }} else {{
      document.getElementById('co-email-error').textContent = data.error || 'Failed to create payment request';
      document.getElementById('co-email-error').style.display = 'block';
    }}
  }})
  .catch(err => {{
    document.getElementById('co-email-error').textContent = 'Network error: ' + err.message;
    document.getElementById('co-email-error').style.display = 'block';
  }});
}}

function checkStatus() {{
  if (!currentPaymentId) return;
  fetch('/api/v1/crypto/pay/' + currentPaymentId)
    .then(r => r.json())
    .then(data => {{
      const el = document.getElementById('co-status');
      if (data.status === 'completed') {{
        el.innerHTML = '<span style="color:#44E5B8;font-size:16px;">✅ Payment confirmed! Your subscription is active.</span>';
      }} else if (data.status === 'activation_pending') {{
        el.innerHTML = '<span style="color:#FFB800;">⚡ Payment received! Activating your subscription...</span>';
      }} else if (data.status === 'expired') {{
        el.innerHTML = '<span style="color:#ff6b6b;">⏰ Payment request expired. Please create a new one.</span>';
      }} else {{
        el.innerHTML = '⏳ Waiting for payment... <br>Send exactly <strong>${{data.amount_usdc.toFixed(2)}} USDC</strong> with memo <strong>{{data.memo}}</strong>.';
      }}
    }});
}}

function startPolling(paymentId) {{
  setInterval(() => {{
    if (paymentId) checkStatus();
  }}, 10000);
}}
</script>
</body>
</html>"""


def register_crypto_payment_routes(
    app: FastAPI,
    *,
    engine: CryptoPaymentEngine,
    require_auth: Callable = None,
    public_base_url: str = "http://localhost:8000",
):
    """
    Wire crypto payment endpoints into the FastAPI app.

    GET  /crypto/checkout/{tier}   — public checkout page (rendered HTML)
    POST /api/v1/crypto/pay        — create a payment request (rate-limited, public)
    GET  /api/v1/crypto/pay/{id}   — check payment status (public)
    GET  /api/v1/crypto/stats      — engine stats (operator)
    GET  /crypto/pay/{id}          — rendered payment status page
    """
    from fastapi import Request
    from fastapi.responses import HTMLResponse

    @app.get("/crypto/checkout/{tier}", response_class=HTMLResponse)
    async def crypto_checkout_page(tier: str):
        """
        Public checkout page for subscribing via USDC.
        Shows the vault wallet address, amount, memo, and instructions.
        """
        t = tier.strip()
        price = await engine._lookup_price(t, "")
        if price is None:
            raise HTTPException(404, f"Unknown tier: {tier}")
        return HTMLResponse(_checkout_page(
            tier=t,
            price=price,
            vault_wallet=engine.vault_wallet,
        ))

    @app.get("/crypto/pay/{payment_id}", response_class=HTMLResponse)
    async def crypto_payment_status_page(payment_id: str):
        """Rendered payment status page for user-friendly viewing."""
        result = engine.get_payment_status(payment_id)
        if not result.get("ok"):
            raise HTTPException(404, "Payment request not found")

        status = result["status"]
        if status == "completed":
            icon = "✅"
            msg = "Payment confirmed! Your subscription is active."
            color = "#44E5B8"
        elif status == "activation_pending":
            icon = "⚡"
            msg = "Payment received! Activating your subscription..."
            color = "#FFB800"
        elif status == "activation_failed":
            icon = "⚠️"
            msg = "Payment received but activation failed. Our team has been notified and will resolve this shortly."
            color = "#FF6B6B"
        elif status == "pending":
            icon = "⏳"
            msg = f"Waiting for payment... Send exactly ${result['amount_usdc']:.2f} USDC with memo {result.get('memo', '?')}."
            color = "#FFB800"
        elif status == "expired":
            icon = "⏰"
            msg = "Payment request has expired. Please create a new one."
            color = "#FF6B6B"
        else:
            icon = "❌"
            msg = f"Status: {status}"
            color = "#FF6B6B"

        from empire_tokens import empire_head
        status_css = """
        .ps-wrap { max-width: 480px; margin: 0 auto; padding: 80px 32px; }
        .ps-card { background: #14141e; border: 1px solid #1e293b; padding: 40px; text-align: center; }
        .ps-icon { font-size: 48px; margin-bottom: 16px; }
        .ps-status { font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 12px; }
        .ps-msg { font-size: 14px; color: #cbd5e1; line-height: 1.6; margin-bottom: 24px; }
        .ps-detail { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #64748b; line-height: 1.8; }
        .ps-detail strong { color: #94a3b8; }
        .ps-btn { display: inline-block; padding: 12px 24px; border: 1px solid #44E5B8; color: #44E5B8; font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; text-decoration: none; transition: all 0.2s; margin-top: 20px; }
        .ps-btn:hover { background: rgba(68,229,184,0.1); }
        """
        head = empire_head(title=f"Empire AI · Payment {status}", extra=status_css)

        return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
<div class="ps-wrap">
  <div class="ps-card">
    <div class="ps-icon">{icon}</div>
    <div class="ps-status" style="color:{color}">{status.upper()}</div>
    <div class="ps-msg">{msg}</div>
    <div class="ps-detail">
      <strong>Tier:</strong> {result['tier_level']}<br>
      <strong>Amount:</strong> ${result['amount_usdc']:.2f} USDC<br>
      <strong>Memo:</strong> {result.get('memo', '?')}<br>
      <strong>Payment ID:</strong> {payment_id[:12]}...<br>
      {"<strong>TX:</strong> " + result['transaction_signature'][:20] + "...<br>" if result.get('transaction_signature') else ""}
    </div>
    <a href="/pricing" class="ps-btn">Back to Pricing</a>
  </div>
</div>
</body>
</html>"""

    @app.post("/api/v1/crypto/pay")
    async def crypto_create_payment(request: Request):
        """
        Create a crypto payment request for a product subscription.

        Rate-limited: 3 requests per IP per hour.
        Public endpoint — no auth required (anyone can buy).

        Body:
          customer_email: str       — buyer's email
          customer_account_id: str  — stable account identifier
          tier_level: str           — product tier (e.g. "ROUTER_SaaS", "ALL_ACCESS")
          product_slug: str (opt)   — product identifier
        """
        # ── Rate limiting ──────────────────────────────────────────
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        if not _check_rate_limit(client_ip):
            raise HTTPException(429, "Too many payment requests. Please wait before trying again.")
        _record_rate_limit(client_ip)

        try:
            body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        email = (body.get("customer_email") or "").strip()
        account_id = (body.get("customer_account_id") or "").strip()
        tier = (body.get("tier_level") or "").strip()
        product = (body.get("product_slug") or "").strip()

        if not email or not account_id or not tier:
            raise HTTPException(400, "customer_email, customer_account_id, and tier_level are required")

        if "@" not in email:
            raise HTTPException(400, "Invalid email address")

        result = await engine.create_payment_request(
            customer_email=email,
            customer_account_id=account_id,
            tier_level=tier,
            product_slug=product,
        )

        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "Failed to create payment request"))

        return result

    @app.get("/api/v1/crypto/pay/{payment_id}")
    async def crypto_payment_status(payment_id: str):
        """
        Check the status of a payment request.

        Public endpoint — no auth required so users can check
        their own payment status via the status_url.
        """
        result = engine.get_payment_status(payment_id)
        if not result.get("ok"):
            raise HTTPException(404, result.get("error", "Payment request not found"))
        return result

    @app.get("/api/v1/crypto/stats")
    async def crypto_stats(auth: bool = Depends(require_auth) if require_auth else None):
        """Return engine statistics for operator dashboard."""
        db_stats = engine.get_db_stats()
        pending = engine.list_pending_requests(limit=5)
        failed = engine.list_activation_failed(limit=20)
        return {
            "stats": dict(engine.stats),
            "db_stats": db_stats,
            "vault_wallet": engine.vault_wallet[:8] + "..." if engine.vault_wallet else "(not configured)",
            "recent_pending": [
                {
                    "id": p["id"][:8],
                    "email": p["customer_email"],
                    "tier": p["tier_level"],
                    "amount": float(p["amount_usdc"]),
                    "memo": p.get("memo", ""),
                    "created": p.get("created_at"),
                }
                for p in pending
            ],
            "pending_count": len(pending),
            "activation_failed": [
                {
                    "id": f["id"],
                    "email": f["customer_email"],
                    "tier": f["tier_level"],
                    "amount": float(f["amount_usdc"]),
                    "tx": (f.get("transaction_signature") or "")[:20],
                    "notes": (f.get("notes") or "")[:200],
                    "failed_at": f.get("updated_at"),
                }
                for f in failed
            ],
        }

    log.info("[crypto-payments] Routes registered · /api/v1/crypto/*")
