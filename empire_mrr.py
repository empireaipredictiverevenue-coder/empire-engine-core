"""
Empire AI · MRR Routes
=========================

Registers subscription + dispatch-invoice endpoints into the hub.

Subscription (Streamflow-style monthly USDC):
  POST /api/v1/subscribe/activate   {contractor_id, wallet, tier}
  POST /api/v1/subscribe/cancel     {contractor_id}
  POST /api/v1/subscribe/verify     {contractor_id}
  GET  /api/v1/subscribe/me         ?contractor_id=
  GET  /api/v1/subscribe/tiers      (public, returns pricing table)

Dispatch invoicing (pay-per-lead USDC):
  POST /api/v1/dispatch/invoice     {contractor_id, dispatch_id, niche, outreach_type}
  POST /api/v1/dispatch/invoice/check  {invoice_id}
  GET  /api/v1/dispatch/invoice/list   ?contractor_id=
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from fastapi import Request
from fastapi.responses import JSONResponse
from supabase import create_client

from empire_subscription import (
    activate_subscription, verify_subscription, cancel_subscription,
    get_subscription, expire_lapsed,
)
from empire_dispatch_invoice import (
    create_invoice, check_all_unpaid, mark_invoice_paid,
    price_for_dispatch, VAULT_WALLET,
)

log = logging.getLogger("mrr_routes")


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _resolve_contractor(phone: str = "", email: str = "") -> dict:
    """Resolve a contractor by phone or email. Returns {id, name} or error dict."""
    sb = _sb()
    if phone:
        # Normalize phone: strip non-digits, add + prefix
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) == 10:
            phone_norm = "+1" + digits
        elif len(digits) == 11 and digits.startswith("1"):
            phone_norm = "+" + digits
        else:
            phone_norm = phone if phone.startswith("+") else "+" + phone
        r = sb.table("contractors").select("id,name").eq("phone", phone_norm).limit(1).execute()
        if r.data:
            return {"ok": True, "id": r.data[0]["id"], "name": r.data[0].get("name", "") or ""}
    if email:
        r = sb.table("contractors").select("id,name").eq("email", email.strip().lower()).limit(1).execute()
        if r.data:
            return {"ok": True, "id": r.data[0]["id"], "name": r.data[0].get("name", "") or ""}
    return {"ok": False, "error": "No contractor found with that phone or email. Make sure the number matches what we have on file."}


def register_mrr_routes(app, require_auth=None, get_db=None):
    @app.get("/api/v1/subscribe/tiers")
    async def list_tiers():
        sb = _sb()
        r = sb.table("subscription_tiers").select("*").eq("active", True).order("sort_order").execute()
        return JSONResponse({"tiers": r.data or [], "vault_wallet": VAULT_WALLET})

    @app.post("/api/v1/subscribe/activate")
    async def subscribe_activate(request: Request, auth: bool = False if require_auth is None else None):
        # Accept either token auth (legacy require_auth) or open (auth=False from monkey patch)
        if require_auth is not None:
            try:
                await require_auth(request)
            except Exception:
                return JSONResponse({"detail": "auth required"}, status_code=401)
        body = await request.json()
        cid = body.get("contractor_id")
        phone = body.get("phone", "")
        email = body.get("email", "")
        wallet = body.get("wallet")
        tier = body.get("tier", "basic")
        # Resolve contractor by phone/email if no direct contractor_id
        if not cid:
            resolved = _resolve_contractor(phone=phone, email=email)
            if not resolved.get("ok"):
                return JSONResponse(resolved, status_code=404)
            cid = resolved["id"]
        if not cid or not wallet:
            return JSONResponse({"detail": "Phone/email + wallet required"}, status_code=400)
        result = activate_subscription(cid, wallet, tier)
        # Attribution: if the activation came from an outreach email,
        # mark that outreach row as paid-driven.
        outreach_id = body.get("outreach_id")
        if result.get("ok") and outreach_id:
            try:
                sb = _sb()
                sb.table("contractor_outreach").update({
                    "paid_at": datetime.now(timezone.utc).isoformat(),
                    "notes": "clicked /for-contractors + activated subscription",
                }).eq("id", outreach_id).execute()
                result["attributed_to"] = outreach_id
            except Exception as _ae:
                log.warning(f"[mrr] outreach attribution failed: {_ae}")
        if not result.get("ok"):
            return JSONResponse(result, status_code=400)
        # Attach resolved info so the frontend can use it
        result["contractor_id"] = cid
        # Look up the contractor name for a personalized response
        try:
            _cr = _sb().table("contractors").select("name").eq("id", cid).limit(1).execute()
            if _cr.data and _cr.data[0].get("name"):
                result["contractor_name"] = _cr.data[0]["name"]
        except Exception:
            pass
        return JSONResponse(result)

    @app.post("/api/v1/subscribe/verify")
    async def subscribe_verify(request: Request):
        if require_auth is not None:
            try:
                await require_auth(request)
            except Exception:
                return JSONResponse({"detail": "auth required"}, status_code=401)
        body = await request.json()
        cid = body.get("contractor_id")
        if not cid:
            return JSONResponse({"detail": "contractor_id required"}, status_code=400)
        return JSONResponse(await verify_subscription(cid))

    @app.post("/api/v1/subscribe/cancel")
    async def subscribe_cancel(request: Request):
        if require_auth is not None:
            try:
                await require_auth(request)
            except Exception:
                return JSONResponse({"detail": "auth required"}, status_code=401)
        body = await request.json()
        cid = body.get("contractor_id")
        if not cid:
            return JSONResponse({"detail": "contractor_id required"}, status_code=400)
        return JSONResponse(cancel_subscription(cid))

    @app.get("/api/v1/subscribe/me")
    async def subscribe_me(request: Request, contractor_id: str):
        return JSONResponse(get_subscription(contractor_id))

    # ── dispatch invoicing ────────────────────────────────────────────

    @app.post("/api/v1/dispatch/invoice")
    async def create_dispatch_invoice(request: Request):
        if require_auth is not None:
            try:
                await require_auth(request)
            except Exception:
                return JSONResponse({"detail": "auth required"}, status_code=401)
        body = await request.json()
        required = ["contractor_id", "dispatch_id", "niche"]
        for r in required:
            if not body.get(r):
                return JSONResponse({"detail": f"{r} required"}, status_code=400)
        result = create_invoice(
            body["contractor_id"], body["dispatch_id"],
            body["niche"], body.get("outreach_type", "call"),
            body.get("memo"),
        )
        if result.get("skipped"):
            return JSONResponse(result)
        return JSONResponse(result)

    @app.post("/api/v1/dispatch/invoice/check")
    async def check_dispatch_invoice(request: Request):
        # Check a single invoice on-chain. Cron does bulk.
        body = await request.json()
        invoice_id = body.get("invoice_id")
        if not invoice_id:
            return JSONResponse({"detail": "invoice_id required"}, status_code=400)
        sb = _sb()
        inv = sb.table("dispatch_invoices").select("id,contractor_id,amount_usdc,status").eq("id", invoice_id).limit(1).execute().data
        if not inv:
            return JSONResponse({"detail": "not found"}, status_code=404)
        if inv[0]["status"] != "unpaid":
            return JSONResponse({"ok": True, "already_paid": True, "status": inv[0]["status"]})
        from empire_dispatch_invoice import check_invoice_payment
        cont = sb.table("contractors").select("solana_wallet").eq("id", inv[0]["contractor_id"]).limit(1).execute().data
        wallet = cont[0].get("solana_wallet") if cont else None
        if not wallet:
            return JSONResponse({"ok": False, "error": "contractor has no wallet on file"})
        import asyncio
        from datetime import timedelta
        since_ts = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        r = asyncio.run(check_invoice_payment(wallet, float(inv[0]["amount_usdc"]), since_ts))
        if r.get("verified"):
            mark_invoice_paid(invoice_id, r["tx_sig"], r["amount_usdc"])
            return JSONResponse({"ok": True, "verified": True, "tx_sig": r["tx_sig"]})
        return JSONResponse({"ok": True, "verified": False, "received": r.get("amount_usdc", 0)})

    @app.post("/api/v1/dispatch/invoice/check-all")
    async def check_all_dispatch_invoices(request: Request):
        if require_auth is not None:
            try:
                await require_auth(request)
            except Exception:
                return JSONResponse({"detail": "auth required"}, status_code=401)
        return JSONResponse(check_all_unpaid())

    @app.get("/api/v1/dispatch/invoice/list")
    async def list_dispatch_invoices(request: Request, contractor_id: str, status: str = None):
        sb = _sb()
        q = sb.table("dispatch_invoices").select("*").eq("contractor_id", contractor_id).order("created_at", desc=True).limit(50)
        if status:
            q = q.eq("status", status)
        return JSONResponse({"invoices": q.execute().data or []})

    @app.post("/api/v1/subscribe/expire-lapsed")
    async def api_expire_lapsed(request: Request):
        if require_auth is not None:
            try:
                await require_auth(request)
            except Exception:
                return JSONResponse({"detail": "auth required"}, status_code=401)
        return JSONResponse(expire_lapsed())

    log.info("[mrr] routes registered: /api/v1/subscribe/* + /api/v1/dispatch/invoice/*")