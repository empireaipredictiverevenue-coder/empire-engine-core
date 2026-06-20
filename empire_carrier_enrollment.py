"""
Empire AI · Carrier Webhook Enrollment
========================================

Self-service enrollment system for insurance carriers to register
for claim-settled webhook access.

Each enrollment creates a unique API key that the carrier uses to
authenticate POST /api/v1/claim-settled. The system supports both:

  1. **Per-carrier API keys** (stored in carrier_enrollments table)
  2. **Master API key** (CLAIM_WEBHOOK_SECRET env var, backwards compat)

Endpoints:
  POST   /api/v1/carrier/enroll              — self-service enrollment
  GET    /api/v1/carrier/enrollments          — list enrollments (operator)
  GET    /api/v1/carrier/enrollments/{id}     — get enrollment (operator)
  POST   /api/v1/carrier/enrollments/{id}/revoke  — revoke key (operator)
  POST   /api/v1/carrier/test-webhook         — test webhook endpoint
  GET    /api/v1/carrier/enrollment-instructions  — public docs

Env vars:
  CLAIM_WEBHOOK_SECRET — master shared secret (backwards compat)
  CARRIER_ENROLLMENT_OPEN — set to "true" to allow open self-service
                           enrollment (default: false, operator-only)

Usage (carrier self-service):
  curl -X POST https://empire-ai.co.uk/api/v1/carrier/enroll \\
    -H "Content-Type: application/json" \\
    -d '{
      "carrier_name": "Allstate",
      "contact_name": "Jane Doe",
      "contact_email": "jane@allstate.com",
      "contact_phone": "+12145551234"
    }'

  Response:
    {
      "ok": true,
      "enrollment": {
        "id": "<uuid>",
        "carrier_name": "Allstate",
        "api_key": "<generated-api-key>",
        "status": "active",
        "webhook_url": "https://empire-ai.co.uk/api/v1/claim-settled",
        "instructions": "..."
      }
    }

  The carrier then uses the api_key as:
    Authorization: Bearer <api_key>
"""

import logging
import os
import uuid
import json
import secrets
import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from supabase import create_client

log = logging.getLogger("empire.carrier_enrollment")

# Char length of generated API keys
API_KEY_BYTES = 32  # 64 hex chars


def _db():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _generate_api_key() -> str:
    """Generate a cryptographically random API key prefixed for identification.
    Format: cem_<64-hex-chars>  (cem = carrier enrollment management)
    """
    raw = secrets.token_hex(API_KEY_BYTES)
    return f"cem_{raw}"


def _hash_api_key(api_key: str) -> str:
    """Hash an API key for lookup. We store a hash, not the raw key,
    so leaked DB dumps don't expose carrier credentials.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def _verify_carrier_api_key(api_key: str) -> Optional[dict]:
    """Check an API key against the carrier_enrollments table.
    Returns the enrollment row if valid and active, None otherwise.

    Also checks the master CLAIM_WEBHOOK_SECRET for backwards compat.
    """
    # Check master secret first (fast path, no DB call)
    master_secret = os.environ.get("CLAIM_WEBHOOK_SECRET", "")
    if master_secret and api_key == master_secret:
        return {
            "id": "master",
            "carrier_name": "Master Key",
            "api_key_active": True,
            "status": "active",
        }

    # Check per-carrier keys via hash lookup
    try:
        key_hash = _hash_api_key(api_key)
        sb = _db()
        r = (
            sb.table("carrier_enrollments")
            .select("*")
            .eq("api_key", key_hash)
            .limit(1)
            .execute()
        )
        if r.data:
            enrollment = r.data[0]
            if enrollment.get("status") != "active":
                return None
            if not enrollment.get("api_key_active", True):
                return None
            return enrollment
    except Exception as e:
        log.warning(f"[carrier-enrollment] key lookup failed: {e}")

    return None


def _build_instructions(carrier_name: str, api_key: str) -> str:
    """Return formatted webhook integration instructions for a carrier."""
    webhook_url = "https://empire-ai.co.uk/api/v1/claim-settled"
    return f"""# {carrier_name} — Empire AI Webhook Integration

