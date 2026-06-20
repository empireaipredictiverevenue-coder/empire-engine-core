"""
Empire AI · Fee Routes
=======================

Webhook entry point for "a claim has settled" events. The dispatcher sends
a lead to a contractor. The contractor works the claim with the homeowner.
When the claim settles, this endpoint writes a fee_events row.

Body schema (POST /api/v1/fee/claim-settled):
{
    "claim_id":       "external-claim-ref",      # required
    "contractor_id":  "<uuid>",                   # optional
    "lead_id":        "<uuid>",                   # optional
    "claim_amount":   50000.00,                   # required, USD
    "settled_at":     "2026-06-15T11:38:00Z",     # optional, defaults to now
    "source":         "carrier|webhook|operator", # optional, defaults to "webhook"
    "meta":           {...}                       # optional
}

Returns: {"ok": true, "fee_event": {...}}

Auth: HUB_TOKEN bearer (same as /api/v1/sms/enroll). Webhook callers
typically pass it as Authorization: Bearer HUB_TOKEN.

This is the simple HTTP entry point. The fee_watcher cron agent
(agents/fee_watcher/) is the equivalent polling path for the future,
when claim_events becomes a queryable table.

Usage in hub.py:
    from empire_fee import register_fee_routes
    register_fee_routes(app, require_auth=require_auth)
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request

log = logging.getLogger("empire.fee_routes")

FEE_PERCENT_DEFAULT = 0.03


def _normalize_amount(amount: Any) -> float:
    try:
        return float(amount)
    except (TypeError, ValueError):
        raise HTTPException(400, f"claim_amount must be a number, got {type(amount).__name__}")


def register_fee_routes(
    app: FastAPI,
    *,
    require_auth: Callable,
    fee_percent: float = FEE_PERCENT_DEFAULT,
    get_db: Optional[Callable] = None,
):
    """
    Wire the fee webhook endpoint. Pass a get_db callable to use a custom
    Supabase client; otherwise the function uses the default.
    """

    def _db():
        if get_db is not None:
            return get_db()
        from supabase import create_client
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.post("/api/v1/fee/claim-settled")
    async def fee_claim_settled(
        request: Request,
        auth: bool = Depends(require_auth),
    ):
        """Webhook entry point for settled-claim events. Writes a fee_events row."""
        _started_at = datetime.now(timezone.utc)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        claim_id = body.get("claim_id")
        if not claim_id:
            raise HTTPException(400, "claim_id is required")

        claim_amount = _normalize_amount(body.get("claim_amount"))
        if claim_amount <= 0:
            raise HTTPException(400, "claim_amount must be positive")

        fee = round(claim_amount * fee_percent, 2)
        contractor_id = body.get("contractor_id") or None
        lead_id = body.get("lead_id") or None
        settled_at = body.get("settled_at") or datetime.now(timezone.utc).isoformat()
        source = body.get("source") or "webhook"
        meta = body.get("meta") or {}

        # Resolve contractor contact info for meta if contractor_id provided
        if contractor_id:
            try:
                db_meta = _db()
                c_res = db_meta.table("contractors").select("name, phone, email").eq("id", contractor_id).limit(1).execute()
                if c_res.data:
                    c_data = c_res.data[0]
                    meta["contractor_name"] = c_data.get("name")
                    meta["contractor_phone"] = c_data.get("phone")
                    meta["contractor_email"] = c_data.get("email")
            except Exception:
                pass

        fee_event = {
            "claim_id": claim_id,
            "contractor_id": contractor_id,
            "lead_id": lead_id,
            "claim_amount": claim_amount,
            "fee_amount": fee,
            "fee_percent": fee_percent,
            "currency": "USD",
            "settled_at": settled_at,
            "source": source,
            "status": "pending",
            "meta": meta,
        }

        try:
            db = _db()
            r = db.table("fee_events").insert(fee_event).execute()
            inserted_id = r.data[0]["id"] if r.data else None
            log.info(f"[fee] claim-settled webhook: claim={claim_id} amount=${claim_amount} fee=${fee} contractor={contractor_id} lead={lead_id}")

            # ── Log to agent_activity for audit trail ──
            try:
                db.table("agent_activity").insert({
                    "agent_name": "claim_webhook",
                    "run_id": str(uuid.uuid4()),
                    "started_at": _started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "ok",
                    "rows_seen": 1,
                    "rows_processed": 1,
                    "rows_errored": 0,
                    "error": None,
                    "summary": f"claim_webhook: claim={claim_id} amount=${claim_amount} fee=${fee} source={source}",
                    "meta": {"claim_id": claim_id, "amount": claim_amount, "fee": fee, "contractor_id": str(contractor_id) if contractor_id else None, "source": source},
                }).execute()
            except Exception:
                pass  # non-fatal: logging failure shouldn't break the webhook response

            # ── Referral bounty check: if this is the contractor's first fee_event,
            # automatically mark any pending referral bounties as 'earned' ────
            if contractor_id and inserted_id:
                try:
                    from bots.bounty_tracker import check_bounty_eligible
                    bounty_event = dict(fee_event, id=inserted_id)
                    asyncio.create_task(check_bounty_eligible(bounty_event, db=db))
                except Exception as bounty_err:
                    log.warning(f"[fee] bounty check failed (non-fatal): {bounty_err}")

            return {
                "ok": True,
                "fee_event": {
                    "id": inserted_id,
                    **fee_event,
                },
            }
        except Exception as e:
            # Log failure to agent_activity
            try:
                db.table("agent_activity").insert({
                    "agent_name": "claim_webhook",
                    "run_id": str(uuid.uuid4()),
                    "started_at": _started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                    "rows_seen": 1,
                    "rows_processed": 0,
                    "rows_errored": 1,
                    "error": str(e)[:500],
                    "summary": f"claim_webhook ERROR: claim={claim_id} error={str(e)[:80]}",
                    "meta": {"claim_id": claim_id, "amount": claim_amount, "source": source, "error": str(e)[:500]},
                }).execute()
            except Exception:
                pass
            log.error(f"[fee] webhook insert failed: {e}")
            raise HTTPException(500, f"insert failed: {e}")

    @app.get("/api/v1/fee/list")
    async def fee_list(
        status: str = "all",
        limit: int = 50,
        auth: bool = Depends(require_auth),
    ):
        """List fee_events. Defaults to last 50. Filter by status=pending|paid|..."\
        "invoiced|cancelled."""
        try:
            db = _db()
            q = (db.table("fee_events")
                   .select("*")
                   .order("settled_at", desc=True)
                   .limit(max(1, min(limit, 500))))
            if status and status != "all":
                q = q.eq("status", status)
            return {"fees": (q.execute().data or [])}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/api/v1/fee/stats")
    async def fee_stats(auth: bool = Depends(require_auth)):
        """Rollup of fee_events: total count, total fee, by status."""
        try:
            db = _db()
            r = db.table("fee_events").select("claim_amount,fee_amount,status").limit(10000).execute()
            rows = r.data or []
            from collections import Counter
            n = len(rows)
            total_claim = sum(float(row.get("claim_amount") or 0) for row in rows)
            total_fee = sum(float(row.get("fee_amount") or 0) for row in rows)
            by_status = Counter(row.get("status") or "?" for row in rows)
            return {
                "count": n,
                "total_claim_usd": round(total_claim, 2),
                "total_fee_usd": round(total_fee, 2),
                "by_status": dict(by_status),
            }
        except Exception as e:
            raise HTTPException(500, str(e))
