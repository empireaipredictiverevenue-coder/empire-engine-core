"""
EMPIRE V49 · VOICE ENGINE (Hybrid Architecture)
================================================
Vonage primary · In-house SIP ready. The smart router decides per call.

Architecture:
    Inbound/Outbound call request
              ↓
        VoiceRouter
              ↓
    ┌─────────┴─────────┐
    │                   │
  VonageAdapter   EmpireSIPAdapter
  (today)         (when ready)

This module replaces the empty vonage_inbound stub in hub.py with a full
production-grade voice layer. Connects directly to:
  - Empire Brain (for live call analysis)
  - radar_targets (to enrich the caller)
  - ab_assignments (to attribute conversions)
  - manus_fires (to mark dispatches as voice-confirmed)

Wire-up in hub.py:
    from empire_voice import (
        VoiceRouter, register_voice_routes,
        outbound_strike, inbound_handler,
    )

    voice_router = VoiceRouter(
        vonage_api_key=os.environ.get("VONAGE_API_KEY"),
        vonage_api_secret=os.environ.get("VONAGE_API_SECRET"),
        vonage_app_id=os.environ.get("VONAGE_APP_ID"),
        vonage_private_key_path=os.environ.get("VONAGE_PRIVATE_KEY_PATH"),
        vonage_number=os.environ.get("VONAGE_NUMBER"),
    )
    register_voice_routes(app, voice_router)

Environment variables (all optional — degrades gracefully):
    VONAGE_API_KEY           Vonage API key
    VONAGE_API_SECRET        Vonage API secret
    VONAGE_APP_ID            Vonage application ID
    VONAGE_PRIVATE_KEY_PATH  path to private.key file
    VONAGE_NUMBER            "+18005550199" — your Vonage DID
    EMPIRE_VOICE_ANSWER_URL  webhook for inbound · default /api/v1/voice/answer
    EMPIRE_VOICE_EVENT_URL   webhook for events  · default /api/v1/voice/events
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, PlainTextResponse


log = logging.getLogger("empire.voice")


# ─────────────────────────────────────────────────────────────────────────────
# DATA TYPES
# ─────────────────────────────────────────────────────────────────────────────
class CallStatus(str, Enum):
    QUEUED      = "queued"
    DIALING     = "dialing"
    RINGING     = "ringing"
    ANSWERED    = "answered"
    COMPLETED   = "completed"
    FAILED      = "failed"
    BUSY        = "busy"
    NO_ANSWER   = "no_answer"
    REJECTED    = "rejected"


class CallDirection(str, Enum):
    INBOUND  = "inbound"
    OUTBOUND = "outbound"


# ─────────────────────────────────────────────────────────────────────────────
# VONAGE ADAPTER — the actual telephony provider
# ─────────────────────────────────────────────────────────────────────────────
class VonageAdapter:
    """
    Vonage Voice API adapter. Handles JWT auth, NCCO generation, outbound
    dialing, and event parsing. Designed to be swappable — same interface
    will work when we move to in-house SIP.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        app_id: str = "",
        private_key_path: str = "",
        from_number: str = "",
    ):
        self.api_key      = api_key
        self.api_secret   = api_secret
        self.app_id       = app_id
        self.private_key  = self._load_private_key(private_key_path)
        self.from_number  = from_number
        self.enabled      = bool(api_key and api_secret and app_id and self.private_key)

        if self.enabled:
            log.info(f"[vonage] Adapter ONLINE · DID {from_number}")
        else:
            log.warning("[vonage] Adapter DISABLED · missing credentials (will log-only)")

    def _load_private_key(self, path: str) -> Optional[str]:
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception as e:
            log.error(f"[vonage] Private key load failed: {e}")
            return None

    def _generate_jwt(self) -> Optional[str]:
        """Generate a short-lived JWT for the Vonage API."""
        if not self.enabled:
            return None
        try:
            import jwt
            import time
            payload = {
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "jti": f"empire-{int(time.time() * 1000)}",
                "application_id": self.app_id,
            }
            return jwt.encode(payload, self.private_key, algorithm="RS256")
        except ImportError:
            log.error("[vonage] PyJWT not installed · pip install pyjwt[crypto]")
            return None
        except Exception as e:
            log.error(f"[vonage] JWT generation failed: {e}")
            return None

    async def place_call(
        self,
        to_number: str,
        ncco: list,
        event_webhook: str = "",
    ) -> dict:
        """
        Place an outbound call using the Vonage Voice API.
        Returns: {ok, uuid, status, error?}

        Args:
            to_number: E.164 destination (e.g. "+12145551234")
            ncco: NCCO (Nexmo Call Control Object) — defines call flow
            event_webhook: URL Vonage POSTs status updates to
        """
        if not self.enabled:
            log.info(f"[vonage] STUB · would call {to_number}")
            return {"ok": True, "uuid": "stub-uuid", "status": "stub", "stub": True}

        token = self._generate_jwt()
        if not token:
            return {"ok": False, "error": "JWT generation failed"}

        payload = {
            "to":   [{"type": "phone", "number": to_number.lstrip("+")}],
            "from": {"type": "phone", "number": self.from_number.lstrip("+")},
            "ncco": ncco,
        }
        if event_webhook:
            payload["event_url"] = [event_webhook]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "https://api.nexmo.com/v1/calls",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type":  "application/json",
                    },
                )
                if r.status_code in (200, 201):
                    data = r.json()
                    return {
                        "ok":     True,
                        "uuid":   data.get("uuid"),
                        "status": data.get("status", "queued"),
                    }
                else:
                    return {
                        "ok":    False,
                        "error": f"HTTP {r.status_code}: {r.text[:200]}",
                    }
        except Exception as e:
            log.error(f"[vonage] place_call error: {e}")
            return {"ok": False, "error": str(e)}

    async def send_sms(self, to_number: str, message: str) -> dict:
        """
        Send an SMS via Vonage Messages API. Returns: {ok, message_uuid, error?}
        """
        if not self.enabled:
            log.info(f"[vonage] STUB · would SMS {to_number}: {message[:60]}")
            return {"ok": True, "message_uuid": "stub", "stub": True}

        token = self._generate_jwt()
        if not token:
            return {"ok": False, "error": "JWT generation failed"}

        payload = {
            "from":         self.from_number.lstrip("+"),
            "to":           to_number.lstrip("+"),
            "message_type": "text",
            "text":         message[:1600],  # SMS hard limit
            "channel":      "sms",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "https://api.nexmo.com/v1/messages",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type":  "application/json",
                    },
                )
                if r.status_code in (200, 202):
                    return {
                        "ok":           True,
                        "message_uuid": r.json().get("message_uuid"),
                    }
                else:
                    return {
                        "ok":    False,
                        "error": f"HTTP {r.status_code}: {r.text[:200]}",
                    }
        except Exception as e:
            log.error(f"[vonage] send_sms error: {e}")
            return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# NCCO BUILDERS — Vonage Call Control Object templates
