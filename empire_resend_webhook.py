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
Signed with Svix webhook format (HMAC-SHA256 + base64, whsec_ prefixed secret).
Headers:
  svix-id, svix-timestamp, svix-signature
Signed payload: "{svix_id}.{svix_ts}.{raw_body}"
Secret: base64-decoded whsec_ key → HMAC-SHA256 → base64-encoded digest

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
import base64
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

# Resend generates a unique signing secret per webhook. We store the primary
# one from the env but also know the auto-generated secrets for webhooks 2 and 3.
# The verifier tries all known secrets so events from any webhook are accepted.
WEBHOOK_SECRETS = [
    os.environ.get("RESEND_WEBHOOK_SECRET", ""),
    "whsec_f7qMcUmCy46f0J279QO7qUUM0mTtDsta",  # webhook 2 (bounce/complaint)
    "whsec_ciyjAkwNXqPCFPnEzYwTSFLpnIDAs2qF",  # webhook 3 (inbound email)
]
SIGNATURE_TOLERANCE_SEC = 300  # reject events older than 5 minutes


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _decode_secret(secret: str) -> bytes:
    """Base64-decode the webhook signing secret (strip whsec_ prefix)."""
    raw = secret
    if raw.startswith("whsec_"):
        raw = raw[6:]
    try:
        return base64.b64decode(raw)
    except Exception as exc:
        log.warning(f"webhook: failed to base64-decode signing secret, using raw bytes: {exc}")
        return raw.encode()


def _verify_svix_signature(
    svix_id: str, svix_ts: str, svix_sig: str, raw_body: bytes
) -> bool:
    """Verify Svix-format webhook signature (Resend uses Svix).

    Tries all known WEBHOOK_SECRETS so events from any of the 3 Resend
    webhooks (each with a unique auto-generated signing secret) are accepted.
    """
    if not (svix_id and svix_ts and svix_sig):
        return False
    # Reject old events (replay protection)
    try:
        age = (datetime.now(timezone.utc).timestamp() - int(svix_ts))
        if abs(age) > SIGNATURE_TOLERANCE_SEC:
            log.warning(f"webhook: signature too old ({int(age)}s)")
            return False
    except ValueError:
        return False
    # Build signed content: {svix_id}.{svix_ts}.{raw_body}
    signed_content = f"{svix_id}.{svix_ts}.".encode() + raw_body
    # Try each known secret
    for secret in WEBHOOK_SECRETS:
        if not secret:
            continue
        key = _decode_secret(secret)
        computed = hmac.new(key, signed_content, hashlib.sha256).digest()
        expected = base64.b64encode(computed).decode()
        # svix-signature format: "v1,sig1 v1,sig2..." — try each version
        for part in svix_sig.split():
            if part.startswith("v1,"):
                candidate = part[3:]
                if hmac.compare_digest(expected, candidate):
                    return True
    return False


def _find_outreach_id_from_event(data: dict) -> Optional[str]:
    """Pull the contractor_outreach row id from the email's tags."""
    tags = data.get("tags") or []
    for tag in tags:
        if tag.get("name") == "outreach_id":
            return tag.get("value")
    return None


async def handle_resend_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()

    # Svix webhook headers (Resend uses Svix)
    svix_id = request.headers.get("svix-id") or request.headers.get("webhook-id", "")
    svix_ts = request.headers.get("svix-timestamp") or request.headers.get("webhook-timestamp", "")
    svix_sig = request.headers.get("svix-signature") or request.headers.get("webhook-signature", "")

    if not _verify_svix_signature(svix_id, svix_ts, svix_sig, raw_body):
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
        log.info(f"webhook: {event_type} → recipient={recipient} (no outreach_id tag)")

    return JSONResponse({"ok": True, "event": event_type})


def register_resend_webhook(app):
    """Register the Resend webhook route. Idempotent."""
    @app.post("/api/v1/resend/webhook")
    async def resend_webhook_endpoint(request: Request):
        return await handle_resend_webhook(request)

    log.info("[resend-webhook] route registered: POST /api/v1/resend/webhook")