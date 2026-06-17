"""
EMPIRE V49 · CONTRACTOR PRIORITY DISPATCH
=========================================
Paid tier checkout page at /contractors/priority. $99/mo Solana USDC
subscription for priority lead dispatch, advance notice, and priority
matching.

Payment: Solana USDC to Empire vault wallet. No Stripe dependency.
After payment, contractor fills out the activation form. Operator
verifies on-chain and activates the tier manually (Phase 1).
"""

import os
import re
import json
import logging
import hashlib
from datetime import datetime, timezone
from fastapi import Request
from fastapi.responses import JSONResponse


log = logging.getLogger("empire.contractor_priority")

try:
    from empire_tokens import empire_head
except ImportError:
    def empire_head(title: str = "Empire AI", extra: str = "") -> str:
        return f"<head><title>{title}</title></head>"


# Wallet addresses from env
EMPIRE_VAULT_WALLET = os.environ.get("EMPIRE_VAULT_WALLET", "")
PRIORITY_PRICE_USDC = 99
PRIORITY_MEMO_PREFIX = "PRIORITY:"


def _page_css() -> str:
    """Page-specific CSS matching the Empire contractor design system."""
    return """
    .pp-body {
      min-height: 100vh;
      background: linear-gradient(180deg, #0A1A2F 0%, #08121F 100%);
      color: #E8EEF6;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .pp-wrap {
      max-width: 880px;
      margin: 0 auto;
      padding: 32px 20px 80px;
    }
    .pp-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 0 28px;
      border-bottom: 1px solid rgba(232,238,246,0.08);
    }
    .pp-brand { font-weight: 700; letter-spacing: 0.04em; font-size: 14px; }
    .pp-brand span { color: #4FD1C5; }
    .pp-toplink { color: #94A3B8; font-size: 12px; text-decoration: none; }
    .pp-toplink:hover { color: #4FD1C5; }

    .pp-hero {
      padding: 48px 0 32px;
      text-align: center;
    }
    .pp-hero-eyebrow {
      display: inline-block;
      text-transform: uppercase; letter-spacing: 0.18em;
      font-size: 11px; color: #4FD1C5; margin-bottom: 18px;
      background: rgba(79,209,197,0.10);
      padding: 4px 14px; border-radius: 20px;
    }
    .pp-hero h1 {
      font-size: 40px; line-height: 1.15; font-weight: 800;
      margin: 0 0 16px; color: #FFFFFF;
    }
    .pp-hero h1 em { font-style: normal; color: #4FD1C5; }
    .pp-hero-sub {
      font-size: 17px; line-height: 1.55; color: #B8C5D6;
      max-width: 620px; margin: 0 auto;
    }
    .pp-price-block {
      margin: 32px 0 0;
      display: flex; justify-content: center; align-items: baseline; gap: 6px;
    }
    .pp-price {
      font-size: 56px; font-weight: 800; color: #FFFFFF; line-height: 1;
    }
    .pp-price-super {
      font-size: 22px; font-weight: 600; color: #B8C5D6; vertical-align: super;
    }
    .pp-price-sub {
      font-size: 16px; color: #64748B; margin-left: 4px;
    }

    .pp-section {
      padding: 48px 0;
      border-top: 1px solid rgba(232,238,246,0.08);
    }
    .pp-section h2 {
      font-size: 22px; font-weight: 700; margin: 0 0 24px;
      letter-spacing: -0.01em;
    }

    .pp-features {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 640px) { .pp-features { grid-template-columns: 1fr; } }
    .pp-feat {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.08);
      border-radius: 12px; padding: 20px;
      display: flex; gap: 14px; align-items: flex-start;
    }
    .pp-feat-icon {
      flex-shrink: 0;
      width: 38px; height: 38px; border-radius: 10px;
      background: rgba(79,209,197,0.12);
      display: flex; align-items: center; justify-content: center;
      font-size: 18px;
    }
    .pp-feat h3 { font-size: 15px; margin: 0 0 4px; color: #FFFFFF; }
    .pp-feat p  { font-size: 13px; margin: 0; color: #94A3B8; line-height: 1.5; }

    .pp-compare {
      width: 100%; border-collapse: collapse;
      background: rgba(255,255,255,0.02);
      border: 1px solid rgba(232,238,246,0.08);
      border-radius: 12px; overflow: hidden;
    }
    .pp-compare th {
      text-align: left; padding: 14px 18px;
      font-family: monospace; font-size: 10px; letter-spacing: 0.12em;
      color: #64748B; text-transform: uppercase;
      background: rgba(255,255,255,0.02);
      border-bottom: 1px solid rgba(232,238,246,0.08);
    }
    .pp-compare th:first-child { width: 50%; }
    .pp-compare td {
      padding: 12px 18px;
      font-size: 14px; color: #B8C5D6;
      border-bottom: 1px solid rgba(232,238,246,0.05);
    }
    .pp-compare .yes { color: #4FD1C5; font-weight: 600; }
    .pp-compare .no  { color: #64748B; }
    .pp-compare tr:last-child td { border-bottom: none; }

    .pp-payment {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(79,209,197,0.20);
      border-radius: 14px; padding: 32px;
    }
    .pp-payment-steps {
      counter-reset: paystep;
      list-style: none; padding: 0; margin: 0 0 28px;
    }
    .pp-payment-steps li {
      counter-increment: paystep;
      padding: 14px 0 14px 40px;
      position: relative;
      border-bottom: 1px solid rgba(232,238,246,0.05);
      font-size: 14px; color: #B8C5D6; line-height: 1.6;
    }
    .pp-payment-steps li::before {
      content: counter(paystep);
      position: absolute; left: 0; top: 14px;
      width: 28px; height: 28px; line-height: 28px; text-align: center;
      border-radius: 50%;
      background: rgba(79,209,197,0.16); color: #4FD1C5;
      font-weight: 700; font-size: 13px;
    }
    .pp-payment-steps li code {
      background: rgba(79,209,197,0.08);
      color: #4FD1C5; padding: 2px 6px; border-radius: 4px;
      font-size: 13px; word-break: break-all;
    }
    .pp-wallet-box {
      background: #0A1A2F; border: 1px solid rgba(79,209,197,0.25);
      border-radius: 10px; padding: 16px 18px;
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; margin: 16px 0;
    }
    .pp-wallet-box code {
      font-family: 'SF Mono', 'Fira Code', monospace;
      font-size: 13px; color: #4FD1C5; word-break: break-all;
    }
    .pp-copy-btn {
      flex-shrink: 0;
      padding: 8px 16px; border: 1px solid rgba(79,209,197,0.30);
      background: rgba(79,209,197,0.08); color: #4FD1C5;
      border-radius: 6px; cursor: pointer;
      font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
      text-transform: uppercase;
      transition: all 0.15s;
    }
    .pp-copy-btn:hover { background: rgba(79,209,197,0.16); }
    .pp-copy-btn.copied { background: #4FD1C5; color: #0A1A2F; border-color: #4FD1C5; }

    .pp-form {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(232,238,246,0.10);
      border-radius: 14px; padding: 32px;
    }
    .pp-form-row {
      display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px;
    }
    @media (max-width: 640px) { .pp-form-row { grid-template-columns: 1fr; } }
    .pp-form-row.single { grid-template-columns: 1fr; }
    .pp-field label {
      display: block; font-size: 12px; font-weight: 600;
      letter-spacing: 0.04em; text-transform: uppercase;
      color: #94A3B8; margin-bottom: 6px;
    }
    .pp-field input, .pp-field select {
      width: 100%; padding: 11px 12px; border-radius: 8px;
      background: rgba(10,26,47,0.6); color: #E8EEF6;
      border: 1px solid rgba(232,238,246,0.18);
      font-size: 15px; box-sizing: border-box;
    }
    .pp-field input:focus, .pp-field select:focus {
      outline: 0; border-color: #4FD1C5;
    }
    .pp-submit {
      background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);
      color: #0A1A2F; border: 0; border-radius: 8px;
      padding: 14px 28px; font-size: 15px; font-weight: 700;
      cursor: pointer; letter-spacing: 0.01em;
      width: 100%;
    }
    .pp-submit:disabled { opacity: 0.5; cursor: not-allowed; }
    .pp-submit:hover:not(:disabled) { transform: translateY(-1px); }

    .pp-status {
      margin-top: 18px; padding: 14px 16px; border-radius: 8px;
      font-size: 14px; display: none;
    }
    .pp-status.ok  { background: rgba(79,209,197,0.10); color: #4FD1C5; display: block; }
    .pp-status.err { background: rgba(252,129,129,0.10); color: #FC8181; display: block; }

    .pp-amount-box {
      display: flex; align-items: center; gap: 10px;
      margin: 20px 0; padding: 16px 18px;
      background: rgba(79,209,197,0.08);
      border: 1px solid rgba(79,209,197,0.20);
      border-radius: 10px;
    }
    .pp-amount-label {
      font-size: 13px; color: #94A3B8; text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .pp-amount-value {
      font-family: monospace; font-size: 28px; font-weight: 700;
      color: #4FD1C5;
    }
    .pp-amount-sub {
      font-size: 13px; color: #64748B;
    }

    .pp-footer {
      text-align: center; padding: 40px 0 20px;
      font-size: 12px; color: #64748B;
    }
    """


