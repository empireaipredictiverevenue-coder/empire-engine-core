"""
EMPIRE V49 · MOONPAY CARD CHECKOUT
=====================================
Separate checkout page for card-to-USDC payments via MoonPay.

HOW IT WORKS
-------------
1. User visits /checkout-card/{tier}
2. Enters email → creates payment request → gets unique memo + payment ID
3. "Pay with Card" button opens MoonPay widget (USDC sent to vault wallet)
4. MoonPay sends USDC → Helius webhook detects it → match_payment() matches
   by memo or amount proximity → subscription activates automatically
5. MoonPay webhook at /api/v1/moonpay/webhook also receives transaction_updated
   events and proactively calls match_payment() for faster activation
6. "Pay with Crypto" tab shows the manual USDC transfer option (fallback)

BACKEND INFRASTRUCTURE
-----------------------
The CryptoPaymentEngine + Helius webhook handle on-chain USDC matching.
The MoonPay webhook provides an additional faster path by signing the
payment match before the on-chain confirmation completes. Both paths use
the same match_payment() method for idempotent subscription activation.

SETUP
-----
Set in /root/.env:
  MOONPAY_PUBLIC_KEY=pk_live_xxx   — MoonPay public key (exposed to frontend)
  MOONPAY_SECRET_KEY=sk_live_xxx   — MoonPay secret key (server-side)
  MOONPAY_WEBHOOK_SECRET=xxx       — MoonPay webhook signing secret
  EMPIRE_VAULT_WALLET=<address>    — Solana vault wallet (required!)

Without these keys, the page still renders with "Pay with Crypto" only
and shows setup instructions.
"""

import os
import hmac
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse

log = logging.getLogger("empire.moonpay")


# ── MOONPAY CONFIG (from env) ────────────────────────────────────────
MOONPAY_PUBLIC_KEY = os.environ.get("MOONPAY_PUBLIC_KEY", "").strip()
MOONPAY_SECRET_KEY = os.environ.get("MOONPAY_SECRET_KEY", "").strip()
MOONPAY_WEBHOOK_SECRET = os.environ.get("MOONPAY_WEBHOOK_SECRET", "").strip()
_has_moonpay = bool(MOONPAY_PUBLIC_KEY and MOONPAY_SECRET_KEY)


# ── PRICE LOOKUP (imported from empire_crypto_payments to avoid duplication) ─
from empire_crypto_payments import TIER_PRICES_USDC


def _lookup_price(tier: str) -> Optional[float]:
    """Look up price by tier key."""
    return TIER_PRICES_USDC.get(tier.strip())


# ── CHECKOUT PAGE HTML ────────────────────────────────────────────────

