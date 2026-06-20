"""
Empire AI · Claim-Settled Webhook
===================================

Public webhook endpoint that external systems (contractors, carrier
adjusters, or the operator's settlement pipeline) can POST to when a
claim settles. Automatically creates the fee_event at 3% of the claim
amount and updates the dispatch record.

Unlike /api/v1/fee/operator-mark-settled (which requires an operator
session), this endpoint authenticates via a shared secret API key so
external systems can call it without a dashboard session.

Auth:
  Header:  Authorization: Bearer <CLAIM_WEBHOOK_SECRET>
  (the secret is set via the CLAIM_WEBHOOK_SECRET env var)

POST /api/v1/claim-settled
  Body:
    dispatch_id:   str (required) — UUID of the dispatches row
    claim_amount:  float (required) — settlement amount in USD
    claim_id:      str (optional) — external claim reference number
    settled_at:    str (optional) — ISO 8601 timestamp, defaults to now
    loss_description: str (optional) — brief claim summary
    meta:          dict (optional) — additional metadata

  Returns:
    { ok: true, fee_event_id: "<uuid>", fee_amount: 3750.0,
      claim_amount: 125000.0, fee_percent: 0.03 }
    or
    { ok: false, error: "..." } on failure

Env vars:
    CLAIM_WEBHOOK_SECRET — shared secret for API key auth.
        If not set, the endpoint returns 503 with "not configured".
    NTFY_TOPIC / NTFY_TOKEN — optional ntfy alert on new settlements.

Usage example:
    curl -X POST https://empire-ai.co.uk/api/v1/claim-settled \
      -H "Authorization: Bearer $CLAIM_WEBHOOK_SECRET" \
      -H "Content-Type: application/json" \
      -d '{"dispatch_id": "<uuid>", "claim_amount": 125000}'
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request

log = logging.getLogger("empire.claim_webhook")

FEE_PERCENT = 0.03


def register_claim_webhook(
    app: FastAPI,
    *,
    get_db: Callable,
    broadcaster: Optional[Callable] = None,
):
    """Register the public claim-settled webhook endpoint.

    Args:
        app: FastAPI app to register the route on.
        get_db: Callable that returns a Supabase client.
        broadcaster: Optional LiveBroadcaster for real-time dashboard pushes.
    """
    secret = os.environ.get("CLAIM_WEBHOOK_SECRET", "")

    if secret:
        log.info("[claim-webhook] Secret configured — endpoint will be active")
    else:
        log.warning(
            "[claim-webhook] CLAIM_WEBHOOK_SECRET not set — "
            "endpoint will return 503 until configured"
        )

    # Import the per-carrier key verifier
    try:
        from empire_carrier_enrollment import _verify_carrier_api_key
    except ImportError:
        _verify_carrier_api_key = None
        log.warning("[claim-webhook] carrier_enrollment module not available — per-carrier keys disabled")

    async def _verify_webhook_secret(request: Request) -> (bool, dict):
        """Validate the shared secret or per-carrier API key from Authorization header.
        Returns (is_valid, enrollment_info).
        """
        auth_header = request.headers.get("authorization", "")
        token = auth_header
        if token.lower().startswith("bearer "):
            token = token[7:]
        token = token.strip()

        if not token:
            return False, {}

        # Check master secret first (fast path)
        if secret and token == secret:
            return True, {"id": "master", "carrier_name": "Master Key"}

        # Check per-carrier API keys
        if _verify_carrier_api_key:
            enrollment = _verify_carrier_api_key(token)
            if enrollment:
                return True, enrollment

        return False, {}

    async def _send_ntfy(message: str, title: str, priority: str = "high"):
        """Send an ntfy notification if configured."""
        topic = os.environ.get("NTFY_TOPIC", "")
        token = os.environ.get("NTFY_TOKEN", "")
        if not topic:
            return
        try:
            headers = {
                "Title": title,
                "Priority": priority,
                "Tags": "moneybag",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post(
                    f"https://ntfy.sh/{topic}",
                    data=message,
                    headers=headers,
                )
        except Exception as e:
            log.debug(f"[claim-webhook] ntfy send failed: {e}")

    @app.post("/api/v1/claim-settled")
    async def claim_settled_webhook(request: Request):
        """
        Public webhook for external systems to report a settled claim.

        Creates a fee_events row and updates the dispatch record.
        No operator session required — uses shared API key auth.
        """
        _started_at = datetime.now(timezone.utc)
        # ── Auth check ────────────────────────────────────────────
        is_valid, enrollment = await _verify_webhook_secret(request)
        if not is_valid:
            if not secret:
                raise HTTPException(
                    503,
                    "CLAIM_WEBHOOK_SECRET not configured on server",
                )
            raise HTTPException(401, "Invalid or missing Authorization token")

        # Track which carrier (enrollment) sent this webhook
        carrier_name = enrollment.get("carrier_name", "Unknown")

        # ── Parse body ────────────────────────────────────────────
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        if not isinstance(body, dict):
            raise HTTPException(400, "Body must be a JSON object")

        dispatch_id = (body.get("dispatch_id") or "").strip()
        if not dispatch_id:
            raise HTTPException(400, "dispatch_id is required")

        try:
            claim_amount = float(body.get("claim_amount") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "claim_amount must be a number")
        if claim_amount <= 0:
            raise HTTPException(400, "claim_amount must be positive")
        if claim_amount > 100_000_000:
            raise HTTPException(400, "claim_amount exceeds $100M maximum")

        claim_id = (body.get("claim_id") or "").strip() or None
        settled_at = body.get("settled_at") or datetime.now(timezone.utc).isoformat()
        loss_description = (body.get("loss_description") or "").strip()
        meta = body.get("meta") or {}

        # ── Process ──────────────────────────────────────────────
        try:
            db = get_db()

            # Look up the dispatch
            dispatch_res = (
                db.table("dispatches")
                .select("contractor_id, lead_id, meta, status")
                .eq("id", dispatch_id)
                .limit(1)
                .execute()
            )
            if not dispatch_res.data:
                raise HTTPException(
                    404, f"Dispatch {dispatch_id} not found"
                )
            dispatch = dispatch_res.data[0]

            # Check dispatch isn't already settled
            dispatch_meta = dispatch.get("meta") or {}
            if isinstance(dispatch_meta, str):
                dispatch_meta = {}
            if dispatch_meta.get("settled"):
                log.info(
                    f"[claim-webhook] dispatch {dispatch_id} already "
                    f"settled — returning existing fee_event"
                )
                existing_fee_id = dispatch_meta.get("fee_event_id")
                if existing_fee_id:
                    return {
                        "ok": True,
                        "already_settled": True,
                        "fee_event_id": existing_fee_id,
                        "fee_amount": None,
                        "claim_amount": None,
                        "fee_percent": FEE_PERCENT,
                        "message": f"Dispatch {dispatch_id} already settled",
                    }

            # Resolve contractor_id
            contractor_id = dispatch.get("contractor_id")

            # Resolve lead_id (dispatch.lead_id is radar_targets.id;
            # we want enriched_leads.id)
            lead_id_raw = dispatch.get("lead_id")
            enriched_lead_id = None
            if lead_id_raw:
                try:
                    el_res = (
                        db.table("enriched_leads")
                        .select("id")
                        .eq("radar_target_id", lead_id_raw)
                        .limit(1)
                        .execute()
                    )
                    if el_res.data:
                        enriched_lead_id = el_res.data[0]["id"]
                except Exception:
                    pass

            # Generate a claim_id if none provided
            if not claim_id:
                claim_id = f"webhook-{dispatch_id}"

            # Build fee event
            fee = round(claim_amount * FEE_PERCENT, 2)
            combined_meta = {
                **(meta or {}),
                "webhook_source": True,
                "dispatch_id": str(dispatch_id),
                "loss_description": loss_description or None,
            }

            fee_event = {
                "claim_id": claim_id,
                "contractor_id": contractor_id,
                "lead_id": enriched_lead_id,
                "claim_amount": claim_amount,
                "fee_amount": fee,
                "fee_percent": FEE_PERCENT,
                "currency": "USD",
                "settled_at": settled_at,
                "source": "claim_webhook",
                "status": "pending",
                "meta": combined_meta,
            }

            # Write fee_events row
            r = db.table("fee_events").insert(fee_event).execute()
            inserted_id = r.data[0]["id"] if r.data else None

            # Update dispatch meta with fee_event_id + settled flag
            dispatch_meta["settled"] = True
            dispatch_meta["settled_at"] = settled_at
            dispatch_meta["claim_amount"] = claim_amount
            dispatch_meta["fee_amount"] = fee
            dispatch_meta["fee_event_id"] = inserted_id
            try:
                db.table("dispatches").update(
                    {"meta": dispatch_meta}
                ).eq("id", dispatch_id).execute()
            except Exception as backfill_err:
                log.warning(
                    f"[claim-webhook] dispatch meta backfill failed "
                    f"for {dispatch_id}: {backfill_err}"
                )

            # Create carrier_claims row for audit trail
            try:
                db.table("carrier_claims").insert({
                    "dispatch_id": dispatch_id,
                    "status": "settled",
                    "loss_description": loss_description or "Claim settled via webhook",
                    "settled_amount": claim_amount,
                    "settled_at": settled_at,
                    "filed_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as cc_err:
                log.warning(
                    f"[claim-webhook] carrier_claims insert failed: {cc_err}"
                )

            # ── Broadcast to live dashboard ─────────────────────
            if broadcaster:
                try:
                    await broadcaster.broadcast({
                        "type": "claim_settled",
                        "fee_event_id": inserted_id,
                        "dispatch_id": dispatch_id,
                        "claim_amount": claim_amount,
                        "fee_amount": fee,
                        "settled_at": settled_at,
                    })
                except Exception:
                    pass

            # ── ntfy alert ──────────────────────────────────────
            contractor_name = None
            try:
                if contractor_id:
                    c_res = (
                        db.table("contractors")
                        .select("name")
                        .eq("id", contractor_id)
                        .limit(1)
                        .execute()
                    )
                    if c_res.data:
                        contractor_name = c_res.data[0].get("name")
            except Exception:
                pass

            contractor_label = (
                f" ({contractor_name})" if contractor_name else ""
            )
            await _send_ntfy(
                message=(
                    f"Claim settled via webhook\n"
                    f"Dispatch: {dispatch_id[:12]}...\n"
                    f"Amount: ${claim_amount:,.2f}\n"
                    f"Fee (3%): ${fee:,.2f}\n"
                    f"Contractor: {contractor_id[:12] if contractor_id else 'N/A'}...{contractor_label}\n"
                    f"Claim ref: {claim_id[:40]}..."
                ),
                title=f"💰 ${fee:,.0f} fee event created",
            )

            # Update enrollment last_used_at
            if enrollment.get("id") and enrollment["id"] != "master":
                try:
                    db.table("carrier_enrollments").update({
                        "last_used_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", enrollment["id"]).execute()
                except Exception as touch_err:
                    log.debug(f"[claim-webhook] enrollment touch failed: {touch_err}")

            log.info(
                f"[claim-webhook] dispatch={dispatch_id} "
                f"amount=${claim_amount} fee=${fee} "
                f"contractor={contractor_id} "
                f"carrier={carrier_name} "
                f"fee_event={inserted_id}"
            )

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
                    "summary": f"claim_webhook: dispatch={dispatch_id} amount=${claim_amount} fee=${fee} carrier={carrier_name}",
                    "meta": {"dispatch_id": dispatch_id, "amount": claim_amount, "fee": fee, "claim_id": claim_id, "carrier": carrier_name, "contractor_id": str(contractor_id) if contractor_id else None},
                }).execute()
            except Exception:
                pass  # non-fatal: logging failure shouldn't break the response

            # ── Referral bounty check ────────────────────────────
            if contractor_id and inserted_id:
                try:
                    from bots.bounty_tracker import check_bounty_eligible

                    bounty_event = dict(fee_event, id=inserted_id)
                    asyncio.create_task(
                        check_bounty_eligible(bounty_event, db=db)
                    )
                except Exception as bounty_err:
                    log.warning(
                        f"[claim-webhook] bounty check failed "
                        f"(non-fatal): {bounty_err}"
                    )

            return {
                "ok": True,
                "fee_event_id": inserted_id,
                "fee_amount": fee,
                "claim_amount": claim_amount,
                "fee_percent": FEE_PERCENT,
                "dispatch_id": dispatch_id,
                "claim_id": claim_id,
            }

        except HTTPException:
            raise
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
                    "summary": f"claim_webhook ERROR: dispatch={dispatch_id} error={str(e)[:80]}",
                    "meta": {"dispatch_id": dispatch_id, "amount": claim_amount, "carrier": carrier_name, "error": str(e)[:500]},
                }).execute()
            except Exception:
                pass
            log.error(f"[claim-webhook] processing failed: {e}")
            raise HTTPException(
                500, f"Failed to process claim settlement: {str(e)[:200]}"
            )