def priority_page(public_base_url: str = "") -> str:
    """Render the /contractors/priority checkout page."""
    wallet = EMPIRE_VAULT_WALLET or "WALLET_NOT_CONFIGURED"
    wallet_short = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 12 else wallet

    return f"""<!DOCTYPE html>
<html lang="en">
{empire_head(title="Empire AI · Priority Dispatch", extra=_page_css())}
<body class="pp-body">
  <div class="pp-wrap">
    <header class="pp-header">
      <div class="pp-brand">EMPIRE <span>AI</span></div>
      <a class="pp-toplink" href="/contractors">← Back to contractors</a>
    </header>

    <section class="pp-hero">
      <div class="pp-hero-eyebrow">Priority Tier</div>
      <h1>Get dispatched <em>first.</em> Every time.</h1>
      <p class="pp-hero-sub">
        Standard dispatch works. Priority Dispatch means you see the lead
        before anyone else — and we match you to the highest-value claims
        in your metro.
      </p>
      <div class="pp-price-block">
        <span class="pp-price-super">$</span>
        <span class="pp-price">{PRIORITY_PRICE_USDC}</span>
        <span class="pp-price-sub">USDC / month</span>
      </div>
    </section>

    <section class="pp-section">
      <h2>What you get</h2>
      <div class="pp-features">
        <div class="pp-feat">
          <div class="pp-feat-icon">⚡</div>
          <div>
            <h3>First-look window</h3>
            <p>You get every new lead 15 minutes before it hits the standard queue. Accept before anyone else sees it.</p>
          </div>
        </div>
        <div class="pp-feat">
          <div class="pp-feat-icon">🎯</div>
          <div>
            <h3>Higher claim value routing</h3>
            <p>Priority contractors are matched to claims above $50K first. Standard contractors fill the remainder.</p>
          </div>
        </div>
        <div class="pp-feat">
          <div class="pp-feat-icon">📊</div>
          <div>
            <h3>Weekly dispatch report</h3>
            <p>Every Monday: leads routed, claims in your pipeline, estimated closed value. No guesswork.</p>
          </div>
        </div>
        <div class="pp-feat">
          <div class="pp-feat-icon">🔔</div>
          <div>
            <h3>Advance storm alert</h3>
            <p>We text you 24 hours before a forecasted severe weather event hits your metro so you can pre-stage crews.</p>
          </div>
        </div>
        <div class="pp-feat">
          <div class="pp-feat-icon">🛡️</div>
          <div>
            <h3>Dedicated support</h3>
            <p>Priority email and SMS support. Dispute a match? We fix it same-day. Human operator, not a bot.</p>
          </div>
        </div>
        <div class="pp-feat">
          <div class="pp-feat-icon">💸</div>
          <div>
            <h3>Same 3% fee</h3>
            <p>No markup on the success fee. You pay the subscription — we don't touch your claim settlement beyond the standard 3%.</p>
          </div>
        </div>
      </div>
    </section>

    <section class="pp-section">
      <h2>Free vs Priority</h2>
      <table class="pp-compare">
        <thead>
          <tr><th></th><th>Free</th><th>Priority</th></tr>
        </thead>
        <tbody>
          <tr><td>Lead dispatch</td><td class="yes">✓</td><td class="yes">✓</td></tr>
          <tr><td>First 2 deals complimentary</td><td class="yes">✓</td><td class="yes">✓</td></tr>
          <tr><td>3% fee on settled claims</td><td class="yes">✓</td><td class="yes">✓</td></tr>
          <tr><td>15-min first-look window</td><td class="no">—</td><td class="yes">✓</td></tr>
          <tr><td>$50K+ claim priority routing</td><td class="no">—</td><td class="yes">✓</td></tr>
          <tr><td>Weekly dispatch report</td><td class="no">—</td><td class="yes">✓</td></tr>
          <tr><td>24h advance storm alerts</td><td class="no">—</td><td class="yes">✓</td></tr>
          <tr><td>Dedicated support</td><td class="no">—</td><td class="yes">✓</td></tr>
          <tr><td>Monthly cost</td><td class="yes">$0</td><td class="yes">$99 USDC</td></tr>
        </tbody>
      </table>
    </section>

    <section class="pp-section">
      <h2>Activate Priority Dispatch</h2>
      <p style="color:#B8C5D6;margin:0 0 24px;font-size:15px;">
        Two steps: send <strong>{PRIORITY_PRICE_USDC} USDC</strong> via Solana, then submit your details below.
        We verify on-chain and activate within 24 hours.
      </p>

      <div class="pp-payment">
        <h3 style="font-size:16px;margin:0 0 16px;color:#FFFFFF;">Step 1 — Send payment</h3>

        <div class="pp-amount-box">
          <span class="pp-amount-label">Amount</span>
          <span class="pp-amount-value">{PRIORITY_PRICE_USDC} USDC</span>
          <span class="pp-amount-sub">on Solana</span>
        </div>

        <p style="font-size:13px;color:#94A3B8;margin:0 0 4px;">Send to Empire vault wallet:</p>
        <div class="pp-wallet-box">
          <code id="pp-wallet">{wallet}</code>
          <button class="pp-copy-btn" id="pp-copy-btn" onclick="copyWallet()">Copy</button>
        </div>

        <p style="font-size:12px;color:#64748B;margin:0 0 0;">
          Include memo: <code style="background:rgba(79,209,197,0.08);color:#4FD1C5;padding:1px 5px;border-radius:3px;">{PRIORITY_MEMO_PREFIX}&lt;your-email&gt;</code>
        </p>
      </div>

      <div class="pp-form" style="margin-top:24px;">
        <h3 style="font-size:16px;margin:0 0 16px;color:#FFFFFF;">Step 2 — Confirm your details</h3>
        <form id="pp-form" autocomplete="on">
          <div class="pp-form-row">
            <div class="pp-field">
              <label for="pp-name">Your name</label>
              <input type="text" id="pp-name" name="name" required maxlength="120" autocomplete="name" />
            </div>
            <div class="pp-field">
              <label for="pp-company">Company</label>
              <input type="text" id="pp-company" name="company" required maxlength="200" autocomplete="organization" />
            </div>
          </div>
          <div class="pp-form-row">
            <div class="pp-field">
              <label for="pp-email">Email</label>
              <input type="email" id="pp-email" name="email" required maxlength="200" autocomplete="email" />
            </div>
            <div class="pp-field">
              <label for="pp-phone">Phone (E.164)</label>
              <input type="tel" id="pp-phone" name="phone" required maxlength="20" autocomplete="tel" placeholder="+18175551234" />
            </div>
          </div>
          <div class="pp-form-row">
            <div class="pp-field">
              <label for="pp-metro">Service metro</label>
              <input type="text" id="pp-metro" name="metro" required maxlength="120" placeholder="DFW, Houston, San Antonio, ..." />
            </div>
            <div class="pp-field">
              <label for="pp-wallet-input">Your Solana wallet (for future payouts)</label>
              <input type="text" id="pp-wallet-input" name="solana_wallet" maxlength="48" placeholder="Your SOL address" />
            </div>
          </div>
          <div class="pp-form-row single">
            <div class="pp-field">
              <label for="pp-tx">Transaction signature (from your wallet)</label>
              <input type="text" id="pp-tx" name="tx_signature" required minlength="80" maxlength="200" placeholder="Paste the Solana tx signature after sending" />
            </div>
          </div>
          <button class="pp-submit" type="submit" id="pp-submit">Submit activation</button>
          <div class="pp-status" id="pp-status"></div>
          <p style="margin-top:18px;font-size:12px;color:#64748B;line-height:1.5;">
            By submitting you confirm the payment of {PRIORITY_PRICE_USDC} USDC for the first month of Priority Dispatch. Empire AI will verify the transaction on Solana and activate your tier within 24 hours. Cancel any time — no contract, no minimum.
          </p>
        </form>
      </div>
    </section>

    <footer class="pp-footer">
      empire-ai.co.uk · © 2026 · {PRIORITY_PRICE_USDC} USDC/mo on Solana · Cancel any time
    </footer>
  </div>

  <script>
    function copyWallet() {{
      var el = document.getElementById('pp-wallet');
      var btn = document.getElementById('pp-copy-btn');
      if (!el) return;
      navigator.clipboard.writeText(el.textContent.trim()).then(function() {{
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(function() {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
      }}).catch(function() {{
        // Fallback
        var range = document.createRange();
        range.selectNode(el);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(function() {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
      }});
    }}

    (function() {{
      var form = document.getElementById('pp-form');
      var status = document.getElementById('pp-status');
      var submitBtn = document.getElementById('pp-submit');
      if (!form) return;

      form.addEventListener('submit', async function(e) {{
        e.preventDefault();
        status.className = 'pp-status';
        status.textContent = '';
        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        var fd = new FormData(form);
        var payload = {{
          name:           (fd.get('name')           || '').toString().trim(),
          company:        (fd.get('company')        || '').toString().trim(),
          email:          (fd.get('email')          || '').toString().trim(),
          phone:          (fd.get('phone')          || '').toString().trim(),
          metro:          (fd.get('metro')          || '').toString().trim(),
          solana_wallet:  (fd.get('solana_wallet')  || '').toString().trim(),
          tx_signature:   (fd.get('tx_signature')   || '').toString().trim(),
        }};

        try {{
          var r = await fetch('/api/contractors/priority-activate', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload),
          }});
          var data = await r.json().catch(function() {{ return {{ ok: false, error: 'invalid_response' }}; }});
          if (r.ok && data.ok) {{
            status.className = 'pp-status ok';
            status.textContent = data.message || 'Received! We will verify your payment and activate Priority Dispatch within 24 hours.';
            form.reset();
          }} else {{
            var msg = (data && data.error) ? data.error.replace(/_/g, ' ') : 'something went wrong';
            status.className = 'pp-status err';
            status.textContent = 'Could not submit: ' + msg + '. Please try again or email priority@empire-ai.co.uk.';
          }}
        }} catch (err) {{
          status.className = 'pp-status err';
          status.textContent = 'Network error. Please try again.';
        }} finally {{
          submitBtn.disabled = false;
          submitBtn.textContent = 'Submit activation';
        }}
      }});
    }})();
  </script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────
# Activation endpoint
# ─────────────────────────────────────────────────────────────────────

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def priority_activate(request: Request) -> JSONResponse:
    """POST /api/contractors/priority-activate

    Receives contractor priority activation request. Stores in
    contractor_priority_subscriptions table for operator review.
    Operator verifies Solana tx on-chain and activates manually.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "invalid_payload"}, status_code=400)

    name          = (body.get("name") or "").strip()
    company       = (body.get("company") or "").strip()
    email         = (body.get("email") or "").strip()
    phone         = (body.get("phone") or "").strip()
    metro         = (body.get("metro") or "").strip()
    solana_wallet = (body.get("solana_wallet") or "").strip()
    tx_signature  = (body.get("tx_signature") or "").strip()

    # Validation
    if not name:
        return JSONResponse({"ok": False, "error": "missing_name", "field": "name"}, status_code=400)
    if not company:
        return JSONResponse({"ok": False, "error": "missing_company", "field": "company"}, status_code=400)
    if not email or not _EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "invalid_email", "field": "email"}, status_code=400)
    if not phone or not _E164_RE.match(phone):
        return JSONResponse({"ok": False, "error": "invalid_phone", "field": "phone"}, status_code=400)
    if not metro:
        return JSONResponse({"ok": False, "error": "missing_metro", "field": "metro"}, status_code=400)
    if not tx_signature or len(tx_signature) < 80:
        return JSONResponse({"ok": False, "error": "invalid_tx_signature", "field": "tx_signature"}, status_code=400)
    # Basic Solana wallet validation: 32-44 base58 chars
    if solana_wallet:
        sol_wallet_re = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
        if not sol_wallet_re.match(solana_wallet):
            return JSONResponse({"ok": False, "error": "invalid_solana_wallet", "field": "solana_wallet"}, status_code=400)

    # Get DB
    db = None
    if _get_db_override is not None:
        db = _get_db_override()
    if db is None:
        try:
            from hub import get_db
            db = get_db()
        except Exception:
            try:
                from supabase import create_client
                db = create_client(
                    os.environ.get("SUPABASE_URL", ""),
                    os.environ.get("SUPABASE_SERVICE_KEY", ""),
                )
            except Exception as e:
                log.error(f"[priority_activate] db unavailable: {e}")
                return JSONResponse({"ok": False, "error": "db_unavailable"}, status_code=500)

    # Duplicate check — same email or phone shouldn't double-submit
    try:
        existing = db.table("contractor_priority_subscriptions") \
            .select("id,status") \
            .or_(f"email.eq.{email},phone.eq.{phone}") \
            .in_("status", ["pending_verification","verified","active"]) \
            .limit(1).execute()
        if existing.data:
            return JSONResponse({
                "ok": True,
                "existing": True,
                "message": "You already have a Priority Dispatch subscription pending or active. We'll be in touch.",
            }, status_code=200)
    except Exception as e:
        log.warning(f"[priority_activate] duplicate check failed: {e}")

    # Insert into contractor_priority_subscriptions
    payload = {
        "name": name,
        "company": company,
        "email": email,
        "phone": phone,
        "metro": metro,
        "solana_wallet": solana_wallet or None,
        "tx_signature": tx_signature,
        "amount_usdc": PRIORITY_PRICE_USDC,
        "status": "pending_verification",
        "meta": {
            "page_source": "priority_checkout",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        ins = db.table("contractor_priority_subscriptions").insert(payload).execute()
    except Exception as e:
        log.error(f"[priority_activate] insert failed: {e}")
        return JSONResponse({"ok": False, "error": "insert_failed"}, status_code=500)

    if not ins.data:
        return JSONResponse({"ok": False, "error": "insert_returned_no_row"}, status_code=500)

    sub_id = ins.data[0].get("id")
    log.info(f"[priority_activate] new subscription: {sub_id} | {email} | {company[:30]}")

    return JSONResponse({
        "ok": True,
        "subscription_id": sub_id,
        "message": (
            f"Received! We will verify your {PRIORITY_PRICE_USDC} USDC payment "
            f"(tx: {tx_signature[:12]}...) and activate Priority Dispatch "
            f"within 24 hours. Check {email} for confirmation."
        ),
    }, status_code=200)


# ─────────────────────────────────────────────────────────────────────
# Route registration
# ─────────────────────────────────────────────────────────────────────

def register_priority_routes(
    app,
    public_base_url: str = "",
    get_db=None,
):
    """Mount /contractors/priority and /api/contractors/priority-activate."""
    from fastapi.responses import HTMLResponse

    if get_db is not None:
        global _get_db_override
        _get_db_override = get_db

    app.add_api_route(
        "/contractors/priority",
        lambda: HTMLResponse(priority_page(public_base_url=public_base_url)),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/api/contractors/priority-activate",
        priority_activate,
        methods=["POST"],
    )
    log.info("[priority] routes registered: GET /contractors/priority, POST /api/contractors/priority-activate")


_get_db_override = None