def _checkout_page_html(tier: str, price: float, vault_wallet: str) -> str:
    """Render the standalone card checkout page."""
    from empire_tokens import empire_head

    moonpay_button_html = ""
    if _has_moonpay:
        moonpay_url = (
            f"https://buy.moonpay.com?apiKey={MOONPAY_PUBLIC_KEY}"
            f"&currencyCode=usdc&walletAddress={vault_wallet}"
            f"&baseCurrencyCode=usd&baseCurrencyAmount={price}"
        )
        moonpay_button_html = f"""
      <div class="co-panel" id="co-panel-card">
        <div class="co-section-title">Pay with Card</div>
        <div class="co-card-info">
          <p>Pay with your credit or debit card via <strong style="color:#f8fafc;">MoonPay</strong>.</p>
          <p>Your card will be charged approximately <strong style="color:#f8fafc;">${price:.2f}</strong> plus ~3-5% MoonPay processing fee.</p>
          <p class="co-fee-note">USDC is sent directly to Empire AI's vault on Solana. Your subscription activates automatically once confirmed on-chain (~30 seconds).</p>
        </div>
        <button class="co-btn co-btn-card" id="co-card-btn" onclick="payWithCard()">
          Pay ${price:.2f} with Card
        </button>
        <div id="co-card-status" class="co-pay-status" style="display:none">
          Opening MoonPay secure checkout...
        </div>
        <div class="co-powered">Powered by <a href="https://moonpay.com" target="_blank">MoonPay</a> · Card → USDC on Solana</div>
      </div>
      <script>
        var MOONPAY_URL = '{moonpay_url}';
      </script>
"""
    else:
        moonpay_button_html = """
      <div class="co-panel" id="co-panel-card">
        <div class="co-section-title">Pay with Card</div>
        <div class="co-card-info co-card-info-warn">
          <p>Card payments are not yet configured.</p>
          <p class="co-fee-note">To enable: set <code>MOONPAY_PUBLIC_KEY</code> and <code>MOONPAY_SECRET_KEY</code> in your environment.</p>
        </div>
      </div>
"""

    checkout_css = """
    .co-wrap { max-width: 640px; margin: 0 auto; padding: 80px 32px; position: relative; z-index: 1; }
    .co-card { background: #14141e; border: 1px solid #1e293b; padding: 40px; }
    .co-title { font-size: 28px; font-weight: 200; color: #f8fafc; margin-bottom: 8px; letter-spacing: -0.02em; }
    .co-title em { color: #44E5B8; font-style: italic; font-weight: 500; }
    .co-sub { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #94a3b8; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 32px; }
    .co-tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid #1e293b; }
    .co-tab { padding: 12px 24px; font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: #64748b; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
    .co-tab:hover { color: #94a3b8; }
    .co-tab.active { color: #44E5B8; border-bottom-color: #44E5B8; }
    .co-tab.soon { color: #475569; cursor: not-allowed; font-size: 9px; }
    .co-section-title { font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; color: #94a3b8; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 16px; font-weight: 600; }
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
    .co-btn { display: inline-block; padding: 14px 28px; background: #44E5B8; color: #020617; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; text-decoration: none; font-weight: 600; border: none; cursor: pointer; transition: all 0.2s; margin-top: 16px; }
    .co-btn:hover { background: #3dd4a7; }
    .co-btn:disabled { opacity: 0.4; cursor: wait; }
    .co-btn.secondary { background: transparent; border: 1px solid #44E5B8; color: #44E5B8; }
    .co-btn.secondary:hover { background: rgba(68,229,184,0.1); }
    .co-btn-card { background: #6366f1; color: #f8fafc; width: 100%; text-align: center; display: block; }
    .co-btn-card:hover { background: #4f46e5; }
    .co-form-group { margin-bottom: 20px; }
    .co-form-group label { display: block; font-family: 'SF Mono','Fira Code',monospace; font-size: 9px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }
    .co-form-group input { width: 100%; padding: 12px 14px; background: #0a0a0f; border: 1px solid #1e293b; color: #f8fafc; font-family: 'SF Mono','Fira Code',monospace; font-size: 13px; outline: none; transition: border-color 0.2s; }
    .co-form-group input:focus { border-color: #44E5B8; }
    .co-error { color: #ff6b6b; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; padding: 8px 0; }
    .co-success { color: #44E5B8; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; padding: 8px 0; }
    .co-card-info { background: #0a0a0f; border: 1px solid #1e293b; padding: 20px; margin: 16px 0; }
    .co-card-info p { font-size: 13px; color: #cbd5e1; line-height: 1.7; margin: 0 0 6px; }
    .co-card-info-warn code { color: #FFB800; font-size: 11px; }
    .co-fee-note { color: #64748b; font-size: 11px; font-family: 'SF Mono','Fira Code',monospace; }
    .co-pay-status { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #94a3b8; margin-top: 16px; padding: 12px; background: #0a0a0f; border: 1px solid #1e293b; }
    .co-pay-status a { color: #44E5B8; }
    .co-powered { text-align: center; margin-top: 20px; font-size: 10px; color: #475569; font-family: 'SF Mono','Fira Code',monospace; letter-spacing: 0.08em; }
    .co-powered a { color: #64748b; text-decoration: none; }
    .co-powered a:hover { color: #94a3b8; }
    @media (max-width: 540px) { .co-wrap { padding: 40px 16px; } .co-card { padding: 24px; } .co-tab { padding: 10px 14px; } }
    """

    head = empire_head(title=f"Empire AI · Checkout {tier}", extra=checkout_css)

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
<div class="co-wrap">
  <div class="co-card">
    <div class="co-title">Subscribe to <em>{tier}</em></div>
    <div class="co-sub">${price:.2f}/month</div>

    <div class="co-tabs">
      <div class="co-tab active" id="tab-card" onclick="switchTab('card')">Pay with Card</div>
      <div class="co-tab" id="tab-crypto" onclick="switchTab('crypto')">Pay with Crypto</div>
    </div>

    <div id="co-flow">
      <!-- Step 1: Email form (shared) -->
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
        <button class="co-btn" id="co-create-btn" onclick="createPayment()">Continue to Payment</button>
      </div>

      <!-- Step 2: Payment panels -->
      <div id="co-step-pay" style="display:none">
        <!-- Card Panel (MoonPay) -->
        {moonpay_button_html}

        <!-- Crypto Panel (Direct USDC) -->
        <div class="co-panel" id="co-panel-crypto" style="display:none">
          <div class="co-section-title">Pay with USDC (Solana)</div>
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
            <li data-step="5">Your subscription will activate automatically</li>
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
    </div>
  </div>
</div>

<script>
var currentPaymentId = null;
var currentTier = '{tier}';

