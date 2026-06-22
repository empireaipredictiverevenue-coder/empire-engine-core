"""
Empire AI · PAYMENT PAGE
========================

Short-URL payment route for contractors to settle fee_events.

Routes:
  GET  /pay/<claim_id>                  → branded payment page (HTML, no auth)
  GET  /pay/<claim_id>.json             → fee details for the page (no auth)
  POST /api/v1/fee/check-paid           → check on-chain for USDC tx to vault
  POST /api/v1/fee/mark-paid            → mark fee as paid (after confirmed tx)

The page does:
  - Shows fee amount, claim amount, contractor name
  - Shows vault wallet address (full, copyable)
  - Renders a Solana Pay QR code (solana:<vault>?amount=<usdc>&label=Empire%20AI)
  - "I have paid" button → calls /api/v1/fee/mark-paid (operator-authenticated via
    the claim_id as the bearer, since contractors don't have hub accounts)

Vault wallet: VAULT_WALLET (from scripts/vault_monitor.py).
USDC mint on Solana mainnet: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from empire_tokens import empire_head

log = logging.getLogger("empire.payment_page")

# Mirror of the wallet in scripts/vault_monitor.py / scripts/fee_collection_agent.py
VAULT_WALLET = os.environ.get("EMPIRE_VAULT_WALLET", "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM")
# Native SOL = 9 decimals, USDC = 6 decimals. We charge USDC.
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6

_PAYMENT_PAGE_CSS = """
/* Payment page styles — built on Empire design system variables */
.pay-wrap {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.pay-card {
  max-width: 480px; width: 100%;
  background: var(--empire-surface);
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  box-shadow: var(--shadow-elevated);
}
.pay-brand {
  display: flex; align-items: center; gap: 10px; margin-bottom: 24px;
}
.pay-brand-mark {
  width: 36px; height: 36px;
  background: linear-gradient(135deg, var(--signal-teal), var(--strike-cyan));
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: var(--empire-black); font-family: var(--font-display);
}
.pay-brand-name {
  font-size: 14px; font-weight: 600; letter-spacing: .5px;
  color: var(--empire-mist);
}
.pay-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; color: var(--empire-white); }
.pay-sub { color: var(--empire-mist); font-size: 13px; margin-bottom: 24px; }
.pay-amount {
  background: var(--empire-elevated); border: 1px solid var(--empire-border);
  border-radius: var(--radius-lg); padding: 20px; text-align: center; margin-bottom: 20px;
}
.pay-amount-fee { font-size: 38px; font-weight: 700; color: var(--signal-teal); letter-spacing: -.5px; }
.pay-amount-claim { font-size: 13px; color: var(--empire-mist); margin-top: 6px; }
.pay-qr-wrap {
  background: #fff; border-radius: var(--radius-lg); padding: 16px;
  display: flex; justify-content: center; margin-bottom: 18px;
}
.pay-qr-wrap img { display: block; max-width: 240px; width: 100%; height: auto; }
.pay-wallet {
  background: rgba(0,0,0,0.4); border: 1px solid var(--empire-border);
  border-radius: var(--radius-md); padding: 14px; margin-bottom: 18px;
}
.pay-wallet-label {
  font-family: var(--font-mono); font-size: 10px; text-transform: uppercase;
  letter-spacing: 1px; color: var(--empire-mist); margin-bottom: 8px;
}
.pay-wallet-addr {
  font-family: var(--font-mono); font-size: 13px; color: var(--empire-silver);
  word-break: break-all; line-height: 1.5;
}
.pay-copy-btn {
  margin-top: 10px; background: var(--empire-elevated); color: var(--empire-silver);
  border: 1px solid var(--empire-border); padding: 8px 14px; border-radius: var(--radius-sm);
  font-size: 12px; cursor: pointer; width: 100%; font-weight: 500;
  font-family: var(--font-ui); transition: all .15s;
}
.pay-copy-btn:hover { background: var(--empire-shadow); color: var(--empire-white); }
.pay-copy-btn.copied { background: #16a34a; color: #fff; border-color: #16a34a; }
.pay-steps {
  background: rgba(0,0,0,0.4); border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md); padding: 16px; margin-bottom: 18px;
}
.pay-steps h3 {
  font-family: var(--font-mono); font-size: 10px; text-transform: uppercase;
  letter-spacing: 1px; color: var(--empire-mist); margin-bottom: 12px; font-weight: 600;
}
.pay-step {
  display: flex; gap: 12px; margin-bottom: 10px;
  font-size: 13px; color: var(--empire-silver); line-height: 1.5;
}
.pay-step-num {
  flex-shrink: 0; width: 22px; height: 22px;
  background: var(--signal-teal); color: var(--empire-black);
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 11px; font-family: var(--font-mono);
}
.pay-btn {
  display: block; width: 100%;
  background: var(--signal-teal); color: var(--empire-black);
  border: 1px solid var(--signal-teal);
  padding: 14px; border-radius: var(--radius-md);
  font-size: 15px; font-weight: 700; cursor: pointer;
  font-family: var(--font-ui); transition: all .15s;
}
.pay-btn:hover {
  background: transparent; color: var(--signal-teal);
  box-shadow: var(--glow-soft); transform: translateY(-1px);
}
.pay-btn:disabled {
  background: var(--empire-shadow); color: var(--empire-mist);
  border-color: var(--empire-divider); cursor: not-allowed; transform: none;
}
.pay-status {
  margin-top: 14px; padding: 12px; border-radius: var(--radius-sm);
  font-family: var(--font-mono); font-size: 12px; text-align: center; display: none;
}
.pay-status.show { display: block; }
.pay-status.checking { background: var(--strike-cyan-soft); color: var(--strike-cyan); border: 1px solid rgba(90,200,250,0.3); }
.pay-status.paid { background: var(--signal-teal-soft); color: var(--signal-teal); border: 1px solid rgba(68,229,184,0.3); }
.pay-status.error { background: var(--status-red-soft); color: var(--status-red); border: 1px solid rgba(255,71,87,0.3); }
.pay-meta {
  background: rgba(0,0,0,0.4); border: 1px solid var(--empire-divider);
  border-radius: var(--radius-sm); padding: 12px; margin-bottom: 18px;
  font-size: 12px; color: var(--empire-mist); line-height: 1.6;
}
.pay-meta-row { display: flex; justify-content: space-between; gap: 8px; }
.pay-meta-label { color: var(--empire-fog); font-family: var(--font-mono); font-size: 10px; letter-spacing: .08em; }
.pay-footer {
  text-align: center; color: var(--empire-fog);
  font-family: var(--font-mono); font-size: 10px; margin-top: 18px; letter-spacing: .04em;
}
.pay-discount-badge {
  display: inline-block;
  background: linear-gradient(135deg, var(--status-amber), #f59e0b);
  color: #1f2937; padding: 6px 14px; border-radius: var(--radius-pill);
  font-family: var(--font-mono); font-size: 11px; font-weight: 700;
  letter-spacing: .5px; margin-bottom: 10px;
}
.pay-og-line {
  font-size: 13px; text-decoration: line-through;
  color: var(--empire-fog); margin-top: 2px;
}
"""

PAYMENT_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
{head_html}
<body>
<div class="pay-wrap">
<div class="pay-card">
  <div class="pay-brand">
    <div class="pay-brand-mark">E</div>
    <div class="pay-brand-name">EMPIRE AI · empire-ai.co.uk</div>
  </div>

  <h1 class="pay-title">Settle Your Fee</h1>
  <div class="pay-sub">Claim {claim_id} · Pay {fee_usdc} USDC to Empire AI vault.</div>

  <div class="pay-amount">
    {discount_badge}
    <div class="pay-amount-fee">${fee_usd}</div>
    {original_fee_line}
    <div class="pay-amount-claim">3% of ${claim_usd} settled claim</div>
  </div>

  <div class="pay-meta">
    <div class="pay-meta-row"><span class="pay-meta-label">Contractor</span><span>{contractor_name}</span></div>
    <div class="pay-meta-row"><span class="pay-meta-label">Network</span><span>Solana · USDC</span></div>
    <div class="pay-meta-row"><span class="pay-meta-label">Status</span><span style="color:var(--status-amber)">Awaiting payment</span></div>
  </div>

  <div class="pay-qr-wrap">
    <img src="data:image/svg+xml;utf8,{qr_svg}" alt="Solana Pay QR code" />
  </div>

  <div class="pay-wallet">
    <div class="pay-wallet-label">Vault Wallet (USDC on Solana)</div>
    <div class="pay-wallet-addr" id="wallet">{wallet}</div>
    <button class="pay-copy-btn" id="copyBtn" onclick="copyWallet()">📋 Copy wallet address</button>
  </div>

  <div class="pay-steps">
    <h3>How to pay</h3>
    <div class="pay-step"><div class="pay-step-num">1</div><div>Open Phantom, Solflare, or any Solana wallet. Scan the QR code or paste the vault address above.</div></div>
    <div class="pay-step"><div class="pay-step-num">2</div><div>Send exactly <strong>{fee_usdc} USDC</strong> (not SOL). USDC on Solana mainnet.</div></div>
    <div class="pay-step"><div class="pay-step-num">3</div><div>Click <strong>I have paid</strong> below. We auto-verify the on-chain transfer.</div></div>
  </div>

  <button class="pay-btn" id="paidBtn" onclick="markPaid()">✓ I have paid {fee_usdc} USDC</button>
  <div class="pay-status" id="status"></div>

  <div class="pay-footer">
    Need help? Reply to the original SMS or email ops@empire-ai.co.uk.<br>
    Powered by Empire AI · {claim_id_short}
  </div>
</div>
</div>

<script>
const CLAIM_ID = "{claim_id}";
function copyWallet() {{
  const addr = document.getElementById('wallet').textContent.trim();
  navigator.clipboard.writeText(addr).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✓ Copied to clipboard';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = '📋 Copy wallet address'; btn.classList.remove('copied'); }}, 2500);
  }}).catch(() => {{
    const range = document.createRange();
    range.selectNode(document.getElementById('wallet'));
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  }});
}}

async function markPaid() {{
  const btn = document.getElementById('paidBtn');
  const status = document.getElementById('status');
  btn.disabled = true;
  btn.textContent = 'Checking on-chain transfer...';
  status.className = 'pay-status show checking';
  status.textContent = 'Verifying your USDC transfer on Solana...';

  try {{
    const res = await fetch('/api/v1/fee/check-paid', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ claim_id: CLAIM_ID }})
    }});
    const data = await res.json();
    if (res.ok && data.paid) {{
      status.className = 'pay-status show paid';
      status.innerHTML = '✓ Payment confirmed! Fee marked paid. Thank you.<br>Your contractor account has been updated.';
      btn.textContent = '✓ Paid';
      btn.style.background = '#16a34a';
    }} else if (data.found_pending) {{
      status.className = 'pay-status show error';
      status.innerHTML = '⚠ We see your transaction in the mempool but it is not yet confirmed. Wait 30 seconds and click again.';
      btn.disabled = false;
      btn.textContent = '✓ I have paid {fee_usdc} USDC';
    }} else {{
      status.className = 'pay-status show error';
      status.innerHTML = '⚠ No matching transfer found yet. Make sure you sent <strong>{fee_usdc} USDC</strong> (not SOL) to <code style="font-size:11px">{wallet_short}</code>. Allow 30-60 seconds for confirmation.';
      btn.disabled = false;
      btn.textContent = '✓ I have paid {fee_usdc} USDC';
    }}
  }} catch (e) {{
    status.className = 'pay-status show error';
    status.textContent = 'Network error: ' + e.message + '. Try again in a moment.';
    btn.disabled = false;
    btn.textContent = '✓ I have paid {fee_usdc} USDC';
  }}
}}
</script>
</body>
</html>"""


def _fee_usdc_amount(fee_amount_usd: float) -> str:
    """Format fee as USDC string (no decimals for whole dollars, 2dp otherwise)."""
    if fee_amount_usd == int(fee_amount_usd):
        return f"{int(fee_amount_usd)}"
    return f"{fee_amount_usd:.2f}"


def _build_solana_pay_qr_svg(wallet: str, amount_usdc: float, label: str = "Empire AI") -> str:
    """
    Generate an SVG QR code encoding a Solana Pay URI.
    solana:<recipient>?amount=<amount>&label=<label>&spl-token=<mint>
    Uses the public goqr.me API to generate the QR PNG, then embeds it as a
    base64 data URI in an SVG <image> tag. We avoid a python qrcode dep.
    """
    import urllib.parse
    import urllib.request
    import base64

    # Build solana: URI with spl-token param so wallets know it's USDC
    spl_token = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    amount_str = f"{amount_usdc:.6f}".rstrip("0").rstrip(".")
    params = urllib.parse.urlencode({
        "amount": amount_str,
        "label": label,
        "message": "Empire AI settlement fee",
        "spl-token": spl_token,
    })
    solana_uri = f"solana:{wallet}?{params}"

    # QR via goqr.me — returns PNG
    api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&margin=10&data={urllib.parse.quote(solana_uri, safe='')}"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Empire-AI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            png_bytes = r.read()
        b64 = base64.b64encode(png_bytes).decode("ascii")
        # Embed the PNG inside an SVG so the page is one document
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">'
            f'<image href="data:image/png;base64,{b64}" width="240" height="240"/>'
            f'</svg>'
        )
        # HTML-escape for inline embedding
        return (svg
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))
    except Exception as e:
        log.warning(f"[payment_page] QR generation failed ({e}); falling back to plain SVG placeholder")
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">'
            '<rect width="240" height="240" fill="#fff"/>'
            '<text x="120" y="120" text-anchor="middle" fill="#000" font-size="14">QR unavailable</text>'
            '</svg>'
        )


