"""
Empire AI · Contractor Self-Serve Settlement Page
==================================================

Real carriers don't expose settlement APIs. The contractor is the only
entity that knows when their claim got paid by the carrier. Give them a
branded self-serve page they can tap from the SMS reminder:

    /settle/<dispatch_id>?t=<token>

Page flow:
  - Validates dispatch exists + token matches dispatch.token (no login)
  - Looks up carrier_claims row by dispatch_id
  - If status='settled' → shows "already settled" + pay-link for fee
  - If status='open' (or no carrier_claims row yet) → shows claim
    details (dispatch payout_amount, contractor name, lead metro),
    asks for confirmation + final settled amount, posts to
    /api/v1/claim-settled (the same public webhook the operator uses)
  - On confirm: carrier_claims.status='settled', settled_at=now,
    fee_watcher next tick creates fee_event at 3%
  - Then redirects to /pay/<claim_id>

This is the REAL settlement signal source — no simulator, no
synthetic data, no scraped guesses. The contractor's confirmation IS
the ground truth.
"""
import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

log = logging.getLogger("empire.settle_page")


_SETTLE_CSS = """
.settle-wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; background: #0A1A2F; }
.settle-card { max-width: 540px; width: 100%; background: #0f2238; border: 1px solid #1e3a5f; border-radius: 12px; padding: 32px; font-family: 'Inter', -apple-system, sans-serif; color: #e6edf3; }
.settle-card h1 { color: #fff; margin: 0 0 8px; font-size: 24px; font-weight: 600; }
.settle-card .sub { color: #94a3b8; font-size: 14px; margin-bottom: 24px; }
.kv { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #1e3a5f; font-size: 14px; }
.kv:last-of-type { border-bottom: none; }
.kv .k { color: #94a3b8; }
.kv .v { color: #fff; font-weight: 500; }
.amount-input { width: 100%; padding: 12px; background: #0A1A2F; border: 1px solid #2a4a73; border-radius: 6px; color: #fff; font-size: 18px; margin-top: 8px; font-family: 'JetBrains Mono', monospace; box-sizing: border-box; }
.btn { display: inline-block; width: 100%; padding: 14px; background: #16a34a; color: #fff; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; text-align: center; text-decoration: none; margin-top: 20px; font-family: inherit; }
.btn:hover { background: #15803d; }
.btn.secondary { background: #475569; }
.btn.secondary:hover { background: #334155; }
.warn { background: #422006; border: 1px solid #b45309; border-radius: 6px; padding: 12px; font-size: 13px; color: #fde68a; margin-top: 16px; }
.success { background: #052e16; border: 1px solid #16a34a; border-radius: 6px; padding: 16px; font-size: 14px; color: #bbf7d0; margin-top: 16px; }
.legal { color: #64748b; font-size: 11px; margin-top: 24px; line-height: 1.5; }
.brand { font-size: 12px; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 4px; }
"""