function switchTab(tab) {{
  document.querySelectorAll('.co-tab').forEach(function(t) {{ t.classList.remove('active'); }});
  document.querySelectorAll('.co-panel').forEach(function(p) {{ p.style.display = 'none'; }});
  document.getElementById('tab-' + tab).classList.add('active');
  var panel = document.getElementById('co-panel-' + tab);
  if (panel) panel.style.display = 'block';
}}

function createPayment() {{
  var email = document.getElementById('co-email').value.trim();
  var accountId = document.getElementById('co-account').value.trim() || email;
  var errEl = document.getElementById('co-email-error');

  if (!email || !email.includes('@')) {{
    errEl.textContent = 'Please enter a valid email address';
    errEl.style.display = 'block';
    return;
  }}
  errEl.style.display = 'none';
  document.getElementById('co-create-btn').textContent = 'Processing...';
  document.getElementById('co-create-btn').disabled = true;

  fetch('/api/v1/crypto/pay', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ customer_email: email, customer_account_id: accountId, tier_level: currentTier }}),
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    if (data.ok) {{
      currentPaymentId = data.payment_id;
      document.getElementById('co-step-email').style.display = 'none';
      document.getElementById('co-step-pay').style.display = 'block';
      document.getElementById('co-amount').textContent = '$' + data.amount_usdc.toFixed(2) + ' USDC';
      document.getElementById('co-wallet').textContent = data.vault_wallet;
      document.getElementById('co-memo').textContent = data.memo;
      if (typeof MOONPAY_URL !== 'undefined') {{
        window.MOONPAY_URL = window.MOONPAY_URL + '&externalCustomerId=' + data.memo;
      }}
      document.getElementById('co-check-link').innerHTML =
        '<a href="/crypto/pay/' + data.payment_id + '" target="_blank">Payment status page</a>';
      switchTab('card');
      startPolling(data.payment_id);
    }} else {{
      document.getElementById('co-email-error').textContent = data.error || 'Failed to create payment request';
      document.getElementById('co-email-error').style.display = 'block';
      document.getElementById('co-create-btn').textContent = 'Continue to Payment';
      document.getElementById('co-create-btn').disabled = false;
    }}
  }})
  .catch(function(err) {{
    document.getElementById('co-email-error').textContent = 'Network error: ' + err.message;
    document.getElementById('co-email-error').style.display = 'block';
    document.getElementById('co-create-btn').textContent = 'Continue to Payment';
    document.getElementById('co-create-btn').disabled = false;
  }});
}}

function payWithCard() {{
  if (!window.MOONPAY_URL) return;
  var statusEl = document.getElementById('co-card-status');
  statusEl.style.display = 'block';
  statusEl.innerHTML = 'Redirecting to MoonPay secure checkout...';
  window.open(window.MOONPAY_URL, 'moonpay', 'width=480,height=800,scrollbars=yes');
}}

function checkStatus() {{
  if (!currentPaymentId) return;
  fetch('/api/v1/crypto/pay/' + currentPaymentId)
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      var el = document.getElementById('co-status');
      if (data.status === 'completed') {{
        el.innerHTML = '<span style="color:#44E5B8;font-size:16px;">\\u2705 Payment confirmed! Your subscription is active.</span>';
      }} else if (data.status === 'activation_pending') {{
        el.innerHTML = '<span style="color:#FFB800;">\\u26a1 Payment received! Activating your subscription...</span>';
      }} else if (data.status === 'expired') {{
        el.innerHTML = '<span style="color:#ff6b6b;">\\u23f0 Payment request expired. Please create a new one.</span>';
      }} else {{
        el.innerHTML = '\\u23f3 Waiting for payment...';
      }}
    }});
}}

