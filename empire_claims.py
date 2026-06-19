"""
Empire AI · Carrier Claims Routes
=================================

Endpoints for managing the carrier_claims table — the operational
claim tracking layer that sits between dispatch and fee_events.

POST /api/v1/claims/mark-settled — Operator marks a claim as settled
  Body: { dispatch_id, settled_amount, loss_description?, settled_at? }
  Updates carrier_claims.status='settled' and settled_amount.
  The fee_watcher cron agent then picks this up to create fee_events.

GET /api/v1/claims/list — List carrier_claims (with optional status filter)
"""
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request

log = logging.getLogger("empire.claims_routes")


def register_claims_routes(
    app: FastAPI,
    *,
    require_auth: Callable,
    get_db: Optional[Callable] = None,
):
    """Wire the carrier claims endpoints to the hub."""

    def _db():
        if get_db is not None:
            return get_db()
        from supabase import create_client
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.post("/api/v1/claims/mark-settled")
    async def claims_mark_settled(
        request: Request,
        op: dict = Depends(require_auth),
    ):
        """Mark a carrier_claim as settled. The fee_watcher picks this up
        on its next cron tick and creates the fee_event.

        Body:
            dispatch_id: str (required) — the dispatches.id to look up
            settled_amount: float (required) — the settlement amount in USD
            loss_description: str (optional) — claim details
            settled_at: str (optional) — ISO timestamp, defaults to now
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        dispatch_id = body.get("dispatch_id")
        if not dispatch_id:
            raise HTTPException(400, "dispatch_id is required")

        try:
            # Accept both settled_amount and claim_amount (SPA backward compat)
            settled_amount = float(body.get("settled_amount") or body.get("claim_amount", 0))
        except (TypeError, ValueError):
            raise HTTPException(400, "settled_amount (or claim_amount) must be a number")
        if settled_amount <= 0:
            raise HTTPException(400, "settled_amount must be positive")

        try:
            db = _db()

            # Find the carrier_claims row by dispatch_id
            r = db.table("carrier_claims").select("id, dispatch_id, status").eq("dispatch_id", dispatch_id).limit(1).execute()
            if not r.data:
                # No carrier_claims row yet — create one
                loss_description = body.get("loss_description", "")
                settled_at = body.get("settled_at") or datetime.now(timezone.utc).isoformat()

                # Look up dispatch for loss_description context
                try:
                    dr = db.table("dispatches").select("lead_id, meta").eq("id", dispatch_id).limit(1).execute()
                except Exception:
                    dr = type("obj", (), {"data": None})()

                insert_row = {
                    "dispatch_id": dispatch_id,
                    "status": "settled",
                    "loss_description": loss_description,
                    "settled_amount": settled_amount,
                    "settled_at": settled_at,
                    "filed_at": settled_at,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                inserted = db.table("carrier_claims").insert(insert_row).execute()
                claim_row = inserted.data[0] if inserted.data else None
                claim_id = claim_row["id"] if claim_row else None

                log.info(
                    f"[claims] created + settled carrier_claim for dispatch {dispatch_id}: "
                    f"amount=${settled_amount} claim_id={claim_id}"
                )
            else:
                claim_row = r.data[0]
                claim_id = claim_row["id"]

                # Update existing row
                settled_at = body.get("settled_at") or datetime.now(timezone.utc).isoformat()
                updates = {
                    "status": "settled",
                    "settled_amount": settled_amount,
                    "settled_at": settled_at,
                }
                if body.get("loss_description"):
                    updates["loss_description"] = body["loss_description"]

                db.table("carrier_claims").update(updates).eq("id", claim_id).execute()

                log.info(
                    f"[claims] marked carrier_claim {claim_id} settled: "
                    f"dispatch={dispatch_id} amount=${settled_amount}"
                )

            return {
                "ok": True,
                "claim_id": str(claim_id) if claim_id else None,
                "dispatch_id": dispatch_id,
                "settled_amount": settled_amount,
                "next": "fee_watcher will create fee_event on next cron tick",
            }

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[claims] mark-settled failed: {e}")
            raise HTTPException(500, f"failed: {e}")

    @app.get("/api/v1/claims/list")
    async def claims_list(
        status: str = "all",
        limit: int = 50,
        auth: bool = Depends(require_auth),
    ):
        """List carrier_claims. Filter by status=open|settled|closed. Defaults to last 50."""
        try:
            db = _db()
            q = (db.table("carrier_claims")
                   .select("*")
                   .order("created_at", desc=True)
                   .limit(max(1, min(limit, 500))))
            if status and status != "all":
                q = q.eq("status", status)
            return {"claims": (q.execute().data or [])}
        except Exception as e:
            raise HTTPException(500, str(e))
