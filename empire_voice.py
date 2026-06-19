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
from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, PlainTextResponse
from conversion_funnel import COMMISSION_RATE

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
        # Cached JWT — reused across calls to avoid RSA signing on every request
        self._cached_token: Optional[str] = None
        self._cached_token_expiry: float = 0.0
        # Persistent httpx clients — connection pooling eliminates TLS handshake per call
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None

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
        """Generate a short-lived JWT for the Vonage API. Cached for reuse."""
        if not self.enabled:
            return None

        import time
        now = time.time()

        # Return cached token if it still has ≥60s of life remaining
        if self._cached_token is not None and self._cached_token_expiry > now + 60:
            return self._cached_token

        try:
            import jwt
            exp = int(now) + 3600
            payload = {
                "iat": int(now),
                "exp": exp,
                "jti": f"empire-{int(now * 1000)}",
                "application_id": self.app_id,
            }
            token = jwt.encode(payload, self.private_key, algorithm="RS256")
            # Cache the token with its expiry timestamp
            self._cached_token = token
            self._cached_token_expiry = float(exp)
            return token
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
            log.error(f"[vonage] place_call blocked: adapter not enabled (missing creds: VONAGE_API_KEY/SECRET/APPLICATION_ID/PRIVATE_KEY_PATH in /root/.env). to_number={to_number}")
            return {"ok": False, "error": "vonage_adapter_disabled_check_env"}

        token = self._generate_jwt()
        if not token:
            return {"ok": False, "error": "JWT generation failed"}

        payload = {
            "to":   [{"type": "phone", "number": to_number}],
            "from": {"type": "phone", "number": self.from_number},
            "ncco": ncco,
            # Advanced machine detection — async mode means NO silence at call start.
            # Detection runs in the background while the NCCO plays immediately.
            # The event webhook receives machine/human events as they're determined.
            # beep_timeout is 30-120s per Vonage validation. 45s is a
            # reasonable human answer window — TTS starts after that.
            "advanced_machine_detection": {
                "behavior": "continue",
                "mode": "default",
                "beep_timeout": 45,
            },
        }
        if event_webhook:
            payload["event_url"] = [event_webhook]

        try:
            if self._async_client is None:
                self._async_client = httpx.AsyncClient(timeout=10.0)
            r = await self._async_client.post(
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

    def place_call_sync(
        self,
        to_number: str,
        ncco: list,
        event_webhook: str = "",
    ) -> dict:
        """
        Synchronous version of place_call(). Shares JWT cache + connection pool
        with the async path. Used by scripts without an event loop (bots, cron).
        Returns: {ok, uuid, status, error?}
        """
        if not self.enabled:
            log.error(f"[vonage] place_call_sync blocked: adapter not enabled. to_number={to_number}")
            return {"ok": False, "error": "vonage_adapter_disabled_check_env"}

        token = self._generate_jwt()
        if not token:
            return {"ok": False, "error": "JWT generation failed"}

        payload = {
            "to":   [{"type": "phone", "number": to_number}],
            "from": {"type": "phone", "number": self.from_number},
            "ncco": ncco,
            "advanced_machine_detection": {
                "behavior": "continue",
                "mode": "default",
                "beep_timeout": 45,
            },
        }
        if event_webhook:
            payload["event_url"] = [event_webhook]

        try:
            if self._sync_client is None:
                self._sync_client = httpx.Client(timeout=10.0)
            r = self._sync_client.post(
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
            log.error(f"[vonage] place_call_sync error: {e}")
            return {"ok": False, "error": str(e)}

    async def send_sms(self, to_number: str, message: str) -> dict:
        """
        Send an SMS via Vonage Messages API. Returns: {ok, message_uuid, error?}
        """
        if not self.enabled:
            log.error(f"[vonage] send_sms blocked: adapter not enabled. to_number={to_number} body[:60]={message[:60]}")
            return {"ok": False, "error": "vonage_adapter_disabled_check_env"}

        token = self._generate_jwt()
        if not token:
            return {"ok": False, "error": "JWT generation failed"}

        payload = {
            "from":         self.from_number,
            "to":           to_number,
            "message_type": "text",
            "text":         message[:1600],  # SMS hard limit
            "channel":      "sms",
        }

        try:
            if self._async_client is None:
                self._async_client = httpx.AsyncClient(timeout=10.0)
            r = await self._async_client.post(
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
                "number": forward_to,
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
    NCCO for outbound strikes. Warm-forward: connect immediately when an
    operator is available (skips TTS preamble for human-answered calls).
    Falls back to the talk script when connect times out or no operator.
    """
    ncco: list = []

    if operator_number:
        # Connect first — when a human answers, they're bridged immediately
        # without a TTS preamble (saves 2-5s per answered call).
        # If connect fails/timeouts, the talk action plays as voicemail.
        ncco.append({
            "action":   "connect",
            "endpoint": [{
                "type":   "phone",
                "number": operator_number,
            }],
            "timeout":  30,
            "limit":    1800,
        })

    fee = round(asset_value * COMMISSION_RATE, 0)
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

    # Talk plays only when there's no operator, or when the connect action
    # fails/times out (e.g., voicemail that doesn't answer quickly enough).
    ncco.append({
        "action":    "talk",
        "text":      pitch,
        "voiceName": "Amy",
    })

    return ncco


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING TTS NCCO — live phone-call audio from synthetic_brain
# ─────────────────────────────────────────────────────────────────────────────
def ncco_stream_tts(
    ws_url: str,
    target_address: str = "",
    operator_number: str = "",
) -> list:
    """
    Build a Vonage NCCO that streams live TTS audio from the synthetic_brain
    WebSocket onto the call. The `stream` action tells Vonage to open a
    WebSocket to `ws_url` and play the binary audio frames (L16 16kHz mono
    PCM) back to the caller as they arrive.

    Use this for high-value outbound strikes where we want our own Kokoro
    voice (consistent with the SPA's video ads) rather than Vonage's
    built-in TTS voices. The voice_streaming_agent registers the script
    via synthetic_brain's /register_stream endpoint first, then calls
    place_streaming_strike() with the returned ws_url.

    Optional warm-forward: if operator_number is set and a human answers
    within `connect_timeout_s`, we connect them to the operator and skip
    the TTS stream. If connect times out (voicemail/silence), the stream
    NCCO plays. Same warm-forward logic as ncco_outbound_strike.

    Audio format: L16 (16-bit signed little-endian PCM), 16kHz, mono.
    """
    op = operator_number or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
    ncco: list = []

    if op:
        ncco.append({
            "action":   "connect",
            "endpoint": [{"type": "phone", "number": op}],
            "timeout":  30,
            "limit":    1800,
            # AMD: hang up on voicemail so the stream NCCO (below) doesn't
            # burn minutes on a machine. Without this the connect action
            # would bridge to whatever the operator's voicemail picks up,
            # which is what we explicitly want to avoid here.
            "machineDetection": "hangup",
        })

    # Stream action — Vonage opens WebSocket to ws_url and plays whatever
    # binary audio frames we send. Audio format is fixed: L16 16kHz mono.
    ncco.append({
        "action":  "stream",
        "streamUrl": [ws_url],
        "level":   0,
    })

    return ncco


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC NCCO — brain-decided call scripts
# ─────────────────────────────────────────────────────────────────────────────
def ncco_dynamic_inbound(
    target_address: str = "",
    severity: str = "",
    brain_decision: Optional[dict] = None,
    forward_to: str = "",
) -> list:
    """
    Dynamic NCCO based on the brain's GO/NO-GO decision.
    GO + high confidence → confident storm pitch
    GO + low confidence → softer weather mention
    NO_GO or no brain → generic greeting (fallback)
    """
    operator_number = forward_to or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")

    if brain_decision and brain_decision.get("decision") == "GO":
        confidence = float(brain_decision.get("confidence", 0))
        reasoning = brain_decision.get("reasoning", "")

        if confidence >= 0.7:
            # High-confidence GO — confident storm strike pitch
            pitch = (
                "This is Empire AI. Our predictive system detected severe weather "
            )
            if target_address:
                pitch += f"in the area of {target_address}. "
            pitch += (
                "We are dispatching commercial property outreach on behalf of our client. "
                "This is a paid commercial dispatch service. "
            )
            short_reason = reasoning[:100].rstrip(".") if reasoning else ""
            if len(short_reason) > 10:
                pitch += f"Our assessment indicates {short_reason}. "
            pitch += "Please hold for a specialist."
        else:
            # Lower-confidence GO — softer pitch
            pitch = (
                "This is Empire AI. This is a paid commercial dispatch service. "
            )
            if target_address:
                pitch += f"Our system has noted weather activity near {target_address}. "
            pitch += "Please hold while we connect you to a specialist."
    else:
        # NO_GO or no brain — generic greeting
        pitch = (
            "Thank you for calling Empire AI. "
            "This is a paid commercial dispatch service. "
        )
        if target_address:
            pitch += f"We detected weather activity near {target_address}. "
        pitch += "Please hold while we connect you."

    ncco: list = [
        {
            "action": "talk",
            "text": pitch,
            "voiceName": "Amy",
            "level": 0,
        },
    ]

    if operator_number:
        ncco.append({
            "action": "connect",
            "from": "",
            "endpoint": [{
                "type": "phone",
                "number": operator_number,
            }],
            "timeout": 30,
            "limit": 1800,
        })
    else:
        ncco.append({
            "action": "record",
            "eventUrl": [],
            "endOnSilence": 3,
            "endOnKey": "#",
            "timeOut": 120,
            "beepStart": True,
        })
        ncco.append({
            "action": "talk",
            "text": "Thank you. An operator will follow up within one business day.",
        })

    return ncco


def ncco_dynamic_outbound(
    target_address: str = "",
    asset_value: float = 0,
    brain_decision: Optional[dict] = None,
    operator_number: str = "",
) -> list:
    """
    Dynamic NCCO for outbound strikes based on the brain's GO/NO-GO decision.
    GO + high confidence → confident storm pitch with asset value details
    GO + low confidence → softer weather mention
    NO_GO or no brain → fallback to standard outbound NCCO
    """
    if not (brain_decision and brain_decision.get("decision") == "GO"):
        # No brain or NO_GO — fallback to the standard static NCCO
        return ncco_outbound_strike(
            target_address=target_address,
            asset_value=asset_value,
            operator_number=operator_number,
        )

    confidence = float(brain_decision.get("confidence", 0))
    reasoning = brain_decision.get("reasoning", "")
    op = operator_number or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")

    # Build the ncco with warm-forward (same structure as ncco_outbound_strike)
    ncco: list = []

    if op:
        ncco.append({
            "action":   "connect",
            "endpoint": [{"type": "phone", "number": op}],
            "timeout":  30,
            "limit":    1800,
        })

    fee = round(asset_value * COMMISSION_RATE, 0)

    if confidence >= 0.7:
        # High-confidence GO — confident storm pitch with asset details
        pitch = (
            "This is Empire AI Predictive Cloud. "
            "Our system detected severe weather activity at your facility. "
        )
        if target_address:
            pitch += f"We are monitoring conditions near {target_address}. "
        if asset_value > 0:
            pitch += (
                f"Based on estimated asset value of ${asset_value:,.0f}, "
                f"our success-only fee on a settled claim would be ${fee:,.0f}. "
                "No charge if no claim is filed or no settlement reached. "
            )
        short_reason = reasoning[:100].rstrip(".") if reasoning else ""
        if len(short_reason) > 10:
            pitch += f"Our assessment indicates {short_reason}. "
        pitch += "Please hold while we connect you to a specialist."
    else:
        # Lower-confidence GO — softer pitch
        pitch = (
            "This is Empire AI. This is a paid commercial dispatch service. "
        )
        if target_address:
            pitch += f"Our system has noted weather activity near {target_address}. "
        if asset_value > 0:
            pitch += (
                f"Based on an estimated asset value of ${asset_value:,.0f}, "
                f"our fee on settlement would be ${fee:,.0f}. "
            )
        pitch += "Please hold while we connect you to a specialist."

    ncco.append({
        "action":    "talk",
        "text":      pitch,
        "voiceName": "Amy",
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
            "outbound_placed":    0,
            "inbound_received":   0,
            "sms_sent":           0,
            "calls_completed":    0,
            "calls_failed":       0,
            "detected_human":     0,
            "detected_machine":   0,
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
        brain_decision: Optional[dict] = None,  # from BrainDecider.decide()
    ) -> dict:
        """
        Place an outbound strike call. Used by the Manus operator pipeline
        and the brain when an immediate dial is requested.

        When brain_decision is provided, uses ncco_dynamic_outbound() to
        customize the pitch based on GO/NO-GO decision + confidence.
        Falls back to static ncco_outbound_strike() when no brain.
        """
        if brain_decision:
            ncco = ncco_dynamic_outbound(
                target_address=target_address,
                asset_value=asset_value,
                brain_decision=brain_decision,
                operator_number=operator_number,
            )
        else:
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

    async def place_streaming_strike(
        self,
        to_number: str,
        ws_url: str,
        target_address: str = "",
        operator_number: str = "",
        broadcaster=None,
        brain_decision: Optional[dict] = None,
    ) -> dict:
        """
        Place an outbound call that streams live Kokoro TTS from the
        synthetic_brain WebSocket onto the call. Used by the
        voice_streaming_agent for high-value strikes where we want our
        own voice rather than Vonage's built-in TTS.

        Args:
            to_number:      E.164 destination phone
            ws_url:         The wss:// URL the synthetic_brain returned from
                            /register_stream — Vonage connects here to pull
                            the audio stream.
            target_address: For broadcaster payload context only.
            operator_number: Warm-forward number (optional, falls through to
                            EMPIRE_OPERATOR_NUMBER env var).
            broadcaster:    Optional empire_live.LiveBroadcaster for the
                            live dashboard feed.
            brain_decision: Optional BrainDecider output for stats.

        Returns:
            Dict from the underlying adapter (ok, uuid, status, error?).
        """
        op = operator_number or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
        ncco = ncco_stream_tts(
            ws_url=ws_url,
            target_address=target_address,
            operator_number=op,
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
        if result.get("ok"):
            self.stats.setdefault("streaming_strikes", 0)
            self.stats["streaming_strikes"] += 1

        if broadcaster and result.get("ok"):
            try:
                await broadcaster.broadcast({
                    "type":         "streaming_strike",
                    "direction":    "outbound",
                    "to":           to_number,
                    "target":       target_address,
                    "uuid":         result.get("uuid"),
                    "ws_url":       ws_url,
                    "brain_decision": (brain_decision or {}).get("decision"),
                    "confidence":   (brain_decision or {}).get("confidence"),
                })
            except Exception:
                pass
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
    brain_decider=None,
    brain_memory=None,
):
    """
    Register the voice webhooks with the FastAPI app. Call this once during
    startup. The two webhooks must be configured in your Vonage application:

      Answer URL: https://empire-ai.co.uk/api/v1/voice/answer
      Event URL:  https://empire-ai.co.uk/api/v1/voice/events
    """

    # ── DEFERRED INBOUND EVENT PROCESSOR ──────────────────────────────
    async def _post_inbound_event(
        from_number: str,
        to_number: str,
        call_uuid: str,
        conversation_uuid: str,
        target_address: str = "",
        severity: str = "",
    ):
        """Run broadcast, ntfy, and A/B update in the background
        so the NCCO is returned to Vonage without delay.

        target_address and severity can be pre-resolved by the voice_answer
        route (Phase 7 brain integration) to avoid a duplicate DB lookup.
        If empty, falls back to a quick radar_targets lookup.
        """
        # 1. Enrich with radar_targets lookup (only if not already resolved)
        if not target_address and get_db:
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

        # 2. Broadcast to live dashboards
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

        # 3. Ntfy the operator
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

        # 4. Mark this caller as converted in A/B (they called us)
        if get_db:
            try:
                db = get_db()
                db.table("ab_assignments").update({
                    "converted":    True,
                    "converted_at": datetime.now(timezone.utc).isoformat(),
                }).eq("visitor_ip", conversation_uuid).execute()
            except Exception:
                pass

    # ── INBOUND ANSWER WEBHOOK ──────────────────────────────────────────
    @app.get("/api/v1/voice/answer")
    @app.post("/api/v1/voice/answer")
    async def voice_answer(request: Request, background_tasks: BackgroundTasks):
        """
        Vonage hits this when a call comes in. Returns NCCO immediately;
        enrichment, broadcast, and ntfy run in the background.

        Phase 7: Brain-decided dynamic NCCO — the BrainDecider evaluates the
        caller's context (radar_targets + storm_forecasts) and selects the
        appropriate script (GO/NO_GO with confidence weighting). Decision is
        recorded in BrainMemory for future few-shot learning.
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

        # ── Enrich caller + consult the brain (synchronous DB + LLM) ──
        target_address = ""
        severity = ""
        city = ""
        lead_id = None
        brain_decision = None

        if get_db:
            try:
                db = get_db()
                clean_phone = from_number.lstrip("+1").lstrip("+").strip()
                res = db.table("radar_targets") \
                    .select("id, warehouse_name, address, city, state, damage_severity, asset_value") \
                    .or_(f"phone.ilike.%{clean_phone[-10:]},phone2.ilike.%{clean_phone[-10:]}") \
                    .limit(1).execute()
                if res.data:
                    row = res.data[0]
                    target_address = row.get("address", "") or ""
                    city = row.get("city", "") or ""
                    severity = row.get("damage_severity", "") or ""
                    state = row.get("state", "") or ""
                    lead_id = row.get("id")

                    # If brain_decider is wired, build target + alert and decide
                    if brain_decider is not None:
                        target = {
                            "warehouse_name": row.get("warehouse_name") or "Caller",
                            "address": target_address or "unknown",
                            "city": city,
                            "phone": from_number,
                            "email": "",
                            "website": "",
                            "raw_tags": {"types": ["commercial"]},
                        }
                        alert_summary = {
                            "event": "Inbound Call",
                            "severity": severity or "Moderate",
                            "urgency": "",
                            "area": f"{city}, {state}" if city else "",
                        }

                        # Enrich with storm_forecast if city is known
                        if city:
                            try:
                                storm_res = db.table("storm_forecasts") \
                                    .select("event, severity, urgency, area") \
                                    .ilike("area", f"%{city}%") \
                                    .order("created_at", desc=True) \
                                    .limit(1).execute()
                                if storm_res.data:
                                    s = storm_res.data[0]
                                    alert_summary["event"] = s.get("event") or alert_summary["event"]
                                    alert_summary["severity"] = s.get("severity") or alert_summary["severity"]
                                    alert_summary["area"] = s.get("area") or alert_summary["area"]
                            except Exception:
                                pass

                        # ── Retrieve similar past decisions for few-shot learning ──
                        memory_context = ""
                        if brain_memory is not None:
                            try:
                                asset_val = float(row.get("asset_value") or 0)
                                similar = await brain_memory.retrieve_similar(
                                    address=target_address or "unknown",
                                    city=city or "unknown",
                                    severity=severity or "Moderate",
                                    asset_value=asset_val,
                                    urgency_signal=alert_summary.get("event", ""),
                                    k=5,
                                    only_with_outcomes=True,
                                )
                                if similar:
                                    memory_context = _render_few_shot(similar)
                                    log.info(
                                        f"[voice] brain memory: {len(similar)} similar past leads "
                                        f"retrieved for {city or 'unknown'}"
                                    )
                            except Exception as e:
                                log.debug(f"[voice] memory retrieval: {e}")

                        try:
                            brain_decision = await brain_decider.decide(
                                target, alert_summary,
                                memory_context=memory_context,
                            )
                            log.info(
                                f"[voice] brain: {brain_decision.get('decision')} · "
                                f"confidence={brain_decision.get('confidence', 0)} · "
                                f"reasoning={brain_decision.get('reasoning', '')[:80]}"
                            )
                        except Exception as e:
                            log.warning(f"[voice] brain.decide() failed: {e}")

                        # Record the decision in brain_memory for future few-shot learning
                        if brain_decision is not None and brain_memory is not None and lead_id:
                            try:
                                urgency = round(float(brain_decision.get("confidence", 0)) * 10)
                                await brain_memory.record_decision(
                                    lead_id=lead_id,
                                    decision=brain_decision.get("decision", "NO_GO"),
                                    urgency=min(urgency, 10),
                                    reasoning=brain_decision.get("reasoning", "")[:500],
                                    address=target_address or "unknown",
                                    city=city or "unknown",
                                    severity=severity or "Moderate",
                                    asset_value=float(row.get("asset_value") or 0),
                                )
                            except Exception as e:
                                log.debug(f"[voice] brain_memory record: {e}")
            except Exception as e:
                log.debug(f"[voice] caller enrichment failed: {e}")

        # Schedule background tasks (broadcast, ntfy, AB update)
        # Pass pre-resolved target_address + severity to avoid duplicate DB lookup
        background_tasks.add_task(
            _post_inbound_event,
            from_number, to_number, call_uuid,
            params.get("conversation_uuid", ""),
            target_address,
            severity,
        )

        # Build dynamic NCCO based on brain decision
        operator_number = os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
        ncco = ncco_dynamic_inbound(
            target_address=target_address,
            severity=severity,
            brain_decision=brain_decision,
            forward_to=operator_number,
        )

        return JSONResponse(content=ncco)

    # ── BILLABLE-SECONDS THRESHOLD ─────────────────────────────────────
    _BILLABLE_SECONDS = 90   # minimum call duration (seconds) to qualify as billable

    # ── CALL BILLING PROCESSOR ─────────────────────────────────────────
    async def _process_call_billing(call_uuid: str, duration: int, event: dict):
        """
        Process billing for a completed call. Must meet the minimum
        duration threshold (90s) to be billable.

        Lookup flow:
          1. Find the call_logs record by vonage_call_id
          2. If the call had a buyer assigned, compute fee_earned
          3. Mark is_billable on the call_logs record
          4. Increment the buyer's calls_accepted counter
          5. Invalidate the switchboard's buyers cache
        """
        if duration < _BILLABLE_SECONDS:
            log.info(
                f"[voice] billing skipped: {call_uuid[:8]}... "
                f"duration={duration}s < {_BILLABLE_SECONDS}s threshold"
            )
            return
        if not get_db:
            log.warning(f"[voice] billing skipped: {call_uuid[:8]}... no get_db")
            return
        try:
            db = get_db()

            log.info(
                f"[voice] billing: processing {call_uuid[:8]}... "
                f"duration={duration}s ≥ {_BILLABLE_SECONDS}s threshold"
            )

            # 1. Find the call_logs record (created by switchboard at route time)
            cl_res = db.table("call_logs").select("id,buyer_id,payout_value,niche,status") \
                .eq("vonage_call_id", call_uuid).limit(1).execute()
            if not cl_res.data:
                log.info(
                    f"[voice] billing: no call_logs record for {call_uuid[:8]}... "
                    f"(call not routed through switchboard)"
                )
                return  # no routing record for this call_uuid
            cl = cl_res.data[0]
            buyer_id = cl.get("buyer_id")
            payout_value = float(cl.get("payout_value") or 0)

            # 2. If buyer assigned, get their fee_rate for fee computation
            fee_rate = COMMISSION_RATE  # default 3% (from conversion_funnel)
            if buyer_id:
                buyer_res = db.table("buyers").select("fee_rate").eq("id", buyer_id).limit(1).execute()
                if buyer_res.data:
                    fee_rate = float(buyer_res.data[0].get("fee_rate") or COMMISSION_RATE)

            # 3. Compute fee_earned
            fee_earned = round(payout_value * fee_rate, 2)

            # 4. Update call_logs with billing info
            db.table("call_logs").update({
                "is_billable": True,
                "fee_earned": fee_earned,
                "status": "completed",
            }).eq("id", cl["id"]).execute()

            # 5. Update buyer's calls_accepted counter
            if buyer_id:
                buyer_update = db.table("buyers").select("calls_accepted").eq("id", buyer_id).limit(1).execute()
                if buyer_update.data:
                    cur = int(buyer_update.data[0].get("calls_accepted") or 0)
                    db.table("buyers").update({"calls_accepted": cur + 1}).eq("id", buyer_id).execute()

            # 6. Invalidate switchboard's buyers cache so next route picks fresh data
            try:
                from empire_switchboard import _invalidate_buyers_cache
                _invalidate_buyers_cache()
            except Exception:
                pass

            log.info(
                f"[voice] billing: call {call_uuid} · "
                f"duration={duration}s · fee=${fee_earned} · "
                f"buyer={'yes' if buyer_id else 'no'}"
            )

        except Exception as e:
            log.warning(f"[voice] billing error: {e}")

    # ── EVENT WEBHOOK ───────────────────────────────────────────────────
    @app.post("/api/v1/voice/events")
    async def voice_events(request: Request):
        """
        Vonage posts call lifecycle events here: ringing, answered,
        completed, etc. Also receives advanced_machine_detection results
        (status = "human" | "machine"). We log AMD results to track
        detection rates and push to the live dashboard.
        """
        try:
            event = await request.json()
        except Exception:
            event = {}

        status     = event.get("status", "unknown")
        call_uuid  = event.get("uuid", "")
        direction  = event.get("direction", "")
        duration   = int(event.get("duration", 0) or 0)

        # ── Update stats ────────────────────────────────────────────
        if status == "completed":
            router.stats["calls_completed"] += 1
            # Fire-and-forget billing processor (background task so the
            # event response is returned to Vonage without delay)
            asyncio.ensure_future(_process_call_billing(call_uuid, duration, event))
        elif status in ("failed", "rejected", "busy", "timeout"):
            router.stats["calls_failed"] += 1
        elif status == "human":
            router.stats["detected_human"] += 1
            log.info(
                f"[voice] AMD: human detected on {call_uuid} · "
                f"from {event.get('from', '?')}"
            )
        elif status == "machine":
            router.stats["detected_machine"] += 1
            sub = event.get("sub_state", "unknown")
            log.info(
                f"[voice] AMD: machine detected on {call_uuid} · "
                f"sub_state={sub} · from {event.get('from', '?')}"
            )

        # ── Persist to call_events table ────────────────────────────
        if get_db:
            try:
                db = get_db()
                meta = dict(event)
                # Normalize call identifiers so human/machine events
                # can be joined with their parent call record
                db.table("call_events").insert({
                    "call_uuid":  call_uuid,
                    "status":     status,
                    "direction":  direction,
                    "duration":   int(duration) if duration else 0,
                    "sub_state":  event.get("sub_state", None),
                    "meta":       meta,
                }).execute()
            except Exception as e:
                # call_events table optional; warn but don't fail
                log.debug(f"[voice] call_events insert: {e}")

        # ── Push to live dashboards ──────────────────────────────────
        if broadcaster:
            try:
                payload = {
                    "type":      "call_event",
                    "status":    status,
                    "uuid":      call_uuid,
                    "direction": direction,
                    "duration":  duration,
                }
                # Include AMD detail when present so the dashboard
                # can surface machine/human detection in real-time
                if status in ("human", "machine"):
                    payload["amd"] = {
                        "result":    status,
                        "sub_state": event.get("sub_state", ""),
                    }
                await broadcaster.broadcast(payload)
            except Exception:
                pass

        return PlainTextResponse("ok", status_code=200)

    # ── OPERATOR: PLACE OUTBOUND STRIKE (with brain-decided NCCO) ──
    if require_auth:
        @app.post("/api/v1/voice/strike")
        async def voice_strike(request: Request, auth: bool = Depends(require_auth)):
            # Optional target_id/lead_id in the body → look up the SI strategy
            # chosen at strike time so the NCCO script aligns with it.
            try:
                _voice_body_preview = await request.json()
            except Exception:
                _voice_body_preview = {}
            _voice_target_id = _voice_body_preview.get("target_id") or _voice_body_preview.get("lead_id")
            _voice_strategy = None
            _voice_niche = None
            if _voice_target_id and get_db:
                try:
                    db_v = get_db()
                    _sr = db_v.table("strike_log").select("meta") \
                        .eq("target_id", _voice_target_id) \
                        .order("created_at", desc=True).limit(1).execute()
                    if _sr.data:
                        _meta = _sr.data[0].get("meta") or {}
                        if isinstance(_meta, str):
                            try: _meta = __import__("json").loads(_meta)
                            except Exception: _meta = {}
                        _voice_strategy = (_meta or {}).get("strategy")
                        _voice_niche = (_meta or {}).get("niche")
                except Exception as e:
                    log.debug(f"[voice.strike] strategy lookup failed: {e}")
            # Note: _voice_strategy / _voice_niche will be folded into the
            # brain_decision dict below (after decide() returns) so the NCCO
            # builder inside place_strike_call can read them.
            """
            Operator endpoint to trigger an outbound strike call.
            Enriches target from radar_targets + storm_forecasts, consults
            the brain for a GO/NO-GO decision + few-shot memory, then
            generates a dynamic NCCO based on the decision.

            Body: {to: "+12145551234", target_address: "...", asset_value: 2500000}
            """
            try:
                body = await request.json()
            except Exception:
                body = {}
            to_number      = body.get("to", "")
            target_address = body.get("target_address", "")
            asset_value    = float(body.get("asset_value", 0) or 0)
            severity       = body.get("severity", "")

            if not to_number:
                raise HTTPException(400, "to (phone number) required")

            operator = os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
            brain_decision = None
            # Initialize variables that may be set inside the enrichment block
            state = ""

            # ── Enrich + consult the brain for outbound strikes ──
            if brain_decider is not None and get_db:
                try:
                    db = get_db()
                    clean = to_number.lstrip("+1").lstrip("+").strip()
                    res = db.table("radar_targets") \
                        .select("id, warehouse_name, address, city, state, damage_severity, asset_value") \
                        .or_(f"phone.ilike.%{clean[-10:]},phone2.ilike.%{clean[-10:]}") \
                        .limit(1).execute()
                    lead_id = None
                    city = ""
                    state = ""
                    target_addr = target_address

                    if res.data:
                        row = res.data[0]
                        target_addr = row.get("address", "") or target_address
                        city = row.get("city", "") or ""
                        state = row.get("state", "") or ""
                        severity = row.get("damage_severity", "") or severity
                        asset_value = float(row.get("asset_value") or 0) or asset_value
                        lead_id = row.get("id")

                    target = {
                        "warehouse_name": (res.data[0].get("warehouse_name") if res.data else None) or "Prospect",
                        "address": target_addr or "unknown",
                        "city": city or "unknown",
                        "phone": to_number,
                        "email": "",
                        "website": "",
                        "raw_tags": {"types": ["commercial"]},
                    }
                    alert_summary = {
                        "event": "Outbound Strike",
                        "severity": severity or "Moderate",
                        "urgency": "",
                        "area": f"{city}, {state}" if city else "",
                    }

                    if city:
                        try:
                            storm_res = db.table("storm_forecasts") \
                                .select("event, severity, urgency, area") \
                                .ilike("area", f"%{city}%") \
                                .order("created_at", desc=True).limit(1).execute()
                            if storm_res.data:
                                s = storm_res.data[0]
                                alert_summary["event"] = s.get("event") or alert_summary["event"]
                                alert_summary["severity"] = s.get("severity") or alert_summary["severity"]
                        except Exception:
                            pass

                    # Few-shot memory retrieval
                    memory_context = ""
                    if brain_memory is not None:
                        try:
                            similar = await brain_memory.retrieve_similar(
                                address=target_addr or "unknown",
                                city=city or "unknown",
                                severity=severity or "Moderate",
                                asset_value=asset_value,
                                urgency_signal=alert_summary.get("event", ""),
                                k=5,
                                only_with_outcomes=True,
                            )
                            if similar:
                                memory_context = _render_few_shot(similar)
                                log.info(f"[voice/strike] memory: {len(similar)} similar leads retrieved")
                        except Exception as e:
                            log.debug(f"[voice/strike] memory retrieval: {e}")

                    brain_decision = await brain_decider.decide(
                        target, alert_summary,
                        memory_context=memory_context,
                    )
                    # Fold the SI-chosen strategy/niche into the brain_decision
                    # so the NCCO builder inside place_strike_call can read it.
                    if _voice_strategy and isinstance(brain_decision, dict):
                        brain_decision["si_strategy"] = _voice_strategy
                    if _voice_niche and isinstance(brain_decision, dict):
                        brain_decision["si_niche"] = _voice_niche
                    log.info(
                        f"[voice/strike] brain: {brain_decision.get('decision')} · "
                        f"confidence={brain_decision.get('confidence', 0)}"
                    )

                    # Record decision in memory
                    if brain_memory is not None and lead_id:
                        try:
                            urg = round(float(brain_decision.get("confidence", 0)) * 10)
                            await brain_memory.record_decision(
                                lead_id=lead_id,
                                decision=brain_decision.get("decision", "NO_GO"),
                                urgency=min(urg, 10),
                                reasoning=brain_decision.get("reasoning", "")[:500],
                                address=target_addr or "unknown",
                                city=city or "unknown",
                                severity=severity or "Moderate",
                                asset_value=asset_value,
                            )
                        except Exception as e:
                            log.debug(f"[voice/strike] record: {e}")
                except Exception as e:
                    log.debug(f"[voice/strike] enrichment: {e}")

            # Use enriched data when DB had a match
            call_target_addr = target_addr if (res.data and target_addr) else target_address
            call_asset_val = asset_value if (res.data and float(row.get("asset_value") or 0) > 0) else float(body.get("asset_value", 0) or 0)

            result = await router.place_strike_call(
                to_number=to_number,
                target_address=call_target_addr,
                asset_value=call_asset_val,
                operator_number=operator,
                broadcaster=broadcaster,
                brain_decision=brain_decision,
            )

            # ── Create call_logs record for billing ──
            if result.get("ok") and result.get("uuid") and get_db:
                try:
                    _cl_uuid = result["uuid"]
                    _cl_niche = body.get("niche") or _voice_niche or "unknown"
                    _cl_state = body.get("state") or state or "TX"
                    _cl_caller = to_number

                    # Try to find a buyer via switchboard (synchronous function)
                    _cl_buyer = None
                    try:
                        from empire_switchboard import find_buyer
                        _cl_buyer = find_buyer(_cl_niche, _cl_state, _cl_caller, 0)
                    except Exception:
                        pass

                    _cl_db = get_db()
                    _cl_db.table("call_logs").insert({
                        "vonage_call_id": _cl_uuid,
                        "buyer_id": _cl_buyer["id"] if _cl_buyer else None,
                        "niche": _cl_niche,
                        "caller_state": _cl_state,
                        "caller_number": _cl_caller,
                        "status": "routed" if _cl_buyer else "strike",
                        "payout_value": float(_cl_buyer.get("base_payout", 0)) if _cl_buyer else 0.0,
                        "source": "strike",
                    }).execute()
                    log.info(
                        f"[voice/strike] call_logs created for {_cl_uuid[:8]}... · "
                        f"niche={_cl_niche} state={_cl_state} "
                        f"buyer={'yes' if _cl_buyer else 'no'}"
                    )
                except Exception as e:
                    log.warning(f"[voice/strike] call_logs insert failed: {e}")

            return result

        @app.get("/api/v1/voice/stats")
        async def voice_stats(auth: bool = Depends(require_auth)):
            """Live voice engine stats."""
            return {
                **router.stats,
                "vonage_enabled": router.vonage.enabled,
            }

    # Import render_few_shot here (module-level import unsafe due to potential
    # circular deps at import time — brain_memory doesn't import voice, but
    # we keep it local to the registration function for clarity).
    from empire_brain_memory import render_few_shot as _render_few_shot

    log.info("[voice] Routes registered · /api/v1/voice/{answer,events,strike,stats}")
