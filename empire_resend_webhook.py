"""
Empire AI · Resend Webhook Handler
====================================

Receives Resend events for:
  - email.delivered    → contractor_outreach.delivered_at
  - email.opened        → contractor_outreach.opened_at
  - email.clicked       → contractor_outreach.clicked_at (with click URL)
  - email.bounced       → contractor_outreach.status = 'bounced' (mark for retry skip)
  - email.complained    → contractor_outreach.status = 'unsubscribed'

Endpoint: POST /api/v1/resend/webhook
Signed with HMAC-SHA256(secret, f"{timestamp}.{body}"). Resend header format:
  Resend-Signature: t=1234567890,v1=abc123def456...

Resend event payload shape:
  {
    "type": "email.opened",
    "created_at": "2024-04-26T20:37:55.098Z",
    "data": {
      "email_id": "abc123",
      "from": "Empire AI <ops@empire-ai.co.uk>",
      "to": ["contractor@example.com"],
      "subject": "Empire AI · paid tiers are live",
      "tags": [{"name": "outreach_id", "value": "879b1e04-..."}]
    }
  }

We tag every outbound email with the contractor_outreach row id so we can
update state without a separate lookup table.
"""
import os
import hmac
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

REPO = Path("/root/empire-v49")

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from fastapi import Request
from fastapi.responses import JSONResponse
from supabase import create_client

log = logging.getLogger("resend_webhook")

WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")
SIGNATURE_TOLERANCE_SEC = 300  # reject events older than 5 minutes


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _verify_signature(header_val: str, raw_body: bytes) -> bool:
    """Verify Resend-Signature header against the request body + secret."""
    if not header_val or not WEBHOOK_SECRET:
        return False
    parts = dict(p.split("=", 1) for p in header_val.split(",") if "=" in p)
    ts = parts.get("t", "")
    sig = parts.get("v1", "")
    if not (ts and sig):
        return False
    # Reject old events (replay protection)
    try:
        age = (datetime.now(timezone.utc).timestamp() - int(ts))
        if abs(age) > SIGNATURE_TOLERANCE_SEC:
            log.warning(f"webhook: signature too old ({int(age)}s)")
            return False
    except ValueError:
        return False
    signed_payload = f"{ts}.".encode() + raw_body
    expected = hmac.new(WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _find_outreach_id_from_event(data: dict) -> Optional[str]:
    """Pull the contractor_outreach row id from the email's tags."""
    tags = data.get("tags") or []
    for tag in tags:
        if tag.get("name") == "outreach_id":
            return tag.get("value")
    return None


async def handle_resend_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    sig_header = request.headers.get("resend-signature", "") or request.headers.get("Resend-Signature", "")
    if not _verify_signature(sig_header, raw_body):
        log.warning("webhook: signature verification failed")
        return JSONResponse({"detail": "invalid signature"}, status_code=401)

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse({"detail": "invalid json"}, status_code=400)

    event_type = event.get("type", "")
    event_data = event.get("data") or {}
    event_ts = event.get("created_at") or datetime.now(timezone.utc).isoformat()
    to_list = event_data.get("to") or []
    recipient = to_list[0] if to_list else None

    outreach_id = _find_outreach_id_from_event(event_data)
    sb = _sb()

    update = {}
    if event_type == "email.delivered":
        update["delivered_at"] = event_ts
    elif event_type == "email.opened":
        update["opened_at"] = event_ts
    elif event_type == "email.clicked":
        update["clicked_at"] = event_ts
    elif event_type == "email.bounced":
        update["status"] = "bounced"
    elif event_type == "email.complained":
        update["status"] = "unsubscribed"

    if not update:
        return JSONResponse({"detail": f"unhandled event: {event_type}"}, status_code=200)

    # If we have an outreach_id, update directly. Otherwise try matching by recipient.
    if outreach_id:
        sb.table("contractor_outreach").update(update).eq("id", outreach_id).execute()
        log.info(f"webhook: {event_type} → outreach_id={outreach_id[:8]}")
    elif recipient:
        # Fallback: try to find by recipient (to[0])
        # We don't store recipient on the outreach row, so use contractor email
        # via a sub-query. Simpler: log the event so we can attribute later.
        log.info(f"webhook: {event_type} → recipient={recipient} (no outreach_id tag)")

    return JSONResponse({"ok": True, "event": event_type})


def register_resend_webhook(app):
    """Register the Resend webhook route. Idempotent."""
    @app.post("/api/v1/resend/webhook")
    async def resend_webhook_endpoint(request: Request):
        return await handle_resend_webhook(request)

    log.info("[resend-webhook] route registered: POST /api/v1/resend/webhook")