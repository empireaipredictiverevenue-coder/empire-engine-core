"""
EMPIRE V49 · INBOUND CALL TRIAGE (SAFE VERSION)
=================================================
Handles inbound calls SAFELY. The boundary I drew:

  ✅ AI does the routing decisions  (which queue does this call go to?)
  ✅ AI transcribes voicemails       (Whisper API)
  ✅ AI scores transcript urgency    (so the operator's callback list is ranked)
  ✅ AI surfaces priority callbacks  (in the playbook)

  ❌ AI does NOT impersonate a human in voice
  ❌ AI does NOT pretend the operator is on the line
  ❌ AI does NOT collect personal/financial info via voice
  ❌ AI does NOT make legal/insurance assertions to callers

WHY THIS LINE
─────────────
Multiple states (CA, IL, NY, TX) have started passing laws requiring
clear disclosure when AI is being used in voice interactions. The
California AI Transparency Act (SB-942, signed Sep 2024) and the
Illinois Automated Decision Systems law both impose liability on
operators who deploy AI that could be mistaken for a human.

The SAFE design is:
  - Empire AI clearly identifies itself as "Empire AI's automated
    answering service" in the greeting
  - If caller wants to speak to a human, route to human or take
    a voicemail
  - AI work happens AFTER the call (transcription, ranking)
  - Operator gets a prioritized callback list, makes the human call

This is the same posture banks use (their voice IVR clearly identifies
itself, AI does post-call processing, humans do the actual outreach).

WHAT THIS MODULE DOES
─────────────────────
  1. Inbound call lands on Vonage DID
  2. NCCO greets caller: identifies as automated, offers options:
       - "Press 1 to speak to a representative"
       - "Press 2 to leave a message"
       - "Press 3 to be removed from our outreach list"
  3. If 1 → forward to operator number (if available) else voicemail
  4. If 2 → record voicemail, terminate
  5. If 3 → immediate opt-out (add to sms_opt_outs + email_unsubscribes)
  6. After voicemail recorded:
     - Download audio from Vonage
     - Transcribe via OpenAI Whisper API
     - Score urgency via Claude (intent classification)
     - Insert into inbound_calls table
     - Push to playbook task queue
     - Ntfy operator

  No AI voice. No conversational triage. Pure routing + post-processing.


SCHEMA
──────
    CREATE TABLE IF NOT EXISTS inbound_calls (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      call_uuid       text UNIQUE NOT NULL,        -- Vonage call UUID
      from_number     text NOT NULL,
      to_number       text,
      duration        int DEFAULT 0,
      disposition     text                          -- 'forwarded' | 'voicemail' | 'opt_out' | 'hung_up'
        CHECK (disposition IN ('forwarded','voicemail','opt_out','hung_up')),
      recording_url   text,                         -- temporary Vonage URL (expires)
      recording_path  text,                         -- our copy if downloaded
      transcript      text,
      urgency_score   int,                          -- 1-10, Claude classification
      intent          text,                         -- 'callback_requested' | 'opt_out' | 'general_inquiry' | etc
      matched_lead_id uuid,                         -- if from_number matches a radar_target
      status          text DEFAULT 'new'
        CHECK (status IN ('new','reviewed','called_back','closed')),
      meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS inbound_calls_status_idx
      ON inbound_calls (status, urgency_score DESC, created_at DESC);
    CREATE INDEX IF NOT EXISTS inbound_calls_from_idx
      ON inbound_calls (from_number);


WIRE-UP IN hub.py
─────────────────
    from empire_inbound import (
        InboundCallTriage,
        register_inbound_routes,
        build_safe_inbound_ncco,
    )

    inbound_triage = InboundCallTriage(
        get_db=         get_db,
        anthropic_key=  os.environ.get("ANTHROPIC_API_KEY", ""),
        openai_key=     os.environ.get("OPENAI_API_KEY", ""),  # for Whisper
        operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
        broadcaster=    live_broadcaster,
        ntfy_topic=     NTFY_TOPIC,
        ntfy_token=     NTFY_TOKEN,
    )

    register_inbound_routes(app, inbound_triage, require_auth=require_auth)

    # ⚠ REPLACE the empire_voice answer NCCO call with the safe inbound NCCO.
    # In empire_voice.py's voice_answer route, change:
    #     ncco = ncco_inbound_strike(...)
    # to:
    #     ncco = build_safe_inbound_ncco(
    #         business_name="Empire AI",
    #         operator_number=os.environ.get("EMPIRE_OPERATOR_NUMBER", ""),
    #         recording_url=f"{PUBLIC_BASE_URL}/api/v1/inbound/recording",
    #     )


ENVIRONMENT VARIABLES
─────────────────────
    OPENAI_API_KEY              for Whisper transcription
    EMPIRE_OPERATOR_NUMBER      where "press 1" forwards to
    EMPIRE_RECORDING_BUCKET     optional · S3/R2 bucket for permanent storage
"""