## Endpoint
POST {webhook_url}

## Authentication
Authorization: Bearer {api_key}

## Request Format
```json
{{
  "dispatch_id": "<UUID from Empire AI dispatch>",
  "claim_amount": 125000.00,
  "claim_id": "<your internal claim reference>",
  "settled_at": "2026-06-19T14:00:00+00:00",
  "loss_description": "Hail damage to roof and gutters"
}}
```

## Required Fields
- **dispatch_id**: The dispatch UUID provided by Empire AI when a lead was assigned
- **claim_amount**: Settlement amount in USD (positive number, max $100M)

## Optional Fields
- **claim_id**: Your internal claim reference number (stored in our ledger)
- **settled_at**: ISO 8601 timestamp of settlement (defaults to now)
- **loss_description**: Brief description of the claim

## Response
```json
{{
  "ok": true,
  "fee_event_id": "<uuid>",
  "fee_amount": 3750.00,
  "claim_amount": 125000.00,
  "fee_percent": 0.03,
  "dispatch_id": "<uuid>",
  "claim_id": "<your claim id>"
}}
```

## Testing
POST https://empire-ai.co.uk/api/v1/carrier/test-webhook
Same auth. Body:
```json
{{
  "dispatch_id": "<a real dispatch UUID>",
  "claim_amount": 1000
}}
```
This sends a test $1,000 claim. The fee will be $30 (3%).
"""


def register_carrier_enrollment_routes(
    app: FastAPI,
    *,
    require_auth: callable = None,
):
    """Register carrier enrollment routes."""

    enrollment_open = os.environ.get("CARRIER_ENROLLMENT_OPEN", "").lower() in (
        "true",
        "1",
        "yes",
    )

    # ── PUBLIC: Self-service enrollment ──────────────────────────
    @app.post("/api/v1/carrier/enroll")
    async def carrier_enroll(request: Request):
        """
        Self-service enrollment for insurance carriers.

        If CARRIER_ENROLLMENT_OPEN=true, any carrier can enroll without
        operator approval. Otherwise, this endpoint still works but the
        enrollment is created with status='pending' and requires operator
        approval via the management endpoints.
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        carrier_name = (body.get("carrier_name") or "").strip()
        if not carrier_name:
            raise HTTPException(400, "carrier_name is required")

        if len(carrier_name) > 200:
            raise HTTPException(400, "carrier_name must be 200 characters or less")

        contact_name = (body.get("contact_name") or "").strip()[:160] or None
        contact_email = (body.get("contact_email") or "").strip()[:200] or None
        contact_phone = (body.get("contact_phone") or "").strip()[:30] or None

        if not contact_email and not contact_phone:
            raise HTTPException(
                400,
                "Either contact_email or contact_phone is required",
            )

        # Generate API key
        api_key = _generate_api_key()
        api_key_hash = _hash_api_key(api_key)

        status = "active" if enrollment_open else "pending"

        # Store in DB (store hashed key, return raw key to caller)
        try:
            sb = _db()
            enrollment = {
                "carrier_name": carrier_name,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "api_key": api_key_hash,
                "api_key_active": True,
                "status": status,
                "meta": {"enrollment_source": "self_service"},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            r = sb.table("carrier_enrollments").insert(enrollment).execute()
            inserted = r.data[0] if r.data else enrollment
            enrollment_id = inserted.get("id")

            log.info(
                f"[carrier-enrollment] new enrollment: "
                f"carrier={carrier_name} id={enrollment_id} status={status}"
            )

        except Exception as e:
            log.error(f"[carrier-enrollment] DB insert failed: {e}")
            raise HTTPException(500, "Failed to create enrollment — please try again later")

        instructions = _build_instructions(carrier_name, api_key)

        return {
            "ok": True,
            "enrollment": {
                "id": enrollment_id,
                "carrier_name": carrier_name,
                "api_key": api_key,
                "status": status,
                "webhook_url": "https://empire-ai.co.uk/api/v1/claim-settled",
                "test_url": "https://empire-ai.co.uk/api/v1/carrier/test-webhook",
                "notes": (
                    "Enrollment is pending operator approval. "
                    "You will receive a confirmation email when approved."
                    if status == "pending"
                    else "Enrollment active. Use the API key in the Authorization header."
                ),
            },
            "instructions": instructions,
        }

    # ── OPERATOR: List enrollments ───────────────────────────────
    @app.get("/api/v1/carrier/enrollments")
    async def carrier_list_enrollments(
        status: str = None,
        limit: int = 100,
        auth: dict = Depends(require_auth) if require_auth else None,
    ):
        """List all carrier enrollments. Operator-only (requires auth)."""
        try:
            sb = _db()
            query = sb.table("carrier_enrollments").select("*").order("created_at", desc=True)

            if status:
                query = query.eq("status", status)

            r = query.limit(max(1, min(limit, 500))).execute()

            # Strip full API keys from response (show hash prefix only for debugging)
            enrollments = []
            for row in r.data or []:
                row_copy = dict(row)
                if row_copy.get("api_key"):
                    row_copy["api_key"] = row_copy["api_key"][:12] + "... [hashed]"
                enrollments.append(row_copy)

            return {"enrollments": enrollments, "total": len(enrollments)}
        except Exception as e:
            log.error(f"[carrier-enrollment] list failed: {e}")
            raise HTTPException(500, "Failed to list enrollments")

    # ── OPERATOR: Get single enrollment ───────────────────────────
    @app.get("/api/v1/carrier/enrollments/{enrollment_id}")
    async def carrier_get_enrollment(
        enrollment_id: str,
        auth: dict = Depends(require_auth) if require_auth else None,
    ):
        """Get a single enrollment. Operator-only."""
        try:
            sb = _db()
            r = sb.table("carrier_enrollments").select("*").eq("id", enrollment_id).limit(1).execute()
            if not r.data:
                raise HTTPException(404, "Enrollment not found")

            row = dict(r.data[0])
            # Strip full API key hash from response
            if row.get("api_key"):
                row["api_key"] = row["api_key"][:12] + "... [hashed]"

            return row
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[carrier-enrollment] get failed: {e}")
            raise HTTPException(500, "Failed to get enrollment")

    # ── OPERATOR: Revoke / rotate API key ─────────────────────────
    @app.post("/api/v1/carrier/enrollments/{enrollment_id}/revoke")
    async def carrier_revoke_key(
        enrollment_id: str,
        request: Request,
        auth: dict = Depends(require_auth) if require_auth else None,
    ):
        """
        Revoke a carrier's API key. Optionally rotate (issue new key).
        Body: {"rotate": true} to issue a new key.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}

        rotate = body.get("rotate", False)

        try:
            sb = _db()
            r = sb.table("carrier_enrollments").select("*").eq("id", enrollment_id).limit(1).execute()
            if not r.data:
                raise HTTPException(404, "Enrollment not found")

            update = {
                "api_key_active": False,
                "status": "revoked",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            if rotate:
                new_key = _generate_api_key()
                update["api_key"] = _hash_api_key(new_key)
                update["api_key_active"] = True
                update["status"] = "active"

            sb.table("carrier_enrollments").update(update).eq("id", enrollment_id).execute()

            enrollment = r.data[0]
            log.info(
                f"[carrier-enrollment] key {'rotated' if rotate else 'revoked'}: "
                f"carrier={enrollment.get('carrier_name')} id={enrollment_id}"
            )

            response = {
                "ok": True,
                "action": "rotated" if rotate else "revoked",
                "carrier_name": enrollment.get("carrier_name"),
            }
            if rotate:
                response["new_api_key"] = new_key
                response["instructions"] = _build_instructions(
                    enrollment.get("carrier_name", "Carrier"), new_key
                )

            return response

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[carrier-enrollment] revoke failed: {e}")
            raise HTTPException(500, "Failed to revoke API key")

    # ── PUBLIC: Test webhook endpoint ────────────────────────────
    @app.post("/api/v1/carrier/test-webhook")
    async def carrier_test_webhook(request: Request):
        """
        Test endpoint for enrolled carriers to verify their integration.
        Same auth as /api/v1/claim-settled. Processes a test settlement
        at $1,000 to verify the full chain works.

        Does NOT write to fee_events (only logs the test event).
        """
        # Authenticate
        auth_header = request.headers.get("authorization", "")
        token = auth_header
        if token.lower().startswith("bearer "):
            token = token[7:]

        enrollment = _verify_carrier_api_key(token.strip())
        if not enrollment:
            raise HTTPException(401, "Invalid or missing Authorization token")

        try:
            body = await request.json()
        except Exception:
            body = {}

        dispatch_id = (body.get("dispatch_id") or "").strip()
        if not dispatch_id:
            raise HTTPException(400, "dispatch_id is required")

        test_amount = 1000.00  # Fixed test amount
        test_fee = round(test_amount * 0.03, 2)

        # Verify the dispatch exists (but don't write fee_events)
        try:
            sb = _db()
            dispatch = (
                sb.table("dispatches")
                .select("id, contractor_id, status")
                .eq("id", dispatch_id)
                .limit(1)
                .execute()
            )
            if not dispatch.data:
                raise HTTPException(404, f"Dispatch {dispatch_id} not found")

            # Log the test event
            carrier_name = enrollment.get("carrier_name", "Unknown Carrier")
            log.info(
                f"[carrier-test] test webhook from {carrier_name}: "
                f"dispatch={dispatch_id} amount=${test_amount} fee=${test_fee}"
            )

            return {
                "ok": True,
                "test": True,
                "carrier_name": carrier_name,
                "dispatch_id": dispatch_id,
                "test_amount": test_amount,
                "test_fee": test_fee,
                "fee_percent": 0.03,
                "note": "This was a TEST — no fee_event was created. Send to /api/v1/claim-settled for real processing.",
            }

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[carrier-test] processing failed: {e}")
            raise HTTPException(500, f"Test webhook failed: {str(e)[:200]}")

    # ── PUBLIC: Enrollment instructions ──────────────────────────
    @app.get("/api/v1/carrier/enrollment-instructions")
    async def carrier_enrollment_instructions():
        """Return public webhook integration documentation."""
        return {
            "webhook_url": "https://empire-ai.co.uk/api/v1/claim-settled",
            "test_url": "https://empire-ai.co.uk/api/v1/carrier/test-webhook",
            "enroll_url": "https://empire-ai.co.uk/api/v1/carrier/enroll",
            "auth_method": "Bearer token in Authorization header",
            "auth_note": "Get your API key by POSTing to /api/v1/carrier/enroll",
            "fee_percent": 0.03,
            "format": "JSON",
            "rate_limits": {
                "max_claim_amount": 100_000_000,
                "min_claim_amount": 0.01,
            },
            "required_fields": [
                {"name": "dispatch_id", "type": "string (UUID)", "description": "Empire AI dispatch UUID"},
                {"name": "claim_amount", "type": "number", "description": "Settlement amount in USD"},
            ],
            "optional_fields": [
                {"name": "claim_id", "type": "string", "description": "Your internal claim reference"},
                {"name": "settled_at", "type": "ISO 8601", "description": "Settlement timestamp"},
                {"name": "loss_description", "type": "string", "description": "Brief claim summary"},
            ],
        }