function startPolling(paymentId) {{
  setInterval(function() {{
    if (paymentId) checkStatus();
  }}, 10000);
}}
</script>
</body>
</html>"""


# ── ROUTE REGISTRATION ────────────────────────────────────────────────

def register_moonpay_checkout_routes(
    app: FastAPI,
    *,
    get_db: Callable,
    vault_wallet: str = "",
    require_auth: Callable = None,
    crypto_payment_engine: Optional[object] = None,
):
    """
    Wire MoonPay checkout routes into the FastAPI app.

    GET  /checkout-card/{tier}       — standalone card checkout page (public)
    POST /api/v1/moonpay/webhook     — MoonPay transaction webhook (public)
    GET  /api/v1/moonpay/status      — MoonPay configuration status (operator)

    Requires a non-empty vault_wallet. Raises RuntimeError if missing.
    """
    if not vault_wallet or not vault_wallet.strip():
        raise RuntimeError(
            "register_moonpay_checkout_routes requires EMPIRE_VAULT_WALLET "
            "to be set. The checkout page needs a wallet address to render."
        )

    @app.get("/checkout-card/{tier}", response_class=HTMLResponse)
    async def moonpay_checkout_page(tier: str):
        """Standalone card checkout page with MoonPay widget + crypto fallback."""
        t = tier.strip()
        price = _lookup_price(t)
        if price is None:
            raise HTTPException(404, f"Unknown tier: {tier}")
        return HTMLResponse(_checkout_page_html(
            tier=t,
            price=price,
            vault_wallet=vault_wallet,
        ))

    @app.post("/api/v1/moonpay/webhook")
    async def moonpay_webhook(request: Request):
        """
        Receive MoonPay transaction_updated webhook events.

        MoonPay sends POST requests when a transaction status changes.
        This handler:
          1. Validates the HMAC signature (required if MOONPAY_WEBHOOK_SECRET is set)
          2. If the transaction is 'completed', proactively calls
             match_payment() on CryptoPaymentEngine to activate the subscription
          3. Logs the event for operator visibility

        Dual-path activation:
          - Primary: Helius webhook (detects USDC on-chain at vault wallet)
          - Supplementary (this): MoonPay webhook (fires before on-chain confirm)

        match_payment() is idempotent — its DB update uses .eq("status", "pending"),
        so if both webhooks fire for the same payment, only one wins the race.
        """
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8", errors="replace")

        # ── Signature validation (required when secret is set) ──
        if MOONPAY_WEBHOOK_SECRET:
            signature = request.headers.get("X-Moonpay-Signature", "")
            if not signature:
                log.warning("[moonpay-webhook] missing signature header")
                raise HTTPException(401, "Missing signature")
            expected = hmac.new(
                MOONPAY_WEBHOOK_SECRET.encode(),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                log.warning("[moonpay-webhook] invalid signature")
                raise HTTPException(401, "Invalid signature")

        # ── Parse payload ──
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            log.warning("[moonpay-webhook] invalid JSON")
            raise HTTPException(400, "Invalid JSON")

        data = payload.get("data", {})
        status = (data.get("status") or "").lower()

        # Only care about completed transactions
        if status != "completed":
            return {"ok": True, "received": True, "processed": False}

        tx_id = data.get("id", "?")
        wallet_address = data.get("walletAddress", "")
        crypto_amount = float(data.get("cryptoAmount", 0) or 0)
        currency = data.get("currency", "")
        external_customer_id = data.get("externalCustomerId", "")

        log.info(
            f"[moonpay-webhook] completed: "
            f"tx={str(tx_id)[:12]}... · {crypto_amount} {currency} · "
            f"wallet={wallet_address[:8] if wallet_address else '?'}..."
        )

        # ── Proactive payment matching (if crypto_payment_engine wired in) ──
        if crypto_payment_engine and hasattr(crypto_payment_engine, "match_payment"):
            try:
                sender = data.get("walletAddress", "") or data.get("fromAddress", "")
                match_result = await crypto_payment_engine.match_payment(
                    sender_address=sender,
                    amount_usdc=crypto_amount,
                    tx_signature=str(tx_id),
                    memo=external_customer_id or "",
                )
                if match_result.get("matched"):
                    log.info(
                        f"[moonpay-webhook] subscription activated: "
                        f"{match_result.get('payment_id', '?')[:12]}... · "
                        f"{match_result.get('customer_email', '?')}"
                    )
                else:
                    log.info(
                        f"[moonpay-webhook] no pending match for "
                        f"{crypto_amount} {currency} (tx={tx_id[:12]}...) · "
                        f"Helius webhook will handle on-chain confirmation"
                    )
            except Exception as e:
                log.error(f"[moonpay-webhook] match_payment error: {e}")

        return {"ok": True, "received": True, "processed": True}

    @app.get("/api/v1/moonpay/status")
    async def moonpay_status(auth: bool = Depends(require_auth) if require_auth else None):
        """Return MoonPay configuration status for operator review."""
        return {
            "configured": _has_moonpay,
            "public_key_set": bool(MOONPAY_PUBLIC_KEY),
            "secret_key_set": bool(MOONPAY_SECRET_KEY),
            "webhook_secret_set": bool(MOONPAY_WEBHOOK_SECRET),
            "supported_tiers": len(TIER_PRICES_USDC),
            "vault_wallet": vault_wallet[:8] + "..." if len(vault_wallet) > 12 else vault_wallet,
            "checkout_url": "/checkout-card/{tier}",
            "webhook_url": "/api/v1/moonpay/webhook",
            "crypto_engine_wired": crypto_payment_engine is not None,
        }

    log.info("[moonpay-checkout] Routes registered · /checkout-card/{tier}")