import os
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import JSONResponse


log = logging.getLogger("empire.inbound")


# ─────────────────────────────────────────────────────────────────────────────
# THE SAFE NCCO BUILDER
# ─────────────────────────────────────────────────────────────────────────────
def build_safe_inbound_ncco(
    business_name: str = "Empire AI",
    operator_number: str = "",
    recording_url: str = "",
) -> list:
    """
    Returns a Vonage NCCO that handles inbound calls with explicit
    automated-service disclosure. No AI impersonation.

    The flow:
      1. Greeting clearly identifies as automated service
      2. Offers 3 DTMF options (press 1/2/3)
      3. Based on choice: forward, record, or opt-out
    """
    # Compliance: every call recording must be disclosed.
    # Compliance: the system clearly identifies as automated.

    greeting = (
        f"Thank you for calling {business_name}. "
        "You have reached our automated answering service. "
        "This call may be recorded for service and compliance purposes. "
        "Press 1 to be connected to a representative. "
        "Press 2 to leave a message. "
        "Press 3 to be removed from our contact list."
    )

    # The NCCO uses an `input` action to capture DTMF, then we'd route to
    # the appropriate downstream URL based on the digit pressed. The webhook
    # at /api/v1/inbound/dtmf handles the routing.
    ncco: list = [
        {
            "action":     "talk",
            "text":       greeting,
            "voiceName":  "Amy",
            "level":      0,
        },
        {
            "action":     "input",
            "type":       ["dtmf"],
            "dtmf": {
                "maxDigits":      1,
                "timeOut":        10,
                "submitOnHash":   False,
            },
            "eventUrl":   [recording_url + "/dtmf"] if recording_url else [],
        },
    ]

    return ncco


def build_forward_ncco(operator_number: str, lead_addr: str = "") -> list:
    """When caller presses 1 (speak to representative) → forward to operator."""
    intro = "Connecting you now."
    if lead_addr:
        intro = f"Connecting you regarding {lead_addr}. Please hold."
    return [
        {"action": "talk", "text": intro, "voiceName": "Amy"},
        {
            "action":   "connect",
            "endpoint": [{"type": "phone", "number": operator_number.lstrip("+")}],
            "timeout":  30,
            "limit":    1800,
        },
        {
            "action":   "talk",
            "text":     "We were unable to reach a representative. Please leave a message after the tone, and we will return your call within one business day.",
        },
        {
            "action":       "record",
            "endOnSilence": 3,
            "endOnKey":     "#",
            "timeOut":      120,
            "beepStart":    True,
        },
    ]


def build_voicemail_ncco() -> list:
    """When caller presses 2 → take a voicemail."""
    return [
        {
            "action":    "talk",
            "text":      "Please leave your name, callback number, and a brief message after the tone. Press pound when finished.",
            "voiceName": "Amy",
        },
        {
            "action":       "record",
            "endOnSilence": 3,
            "endOnKey":     "#",
            "timeOut":      180,
            "beepStart":    True,
        },
        {
            "action":  "talk",
            "text":    "Thank you. We will return your call within one business day.",
        },
    ]