# ─────────────────────────────────────────────────────────────────────────────
def ncco_inbound_strike(
    target_address: str = "",
    severity:       str = "",
    forward_to:     str = "",
) -> list:
    """
    NCCO for inbound calls. The opener identifies as Empire AI (TCPA-required
    paid commercial identification), brief value pitch, then either:
    - Forwards to a human operator if forward_to is set
    - Records a voicemail otherwise
    """
    intro = (
        "Thank you for calling Empire AI. "
        "This is a paid commercial dispatch service. "
    )
    if target_address:
        intro += (
            f"We detected severe weather activity near {target_address}. "
        )
    intro += "Please hold while we connect you."

    ncco: list = [
        {
            "action":   "talk",
            "text":     intro,
            "voiceName": "Amy",
            "level":    0,
        },
    ]

    if forward_to:
        ncco.append({
            "action":      "connect",
            "from":        "",  # Vonage uses the DID
            "endpoint":    [{
                "type":   "phone",
                "number": forward_to.lstrip("+"),
            }],
            "timeout":     30,
            "limit":       1800,  # 30-minute call cap
        })
    else:
        ncco.append({
            "action":         "record",
            "eventUrl":       [],
            "endOnSilence":   3,
            "endOnKey":       "#",
            "timeOut":        120,
            "beepStart":      True,
        })
        ncco.append({
            "action": "talk",
            "text":   "Thank you. An operator will follow up within one business day.",
        })

    return ncco


def ncco_outbound_strike(
    target_address: str,
    asset_value:    float,
    operator_number: str = "",
) -> list:
    """
    NCCO for outbound strikes. Brief identification, value pitch, then
    bridge to an operator OR to recording for callback.
    """
    fee = round(asset_value * 0.01, 0)
    pitch = (
        "This is Empire AI Predictive Cloud. "
        "Our system detected severe weather activity at your facility. "
    )
    if asset_value > 0:
        pitch += (
            f"Based on an estimated asset value of ${asset_value:,.0f}, "
            f"our success-only fee on a settled claim would be ${fee:,.0f}. "
            "No charge if no claim is filed or no settlement reached. "
        )
    pitch += "Please hold while we connect you to a specialist."

    ncco: list = [
        {
            "action":    "talk",
            "text":      pitch,
            "voiceName": "Amy",
        },
    ]

    if operator_number:
        ncco.append({
            "action":   "connect",
            "endpoint": [{
                "type":   "phone",
                "number": operator_number.lstrip("+"),
            }],
            "timeout":  30,
            "limit":    1800,
        })

    return ncco