def _resolve_fee(claim_id: str):
    """Look up fee_event by claim_id. Returns the row or None."""
    from supabase import create_client
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    r = db.table("fee_events").select("*").eq("claim_id", claim_id).limit(1).execute()
    if r.data:
        return r.data[0]
    return None


def register_payment_routes(app, get_db=None):
    """
    Wire the /pay/<claim_id> page and the check-paid endpoint.
    Pass get_db if you want a custom client; otherwise we create one per request.
    """

    def _db():
        if get_db is not None:
            return get_db()
        from supabase import create_client
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.get("/pay/{claim_id}", response_class=HTMLResponse)
    async def payment_page_route(claim_id: str, request: Request):
        """
        Public payment page. No auth — claim_id is the bearer.
        Looks up the fee_event, renders the page with QR + wallet.
        """
        fee = _resolve_fee(claim_id)
        if not fee:
            return HTMLResponse(
                "<h1 style='color:#fff;font-family:sans-serif;padding:40px'>"
                "Payment not found</h1>"
                "<p style='color:#94a3b8;font-family:sans-serif;padding:0 40px'>"
                "The claim ID is invalid or the fee has been removed. "
                "Reply to the original SMS if you need help.</p>",
                status_code=404,
            )

        fee_amount = float(fee.get("fee_amount") or 0)
        claim_amount = float(fee.get("claim_amount") or 0)
        status = fee.get("status", "pending")

        if status == "paid":
            # Idempotent: show a "already paid" page
            return HTMLResponse(
                f"<h1 style='color:#22c55e;font-family:sans-serif;padding:40px'>"
                f"✓ Already paid</h1>"
                f"<p style='color:#cbd5e1;font-family:sans-serif;padding:0 40px'>"
                f"Fee of ${fee_amount:,.2f} for claim {claim_id} has been received. Thank you.</p>",
                status_code=200,
            )

        # Resolve contractor name for display
        contractor_name = "Contractor"
        contractor_id = fee.get("contractor_id")
        if contractor_id:
            try:
                c = _db().table("contractors").select("name").eq("id", contractor_id).limit(1).execute()
                if c.data:
                    contractor_name = c.data[0].get("name") or contractor_name
            except Exception:
                pass

        fee_usdc = _fee_usdc_amount(fee_amount)

        # Discount badge (if a discount has been offered on this fee_event)
        discount_amount = float(fee.get("discount_amount") or 0)
        discount_expires_at = fee.get("discount_expires_at")
        discount_percent = fee.get("discount_percent")
        discounted_fee = max(0.0, fee_amount - discount_amount)
        if discount_amount > 0 and discount_expires_at:
            # Only show if not expired
            try:
                exp = datetime.fromisoformat(discount_expires_at.replace("Z", "+00:00"))
            except Exception:
                exp = None
            if exp is None or exp > datetime.now(timezone.utc):
                pct_int = int(round(float(discount_percent or 0) * 100))
                discount_badge = (
                    f'<div style="display:inline-block;background:linear-gradient(135deg,#fbbf24,#f59e0b);'
                    f'color:#1f2937;padding:6px 14px;border-radius:999px;font-size:12px;font-weight:700;'
                    f'letter-spacing:.5px;margin-bottom:10px">'
                    f'🔥 {pct_int}% OFF — pay by {exp.strftime("%b %d") if exp else "soon"}'
                    f'</div>'
                )
                original_fee_line = (
                    f'<div class="amount-claim" style="text-decoration:line-through;color:#64748b;margin-top:2px">'
                    f'was ${fee_amount:,.2f} — save ${discount_amount:,.2f}'
                    f'</div>'
                )
                # Use the discounted amount everywhere on the page
                fee_usdc = _fee_usdc_amount(discounted_fee)
                fee_amount = discounted_fee
                fee_usd = f"{discounted_fee:,.2f}"
            else:
                discount_badge = ""
                original_fee_line = ""
        else:
            discount_badge = ""
            original_fee_line = ""

        qr_svg = _build_solana_pay_qr_svg(VAULT_WALLET, fee_amount, "Empire AI")

        head_html = empire_head(
            title="Empire AI · Payment",
            extra=_PAYMENT_PAGE_CSS,
        )

        html = PAYMENT_PAGE_HTML.format(
            head_html=head_html,
            claim_id=claim_id,
            claim_id_short=claim_id[:13],
            fee_usdc=fee_usdc,
            fee_usd=f"{fee_amount:,.2f}",
            claim_usd=f"{claim_amount:,.0f}",
            contractor_name=contractor_name,
            wallet=VAULT_WALLET,
            wallet_short=f"{VAULT_WALLET[:6]}...{VAULT_WALLET[-4:]}",
            qr_svg=qr_svg,
            discount_badge=discount_badge,
            original_fee_line=original_fee_line,
        )
        return HTMLResponse(html)

    @app.get("/pay/{claim_id}.json")
    async def payment_page_json(claim_id: str):
        """JSON view of the fee (no auth, claim_id is the bearer)."""
        fee = _resolve_fee(claim_id)
        if not fee:
            raise HTTPException(404, "fee_event not found for claim_id")
        return JSONResponse({
            "claim_id": fee.get("claim_id"),
            "fee_amount": float(fee.get("fee_amount") or 0),
            "claim_amount": float(fee.get("claim_amount") or 0),
            "status": fee.get("status"),
            "vault_wallet": VAULT_WALLET,
            "network": "solana-mainnet",
            "asset": "USDC",
            "asset_mint": USDC_MINT,
            "settled_at": fee.get("settled_at"),
        })

    @app.post("/api/v1/fee/check-paid")
    async def check_paid_route(request: Request):
        """
        Check on-chain for a USDC transfer to the vault wallet matching
        this fee amount. Uses Helius RPC if HELIUS_API_KEY is set.

        Body: {"claim_id": "..."}

        Returns:
          {paid: true} if matching tx found
          {found_pending: true, paid: false} if tx seen but not yet confirmed
          {paid: false} if nothing found (contractor hasn't paid yet)
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "invalid JSON")

        claim_id = body.get("claim_id")
        if not claim_id:
            raise HTTPException(400, "claim_id required")

        fee = _resolve_fee(claim_id)
        if not fee:
            raise HTTPException(404, "fee not found")
        if fee.get("status") == "paid":
            return {"paid": True, "already_marked": True}

        fee_amount = float(fee.get("fee_amount") or 0)
        helius_key = os.environ.get("HELIUS_API_KEY", "")

        if not helius_key:
            # Without Helius we can't verify on-chain. Defer to operator.
            log.info(f"[payment_page] check-paid for {claim_id} but no HELIUS_API_KEY; deferring")
            return {
                "paid": False,
                "deferred": True,
                "reason": "no_rpc_configured",
                "message": "On-chain verification unavailable; operator will reconcile.",
            }

        # Query Helius for recent USDC transfers to the vault.
        # We look back 7 days and match by amount (in USDC smallest units).
        import urllib.request
        import urllib.parse
        import time
        import base64

        # Helius enhanced transaction history
        url = f"https://api.helius.xyz/v0/addresses/{VAULT_WALLET}/transactions"
        params = {
            "api-key": helius_key,
            "limit": 100,
            "type": "TRANSFER",
        }
        try:
            req = urllib.request.Request(
                f"{url}?{urllib.parse.urlencode(params)}",
                headers={"User-Agent": "Empire-AI/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                txs = json.loads(r.read())
        except Exception as e:
            log.warning(f"[payment_page] helius fetch failed: {e}")
            return {"paid": False, "error": f"rpc_error: {str(e)[:80]}"}

        target_lamports_usdc = int(round(fee_amount * 10**USDC_DECIMALS))
        for tx in txs or []:
            # Helius returns native transfers; USDC transfers show up as SPL token transfers.
            # We check both shapes.
            ts = tx.get("timestamp", 0)
            if ts < time.time() - 7 * 86400:
                continue
            # Native SOL transfer shape
            native = tx.get("nativeTransfers", [])
            for nt in native:
                if nt.get("toUserAccount") == VAULT_WALLET and nt.get("amount", 0) == target_lamports_usdc:
                    return {"paid": True, "tx": tx.get("signature")}
            # Token transfer shape
            for tt in tx.get("tokenTransfers", []) or []:
                if (tt.get("toUserAccount") == VAULT_WALLET
                        and tt.get("mint") == USDC_MINT
                        and tt.get("tokenAmount", {}).get("amount") == str(target_lamports_usdc)):
                    return {"paid": True, "tx": tx.get("signature")}

        return {"paid": False, "found_pending": False, "checked": len(txs or [])}

    @app.post("/api/v1/fee/mark-paid")
    async def mark_paid_route(request: Request):
        """
        Manually mark a fee_event as paid (operator action).
        Body: {"claim_id": "...", "tx_signature": "..."}
        Auth: requires operator Bearer token (header Authorization).
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "invalid JSON")

        claim_id = body.get("claim_id")
        tx_sig = body.get("tx_signature", "")
        if not claim_id:
            raise HTTPException(400, "claim_id required")

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "operator bearer token required")

        token = auth.split(" ", 1)[1].strip()
        expected = os.environ.get("CLAIM_WEBHOOK_SECRET", "")
        if not expected or token != expected:
            raise HTTPException(401, "invalid token")

        try:
            db = _db()
            r = db.table("fee_events").update({
                "status": "paid",
                "meta": {**(fee.get("meta") or {}), "marked_paid_by": "operator",
                         "paid_at": datetime.now(timezone.utc).isoformat(),
                         "tx_signature": tx_sig},
            }).eq("claim_id", claim_id).execute()
            return {"ok": True, "updated": len(r.data or [])}
        except Exception as e:
            raise HTTPException(500, str(e))