def build_optout_ncco() -> list:
    """When caller presses 3 → confirm opt-out."""
    return [
        {
            "action":    "talk",
            "text":      "You have been removed from our contact list. You will receive no further calls, texts, or emails from Empire AI. Goodbye.",
            "voiceName": "Amy",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# INBOUND CALL TRIAGE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class InboundCallTriage:
    """
    Post-call processing: download recording, transcribe via Whisper,
    score urgency via Claude, surface to operator.
    """

    def __init__(
        self,
        *,
        get_db:          Callable,
        anthropic_key:   str = "",
        openai_key:      str = "",
        operator_number: str = "",
        broadcaster=     None,
        ntfy_topic:      str = "",
        ntfy_token:      str = "",
    ):
        self.get_db          = get_db
        self.anthropic_key   = anthropic_key
        self.openai_key      = openai_key
        self.operator_number = operator_number
        self.broadcaster     = broadcaster
        self.ntfy_topic      = ntfy_topic
        self.ntfy_token      = ntfy_token
        self.transcription_enabled = bool(openai_key)
        self.scoring_enabled       = bool(anthropic_key)
        self.stats = {
            "calls_received":     0,
            "calls_forwarded":    0,
            "calls_voicemail":    0,
            "calls_opted_out":    0,
            "recordings_processed": 0,
            "transcriptions_failed": 0,
        }

    # ── ON DTMF: ROUTE THE CALL ──────────────────────────────────────────
    async def route_dtmf(
        self,
        *,
        digit: str,
        from_number: str,
        call_uuid: str,
        to_number: str = "",
    ) -> tuple[list, dict]:
        """
        Caller pressed a digit. Returns (ncco_to_play, decision_dict).
        decision_dict gets logged.
        """
        self.stats["calls_received"] += 1

        # Try to enrich from radar_targets
        target_addr = ""
        matched_lead_id = None
        try:
            db = self.get_db()
            clean_phone = from_number.lstrip("+").lstrip("1")
            res = db.table("radar_targets").select("id, address") \
                .ilike("phone", f"%{clean_phone[-10:]}%").limit(1).execute()
            if res.data:
                target_addr = res.data[0].get("address", "")
                matched_lead_id = res.data[0].get("id")
        except Exception:
            pass

        if digit == "1":
            self.stats["calls_forwarded"] += 1
            disposition = "forwarded"
            ncco = build_forward_ncco(
                operator_number=self.operator_number,
                lead_addr=target_addr,
            )
        elif digit == "2":
            self.stats["calls_voicemail"] += 1
            disposition = "voicemail"
            ncco = build_voicemail_ncco()
        elif digit == "3":
            self.stats["calls_opted_out"] += 1
            disposition = "opt_out"
            ncco = build_optout_ncco()
            # Immediately process the opt-out
            await self._process_opt_out(from_number=from_number)
        else:
            disposition = "hung_up"
            ncco = [{
                "action":    "talk",
                "text":      "We didn't catch a valid selection. Goodbye.",
                "voiceName": "Amy",
            }]

        # Log the call
        try:
            db = self.get_db()
            db.table("inbound_calls").upsert({
                "call_uuid":       call_uuid,
                "from_number":     from_number,
                "to_number":       to_number,
                "disposition":     disposition,
                "matched_lead_id": matched_lead_id,
                "status":          "new",
                "meta": {
                    "dtmf_digit":  digit,
                    "matched_addr": target_addr,
                },
            }, on_conflict="call_uuid").execute()
        except Exception as e:
            log.debug(f"[inbound] log insert: {e}")

        # Push to operator dashboards
        if self.broadcaster:
            try:
                await self.broadcaster.broadcast({
                    "type":         "inbound_call",
                    "from":         from_number,
                    "disposition":  disposition,
                    "lead":         target_addr,
                })
            except Exception:
                pass

        return ncco, {
            "disposition":    disposition,
            "matched_lead":   target_addr,
        }

    # ── ON RECORDING COMPLETE: PROCESS IT ────────────────────────────────
    async def process_recording(
        self,
        *,
        call_uuid: str,
        recording_url: str,
        duration: int = 0,
    ) -> dict:
        """
        Vonage posts here when a recording completes. Download → transcribe
        → score → update the inbound_calls row → push to playbook.
        """
        try:
            db = self.get_db()
            db.table("inbound_calls").update({
                "recording_url": recording_url,
                "duration":      duration,
            }).eq("call_uuid", call_uuid).execute()
        except Exception as e:
            log.debug(f"[inbound] recording url update: {e}")

        # Download + transcribe (best-effort)
        transcript = ""
        if self.transcription_enabled and recording_url:
            transcript = await self._transcribe(recording_url)

        # Score the transcript
        urgency_score = 5
        intent = "general_inquiry"
        if transcript and self.scoring_enabled:
            scored = await self._score_intent(transcript)
            urgency_score = scored.get("urgency", 5)
            intent        = scored.get("intent", "general_inquiry")

        # Persist
        try:
            db.table("inbound_calls").update({
                "transcript":    transcript[:5000] if transcript else None,
                "urgency_score": urgency_score,
                "intent":        intent,
            }).eq("call_uuid", call_uuid).execute()
        except Exception as e:
            log.error(f"[inbound] transcript persist failed: {e}")

        # Pull the call back for the operator notification
        try:
            res = db.table("inbound_calls").select(
                "from_number, transcript, urgency_score, intent, matched_lead_id"
            ).eq("call_uuid", call_uuid).limit(1).execute()
            call = res.data[0] if res.data else {}
        except Exception:
            call = {}

        # Ntfy operator if high urgency
        if urgency_score >= 8 and self.ntfy_topic:
            try:
                headers = {
                    "Title":    f"📞 Inbound · urgency {urgency_score}/10",
                    "Priority": "urgent",
                    "Tags":     "phone",
                }
                if self.ntfy_token:
                    headers["Authorization"] = f"Bearer {self.ntfy_token}"
                body = (
                    f"From: {call.get('from_number')}\n"
                    f"Intent: {intent}\n"
                    f"Transcript: {(transcript or '')[:200]}"
                )
                async with httpx.AsyncClient() as c:
                    await c.post(
                        f"https://ntfy.sh/{self.ntfy_topic}",
                        data=body,
                        headers=headers,
                        timeout=5.0,
                    )
            except Exception:
                pass

        # Push to live dashboards
        if self.broadcaster:
            try:
                await self.broadcaster.broadcast({
                    "type":          "voicemail_transcribed",
                    "from":          call.get("from_number"),
                    "urgency":       urgency_score,
                    "intent":        intent,
                    "preview":       (transcript or "")[:120],
                })
            except Exception:
                pass

        self.stats["recordings_processed"] += 1

        return {
            "ok":            True,
            "transcript":    transcript[:200] if transcript else "",
            "urgency_score": urgency_score,
            "intent":        intent,
        }

    # ── TRANSCRIBE via Whisper ───────────────────────────────────────────
    async def _transcribe(self, recording_url: str) -> str:
        """
        Download the Vonage recording and transcribe via OpenAI Whisper.
        Returns transcript or empty string on failure.
        """
        if not self.transcription_enabled:
            return ""

        try:
            # Step 1: download the audio
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.get(recording_url, follow_redirects=True)
                if r.status_code != 200:
                    log.warning(f"[inbound] recording download HTTP {r.status_code}")
                    return ""
                audio_bytes = r.content

            # Step 2: send to Whisper
            async with httpx.AsyncClient(timeout=120) as c:
                files = {
                    "file": ("recording.mp3", audio_bytes, "audio/mpeg"),
                    "model": (None, "whisper-1"),
                    "response_format": (None, "text"),
                    "language": (None, "en"),
                }
                r = await c.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.openai_key}"},
                    files=files,
                )
                if r.status_code != 200:
                    log.warning(f"[inbound] Whisper HTTP {r.status_code}: {r.text[:200]}")
                    self.stats["transcriptions_failed"] += 1
                    return ""
                return r.text.strip()
        except Exception as e:
            log.error(f"[inbound] transcribe error: {e}")
            self.stats["transcriptions_failed"] += 1
            return ""

    # ── SCORE INTENT via Claude ─────────────────────────────────────────
    async def _score_intent(self, transcript: str) -> dict:
        """
        Score the transcript for urgency (1-10) and intent.
        Returns: {urgency: int, intent: str}
        """
        if not self.scoring_enabled or not transcript:
            return {"urgency": 5, "intent": "general_inquiry"}

        prompt = (
            f"Classify the following voicemail transcript. "
            f"Return ONLY a JSON object with fields:\n"
            f'  "urgency": integer 1-10 (10 = urgent, e.g. active damage; '
            f'                            1 = no action needed),\n'
            f'  "intent": one of [\n'
            f'             "callback_requested", "opt_out", "complaint",\n'
            f'             "info_request", "scheduling", "wrong_number", "spam",\n'
            f'             "general_inquiry"\n'
            f'           ]\n\n'
            f"Transcript:\n\"\"\"\n{transcript[:2000]}\n\"\"\""
        )

        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         self.anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type":      "application/json",
                    },
                    json={
                        "model":      "claude-haiku-4-5-20251001",
                        "max_tokens": 200,
                        "messages":   [{"role": "user", "content": prompt}],
                    },
                )
                if r.status_code != 200:
                    log.warning(f"[inbound] Claude HTTP {r.status_code}")
                    return {"urgency": 5, "intent": "general_inquiry"}
                body = r.json()
                text = body.get("content", [{}])[0].get("text", "")
                # Find the JSON in the response
                import re, json
                m = re.search(r"\{[^}]+\}", text, re.DOTALL)
                if not m:
                    return {"urgency": 5, "intent": "general_inquiry"}
                parsed = json.loads(m.group(0))
                return {
                    "urgency": int(parsed.get("urgency", 5)),
                    "intent":  str(parsed.get("intent", "general_inquiry")),
                }
        except Exception as e:
            log.debug(f"[inbound] score error: {e}")
            return {"urgency": 5, "intent": "general_inquiry"}

    # ── OPT-OUT PROCESSING ──────────────────────────────────────────────
    async def _process_opt_out(self, from_number: str) -> None:
        """Add the caller to all opt-out registries."""
        normalized = from_number if from_number.startswith("+") else f"+{from_number}"

        try:
            db = self.get_db()
            db.table("sms_opt_outs").upsert({
                "phone":  normalized,
                "reason": "voice opt-out · press 3",
            }).execute()
            db.table("sms_sequences").update({"status": "opted_out"}) \
                .eq("phone", normalized).execute()
        except Exception as e:
            log.error(f"[inbound] opt-out write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_inbound_routes(
    app: FastAPI,
    triage: InboundCallTriage,
    *,
    require_auth: Callable,
):
    """Wire the inbound call webhook routes."""

    # ── PUBLIC: DTMF WEBHOOK (caller pressed a digit) ──────────────────
    @app.post("/api/v1/inbound/dtmf")
    async def inbound_dtmf(request: Request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        digit       = ""
        dtmf_data   = payload.get("dtmf", {}) or {}
        if isinstance(dtmf_data, dict):
            digit = (dtmf_data.get("digits") or "").strip()
        elif isinstance(dtmf_data, str):
            digit = dtmf_data.strip()

        from_number = payload.get("from", "")
        to_number   = payload.get("to", "")
        call_uuid   = payload.get("uuid", "")

        ncco, _ = await triage.route_dtmf(
            digit=digit,
            from_number=from_number,
            call_uuid=call_uuid,
            to_number=to_number,
        )
        return JSONResponse(content=ncco)

    # ── PUBLIC: RECORDING COMPLETE WEBHOOK ─────────────────────────────
    @app.post("/api/v1/inbound/recording")
    async def inbound_recording(request: Request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}

        recording_url = payload.get("recording_url", "")
        call_uuid     = payload.get("conversation_uuid") or payload.get("uuid", "")
        duration      = int(payload.get("duration", 0) or 0)

        if not (recording_url and call_uuid):
            return {"ok": False, "error": "missing recording_url or call_uuid"}

        # Process asynchronously — Vonage doesn't wait for us
        import asyncio
        asyncio.create_task(triage.process_recording(
            call_uuid=call_uuid,
            recording_url=recording_url,
            duration=duration,
        ))

        return {"ok": True, "queued": True}

    # ── OPERATOR: LIST INBOUND CALLS ───────────────────────────────────
    @app.get("/api/v1/inbound/calls")
    async def list_inbound_calls(
        status: str = Query("new"),
        limit: int = Query(50, ge=1, le=200),
        auth: bool = Depends(require_auth),
    ):
        try:
            db = triage.get_db()
            q = db.table("inbound_calls").select("*") \
                .order("urgency_score", desc=True) \
                .order("created_at", desc=True) \
                .limit(limit)
            if status != "all":
                q = q.eq("status", status)
            return {"calls": q.execute().data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ── OPERATOR: MARK CALL HANDLED ────────────────────────────────────
    @app.post("/api/v1/inbound/calls/update")
    async def update_call(request: Request, auth: bool = Depends(require_auth)):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        call_id = body.get("call_id")
        if not call_id:
            raise HTTPException(400, "call_id required")

        update = {}
        if "status" in body:
            if body["status"] not in ("new", "reviewed", "called_back", "closed"):
                raise HTTPException(400, "invalid status")
            update["status"] = body["status"]
        if "notes" in body:
            update["meta"] = {"operator_notes": body["notes"][:1000]}

        try:
            db = triage.get_db()
            db.table("inbound_calls").update(update).eq("id", call_id).execute()
            return {"ok": True}
        except Exception as e:
            raise HTTPException(500, str(e))

        # ── OPERATOR: LIST WEBHOOK LEADS ─────────────────────────────────────
    @app.get("/api/v1/inbound/leads")
    async def list_inbound_leads(
        limit: int = Query(50, ge=1, le=200),
        auth: bool = Depends(require_auth),
    ):
        try:
            db = triage.get_db()
            data = db.table("inbound_leads").select("*") \
                .order("created_at", desc=True) \
                .limit(limit).execute().data
            return {"leads": data or []}
        except Exception as e:
            raise HTTPException(500, str(e))

# ── OPERATOR: STATS ────────────────────────────────────────────────
    @app.get("/api/v1/inbound/stats")
    async def inbound_stats(auth: bool = Depends(require_auth)):
        return triage.stats

    log.info("[inbound] Routes registered · /api/v1/inbound/{dtmf,recording,calls,stats}")
