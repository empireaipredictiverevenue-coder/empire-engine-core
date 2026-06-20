"""
Empire AI · Operator Mark-Claim-Settled Route
==============================================

Lightweight UI endpoint that lets the operator mark a claim as settled
without going through the full carrier integration. POSTs to the same
fee/claim-settled endpoint that real webhooks will use, so when the
carrier integration lands, the operator workflow doesn't change.

The operator SPA (empire_command_spa.py) calls this from a "Mark Settled"
button on a dispatch card. The button needs the dispatch_id, claim
amount, and optionally the contractor's claim reference number.

Body schema (POST /api/v1/fee/operator-mark-settled):
{
    "dispatch_id":   "<uuid>",          # required, the dispatches.id row
    "claim_amount":  50000.00,         # required, USD
    "claim_id":      "external-ref",    # optional, defaults to dispatch_id
    "settled_at":    "2026-06-15T...",  # optional, defaults to now
    "meta":          {...}              # optional
}

Auth: requires the same auth as the rest of the operator dashboard
(operator role via empire_auth.require_auth).

The endpoint writes a fee_events row and updates the dispatch row's
meta with the fee_event_id so the operator can trace it back.

Returns: {"ok": true, "fee_event": {...}, "dispatch_id": "<uuid>"}
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request

log = logging.getLogger("empire.fee_routes")

FEE_PERCENT_DEFAULT = 0.03


def register_operator_mark_settled(
    app: FastAPI,
    *,
    require_auth: Callable,
    fee_percent: float = FEE_PERCENT_DEFAULT,
    get_db: Optional[Callable] = None,
):
    """
    Add the operator mark-claim-settled endpoint to the hub. The endpoint
    takes a dispatch_id + claim_amount and writes a fee_events row,
    reusing the same code path as the carrier webhook.
    """

    def _db():
        if get_db is not None:
            return get_db()
        from supabase import create_client
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.post("/api/v1/fee/operator-mark-settled")
    async def operator_mark_settled(
        request: Request,
        op: dict = Depends(require_auth),
    ):
        _started_at = datetime.now(timezone.utc)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        dispatch_id = body.get("dispatch_id")
        if not dispatch_id:
            raise HTTPException(400, "dispatch_id is required")

        try:
            claim_amount = float(body.get("claim_amount"))
        except (TypeError, ValueError):
            raise HTTPException(400, "claim_amount must be a number")
        if claim_amount <= 0:
            raise HTTPException(400, "claim_amount must be positive")

        try:
            db = _db()

            # Look up the dispatch to get contractor + lead info
            dispatch_res = db.table("dispatches").select("lead_id, contractor_id, meta").eq("id", dispatch_id).limit(1).execute()
            if not dispatch_res.data:
                raise HTTPException(404, f"dispatch {dispatch_id} not found")
            dispatch = dispatch_res.data[0]

            # Find the enriched_lead for this dispatch (it's keyed on radar_target_id, not enriched_lead_id)
            radar_target_id = dispatch.get("lead_id")
            enriched_lead_id = None
            if radar_target_id:
                el_res = db.table("enriched_leads").select("id").eq("radar_target_id", radar_target_id).limit(1).execute()
                if el_res.data:
                    enriched_lead_id = el_res.data[0]["id"]

            # Resolve fee params
            claim_id = body.get("claim_id") or f"operator-{dispatch_id}"
            settled_at = body.get("settled_at") or datetime.now(timezone.utc).isoformat()
            meta = body.get("meta") or {}
            meta["marked_by"] = op.get("name") or op.get("email") or "operator"
            meta["dispatch_id"] = str(dispatch_id)
            meta["source"] = "operator_mark_settled"

            fee = round(claim_amount * fee_percent, 2)
            fee_event = {
                "claim_id": claim_id,
                "contractor_id": dispatch.get("contractor_id"),
                "lead_id": enriched_lead_id or None,
                "claim_amount": claim_amount,
                "fee_amount": fee,
                "fee_percent": fee_percent,
                "currency": "USD",
                "settled_at": settled_at,
                "source": "operator_mark_settled",
                "status": "pending",
                "meta": meta,
            }

            # Update the dispatch row FIRST (if this fails, we bail before writing a fee_event)
            existing_meta = dispatch.get("meta") or {}
            existing_meta["settled"] = True
            existing_meta["settled_at"] = settled_at
            existing_meta["claim_amount"] = claim_amount
            db.table("dispatches").update({"meta": existing_meta}).eq("id", dispatch_id).execute()

            r = db.table("fee_events").insert(fee_event).execute()
            inserted_id = r.data[0]["id"] if r.data else None

            # Backfill the fee_event_id on the dispatch
            existing_meta["fee_event_id"] = inserted_id
            try:
                db.table("dispatches").update({"meta": existing_meta}).eq("id", dispatch_id).execute()
            except Exception as backfill_err:
                log.warning(f"[fee] operator-mark-settled: failed to backfill fee_event_id on dispatch {dispatch_id}: {backfill_err}")

            log.info(f"[fee] operator-mark-settled: dispatch={dispatch_id} amount=${claim_amount} fee=${fee} contractor={dispatch.get('contractor_id')} lead={enriched_lead_id}")

            # ── Log to agent_activity for audit trail ──
            try:
                db.table("agent_activity").insert({
                    "agent_name": "operator_mark_settled",
                    "run_id": str(uuid.uuid4()),
                    "started_at": _started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "ok",
                    "rows_seen": 1,
                    "rows_processed": 1,
                    "rows_errored": 0,
                    "error": None,
                    "summary": f"operator-mark-settled: dispatch={dispatch_id} amount=${claim_amount} fee=${fee} contractor={dispatch.get('contractor_id')}",
                    "meta": {"dispatch_id": dispatch_id, "amount": claim_amount, "fee": fee, "contractor_id": str(dispatch.get('contractor_id')) if dispatch.get('contractor_id') else None, "claim_id": claim_id},
                }).execute()
            except Exception:
                pass  # non-fatal: logging failure shouldn't break the response

            # ── Referral bounty check: if this is the contractor's first fee_event,
            # automatically mark any pending referral bounties as 'earned' ────
            if dispatch.get("contractor_id") and inserted_id:
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
                "dispatch_id": dispatch_id,
            }
        except HTTPException:
            raise
        except Exception as e:
            # Log failure to agent_activity
            try:
                db.table("agent_activity").insert({
                    "agent_name": "operator_mark_settled",
                    "run_id": str(uuid.uuid4()),
                    "started_at": _started_at.isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                    "rows_seen": 1,
                    "rows_processed": 0,
                    "rows_errored": 1,
                    "error": str(e)[:500],
                    "summary": f"operator-mark-settled ERROR: dispatch={dispatch_id} error={str(e)[:80]}",
                    "meta": {"dispatch_id": dispatch_id, "amount": claim_amount, "error": str(e)[:500]},
                }).execute()
            except Exception:
                pass
            log.error(f"[fee] operator-mark-settled failed: {e}")
            raise HTTPException(500, f"failed: {e}")