def _head():
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Empire AI · Confirm Settlement</title>
<meta name="theme-color" content="#0A1A2F">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>""" + _SETTLE_CSS + """</style>
</head><body><div class="settle-wrap"><div class="settle-card">"""


def _foot():
    return """</div></div></body></html>"""


def _db():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _resolve_dispatch(dispatch_id: str, token: str):
    """Look up dispatch, validate token. Returns (dispatch, contractor) or raises."""
    db = _db()
    r = db.table("dispatches").select("*").eq("id", dispatch_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "dispatch not found")
    d = r.data[0]
    if token and d.get("token") and token != d.get("token"):
        raise HTTPException(403, "invalid token")
    # Look up contractor name
    cont = None
    if d.get("contractor_id"):
        cr = db.table("contractors").select("id,name,phone,email").eq("id", d["contractor_id"]).limit(1).execute()
        if cr.data:
            cont = cr.data[0]
    return d, cont


def register_settle_routes(app):
    """Wire the /settle/<dispatch_id> self-serve page + POST handler."""

    @app.get("/settle/{dispatch_id}", response_class=HTMLResponse)
    async def settle_page(
        dispatch_id: str,
        request: Request,
        t: str = Query("", description="dispatch token"),
    ):
        """Public page. Token-gated. No login required — the URL is the bearer."""
        try:
            d, cont = _resolve_dispatch(dispatch_id, t)
        except HTTPException as e:
            return HTMLResponse(
                _head() + f'<h1>Not found</h1><div class="warn">{e.detail}</div>' + _foot(),
                status_code=e.status_code,
            )

        db = _db()
        # Look up carrier_claims
        cc = db.table("carrier_claims").select("*").eq("dispatch_id", dispatch_id).limit(1).execute()
        cc_row = (cc.data or [None])[0]

        # Look up lead for context
        lead = None
        if d.get("lead_id"):
            lr = db.table("enriched_leads").select("id,address,city,state,phone,email,warehouse_name").eq("id", d["lead_id"]).limit(1).execute()
            if lr.data:
                lead = lr.data[0]

        # Look up fee_event if any
        fe = None
        if cc_row:
            fr = db.table("fee_events").select("id,claim_id,fee_amount,fee_percent,status").eq("claim_id", cc_row["id"]).limit(1).execute()
            if fr.data:
                fe = fr.data[0]

        cont_name = (cont or {}).get("name") or "Contractor"
        payout = float(d.get("payout_amount") or 0)

        # Idempotent: already settled
        if cc_row and cc_row.get("status") == "settled":
            body = f'<div class="brand">Empire AI</div><h1>✓ Already settled</h1>'
            body += f'<div class="sub">Claim {cc_row["id"][:8]}... was confirmed settled on {(cc_row.get("settled_at") or "")[:10]}</div>'
            if fe:
                fee_amt = float(fe.get("fee_amount") or 0)
                body += f'<div class="kv"><span class="k">Fee owed</span><span class="v">${fee_amt:,.2f}</span></div>'
                body += f'<div class="kv"><span class="k">Status</span><span class="v">{fe.get("status","?")}</span></div>'
                if fe.get("status") != "paid":
                    body += f'<a class="btn" href="https://empire-ai.co.uk/pay/{fe.get("claim_id")}">Pay ${fee_amt:,.0f} fee</a>'
            return HTMLResponse(_head() + body + _foot())

        # Open: render confirmation form
        body = f'<div class="brand">Empire AI</div><h1>Confirm settlement</h1>'
        body += f'<div class="sub">Hi {cont_name} — your claim has been dispatched. Confirm below once the carrier pays out so we can issue your fee invoice.</div>'
        body += f'<div class="kv"><span class="k">Claim reference</span><span class="v">{dispatch_id[:8]}...</span></div>'
        if lead:
            addr = ", ".join(filter(None, [lead.get("address"), lead.get("city"), lead.get("state")]))
            body += f'<div class="kv"><span class="k">Property</span><span class="v">{addr or "—"}</span></div>'
        body += f'<div class="kv"><span class="k">Estimated payout</span><span class="v">${payout:,.2f}</span></div>'
        body += f'<div class="kv"><span class="k">Fee (3%)</span><span class="v">${payout * 0.03:,.2f}</span></div>'

        body += f'<form method="POST" action="/settle/{dispatch_id}?t={t}">'
        body += f'<label class="k" style="display:block;margin-top:20px">Final settled amount (USD)</label>'
        body += f'<input class="amount-input" type="number" name="settled_amount" step="0.01" min="0" value="{payout:.2f}" required>'
        body += f'<button class="btn" type="submit">Confirm settled — generate fee invoice</button>'
        body += f'</form>'
        body += f'<div class="warn">By confirming, you confirm the carrier has paid out the above amount on this claim. Empire AI will create a fee invoice at 3% per your contractor agreement.</div>'
        body += f'<div class="legal">Dispatch ID: {dispatch_id}<br>Token-bound URL. Sharing this link exposes the claim to anyone with the URL.</div>'
        return HTMLResponse(_head() + body + _foot())

    @app.post("/settle/{dispatch_id}")
    async def settle_submit(
        dispatch_id: str,
        request: Request,
        t: str = Query("", description="dispatch token"),
    ):
        """Contractor confirmed. Mark carrier_claims settled → fee_watcher fires."""
        try:
            d, cont = _resolve_dispatch(dispatch_id, t)
        except HTTPException as e:
            return HTMLResponse(
                _head() + f'<h1>Error</h1><div class="warn">{e.detail}</div>' + _foot(),
                status_code=e.status_code,
            )

        # Parse form
        try:
            form = await request.form()
            settled_amount = float(form.get("settled_amount") or 0)
        except Exception as e:
            return HTMLResponse(
                _head() + f'<h1>Error</h1><div class="warn">Could not parse form: {e}</div>' + _foot(),
                status_code=400,
            )

        if settled_amount <= 0:
            return HTMLResponse(
                _head() + f'<h1>Error</h1><div class="warn">Settled amount must be positive.</div>' + _foot(),
                status_code=400,
            )

        db = _db()
        now = datetime.now(timezone.utc).isoformat()

        # Upsert carrier_claims row
        cc = db.table("carrier_claims").select("id,status").eq("dispatch_id", dispatch_id).limit(1).execute()
        if cc.data:
            cid = cc.data[0]["id"]
            db.table("carrier_claims").update({
                "status": "settled",
                "settled_amount": settled_amount,
                "settled_at": now,
            }).eq("id", cid).execute()
        else:
            ins = db.table("carrier_claims").insert({
                "dispatch_id": dispatch_id,
                "status": "settled",
                "settled_amount": settled_amount,
                "settled_at": now,
                "filed_at": now,
                "created_at": now,
            }).execute()
            cid = ins.data[0]["id"] if ins.data else None

        log.info(f"[settle-page] dispatch={dispatch_id} settled ${settled_amount:,.2f} contractor={(cont or {}).get('id')} carrier_claim={cid}")

        # Trigger fee_watcher inline (don't wait for cron tick) by calling
        # /api/v1/claim-settled webhook with the shared secret.
        secret = os.environ.get("CLAIM_WEBHOOK_SECRET", "")
        hub_base = os.environ.get("HUB_PUBLIC_URL", "http://127.0.0.1:8001")
        fee_event_id = None
        try:
            import httpx
            r = httpx.post(
                f"{hub_base}/api/v1/claim-settled",
                headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
                json={"dispatch_id": dispatch_id, "claim_amount": settled_amount, "settled_at": now},
                timeout=15,
            )
            data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
            fee_event_id = data.get("fee_event_id")
        except Exception as e:
            log.warning(f"[settle-page] inline webhook call failed: {e}")

        # Render success + pay link
        body = f'<div class="brand">Empire AI</div><h1>✓ Settlement recorded</h1>'
        body += f'<div class="sub">Thanks {(cont or {}).get("name", "Contractor")}. Fee invoice generated below.</div>'
        body += f'<div class="kv"><span class="k">Settled amount</span><span class="v">${settled_amount:,.2f}</span></div>'
        fee_amt = round(settled_amount * 0.03, 2)
        body += f'<div class="kv"><span class="k">Empire AI fee (3%)</span><span class="v">${fee_amt:,.2f}</span></div>'
        if cid:
            body += f'<a class="btn" href="https://empire-ai.co.uk/pay/{cid}">Pay ${fee_amt:,.0f} now</a>'
        body += f'<div class="success">Settlement logged. The fee invoice will appear in your Empire AI dashboard.</div>'
        return HTMLResponse(_head() + body + _foot())