# ─────────────────────────────────────────────────────────────────────────────
# VOICE ROUTER — the smart traffic cop. Hybrid Vonage + future SIP.
# ─────────────────────────────────────────────────────────────────────────────
class VoiceRouter:
    """
    Picks the right adapter per call. Today, only Vonage is wired.
    When Empire SIP is ready, add an EmpireSIPAdapter and update _pick_adapter()
    to route Tier 1 US corridors through it.
    """

    def __init__(
        self,
        vonage_api_key:          str = "",
        vonage_api_secret:       str = "",
        vonage_app_id:           str = "",
        vonage_private_key_path: str = "",
        vonage_number:           str = "",
        public_base_url:         str = "",
    ):
        self.vonage = VonageAdapter(
            api_key=vonage_api_key,
            api_secret=vonage_api_secret,
            app_id=vonage_app_id,
            private_key_path=vonage_private_key_path,
            from_number=vonage_number,
        )
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else ""
        self.stats = {
            "outbound_placed":   0,
            "inbound_received":  0,
            "sms_sent":          0,
            "calls_completed":   0,
            "calls_failed":      0,
        }

    def _pick_adapter(self, to_number: str, direction: CallDirection):
        """
        Return the adapter to use for this call.
        Future: route US Tier 1 → Empire SIP, EU/Canada/spillover → Vonage.
        For now: everything goes to Vonage.
        """
        # When Empire SIP is ready:
        # if direction == CallDirection.OUTBOUND and self._is_tier_1_us(to_number):
        #     return self.empire_sip
        return self.vonage

    async def place_strike_call(
        self,
        to_number:      str,
        target_address: str = "",
        asset_value:    float = 0,
        operator_number: str = "",
        broadcaster=None,  # optional empire_live.LiveBroadcaster instance
    ) -> dict:
        """
        Place an outbound strike call. Used by the Manus operator pipeline
        and the brain when an immediate dial is requested.
        """
        ncco = ncco_outbound_strike(
            target_address=target_address,
            asset_value=asset_value,
            operator_number=operator_number,
        )
        event_url = ""
        if self.public_base_url:
            event_url = f"{self.public_base_url}/api/v1/voice/events"

        adapter = self._pick_adapter(to_number, CallDirection.OUTBOUND)
        result = await adapter.place_call(
            to_number=to_number,
            ncco=ncco,
            event_webhook=event_url,
        )

        self.stats["outbound_placed"] += 1

        # Broadcast to live dashboards
        if broadcaster and result.get("ok"):
            try:
                await broadcaster.broadcast({
                    "type":          "call_placed",
                    "direction":     "outbound",
                    "to":            to_number,
                    "target":        target_address,
                    "asset_value":   asset_value,
                    "uuid":          result.get("uuid"),
                })
            except Exception:
                pass

        return result

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send a single SMS. Used by the SMS sequence engine."""
        adapter = self._pick_adapter(to_number, CallDirection.OUTBOUND)
        result = await adapter.send_sms(to_number, message)
        if result.get("ok"):
            self.stats["sms_sent"] += 1
        return result


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTE REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────
def register_voice_routes(
    app: FastAPI,
    router: VoiceRouter,
    require_auth=None,
    get_db=None,
    ntfy_topic: str = "",
    ntfy_token: str = "",
    broadcaster=None,
):
    """
    Register the voice webhooks with the FastAPI app. Call this once during
    startup. The two webhooks must be configured in your Vonage application:

      Answer URL: https://empire-ai.co.uk/api/v1/voice/answer
      Event URL:  https://empire-ai.co.uk/api/v1/voice/events
    """

    # ── INBOUND ANSWER WEBHOOK ──────────────────────────────────────────
    @app.get("/api/v1/voice/answer")
    @app.post("/api/v1/voice/answer")
    async def voice_answer(request: Request):
        """
        Vonage hits this when a call comes in. We return an NCCO that
        Vonage executes (talk, connect, record, etc).
        """
        # Vonage sends params as query string OR JSON depending on the version
        params = dict(request.query_params)
        if request.method == "POST":
            try:
                body = await request.json()
                params.update(body)
            except Exception:
                pass

        from_number = params.get("from", "unknown")
        to_number   = params.get("to", "")
        call_uuid   = params.get("uuid", "")

        router.stats["inbound_received"] += 1

        # Try to enrich with radar_targets lookup
        target_address = ""
        severity = ""
        if get_db:
            try:
                db = get_db()
                res = db.table("radar_targets") \
                    .select("address, damage_severity") \
                    .eq("phone", from_number.lstrip("+1").lstrip("+")) \
                    .limit(1).execute()
                if res.data:
                    target_address = res.data[0].get("address", "")
                    severity       = res.data[0].get("damage_severity", "")
            except Exception as e:
                log.debug(f"[voice] enrichment failed: {e}")

        # Push to live dashboards
        if broadcaster:
            try:
                await broadcaster.broadcast({
                    "type":      "call_inbound",
                    "from":      from_number,
                    "to":        to_number,
                    "uuid":      call_uuid,
                    "target":    target_address,
                    "severity":  severity,
                })
            except Exception:
                pass

        # Ntfy the operator
        if ntfy_topic:
            try:
                headers = {
                    "Title":    "📞 EMPIRE · INBOUND CALL",
                    "Priority": "urgent",
                    "Tags":     "phone,rotating_light",
                }
                if ntfy_token:
                    headers["Authorization"] = f"Bearer {ntfy_token}"
                async with httpx.AsyncClient() as c:
                    await c.post(
                        f"https://ntfy.sh/{ntfy_topic}",
                        data=(
                            f"From: {from_number}\n"
                            f"Target: {target_address or 'unmatched caller'}\n"
                            f"UUID: {call_uuid}"
                        ),
                        headers=headers,
                        timeout=5.0,
                    )
            except Exception:
                pass

        # Mark this caller as converted in A/B (they called us)
        if get_db:
            try:
                db = get_db()
                db.table("ab_assignments").update({
                    "converted":    True,
                    "converted_at": datetime.now(timezone.utc).isoformat(),
                }).eq("visitor_ip", params.get("conversation_uuid", "")).execute()
            except Exception:
                pass

        # Build the NCCO
        operator_number = os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
        ncco = ncco_inbound_strike(
            target_address=target_address,
            severity=severity,
            forward_to=operator_number,
        )

        return JSONResponse(content=ncco)

    # ── EVENT WEBHOOK ───────────────────────────────────────────────────
    @app.post("/api/v1/voice/events")
    async def voice_events(request: Request):
        """
        Vonage posts call lifecycle events here: ringing, answered,
        completed, etc. We log them and push to the live dashboard.
        """
        try:
            event = await request.json()
        except Exception:
            event = {}

        status     = event.get("status", "unknown")
        call_uuid  = event.get("uuid", "")
        direction  = event.get("direction", "")
        duration   = event.get("duration", 0)

        # Update stats
        if status == "completed":
            router.stats["calls_completed"] += 1
        elif status in ("failed", "rejected", "busy", "timeout"):
            router.stats["calls_failed"] += 1

        # Persist to call_events table if Supabase is wired
        if get_db:
            try:
                db = get_db()
                db.table("call_events").insert({
                    "call_uuid":  call_uuid,
                    "status":     status,
                    "direction":  direction,
                    "duration":   int(duration) if duration else 0,
                    "meta":       event,
                }).execute()
            except Exception as e:
                # call_events table optional; warn but don't fail
                log.debug(f"[voice] call_events insert: {e}")

        # Push to live dashboards
        if broadcaster:
            try:
                await broadcaster.broadcast({
                    "type":      "call_event",
                    "status":    status,
                    "uuid":      call_uuid,
                    "direction": direction,
                    "duration":  duration,
                })
            except Exception:
                pass

        return PlainTextResponse("ok", status_code=200)

    # ── OPERATOR: PLACE OUTBOUND STRIKE ─────────────────────────────────
    if require_auth:
        @app.post("/api/v1/voice/strike")
        async def voice_strike(request: Request, auth: bool = Depends(require_auth)):
            """
            Operator endpoint to trigger an outbound strike call.
            Body: {to: "+12145551234", target_address: "...", asset_value: 2500000}
            """
            try:
                body = await request.json()
            except Exception:
                body = {}
            to_number      = body.get("to", "")
            target_address = body.get("target_address", "")
            asset_value    = float(body.get("asset_value", 0) or 0)

            if not to_number:
                raise HTTPException(400, "to (phone number) required")

            operator = os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
            result = await router.place_strike_call(
                to_number=to_number,
                target_address=target_address,
                asset_value=asset_value,
                operator_number=operator,
                broadcaster=broadcaster,
            )
            return result

        @app.get("/api/v1/voice/stats")
        async def voice_stats(auth: bool = Depends(require_auth)):
            """Live voice engine stats."""
            return {
                **router.stats,
                "vonage_enabled": router.vonage.enabled,
            }

    log.info("[voice] Routes registered · /api/v1/voice/{answer,events,strike,stats}")
