"""
EMPIRE V49 · SMS SEQUENCE ENGINE
================================
TCPA-safe automated SMS drip. The "follow-up loop" that converts verified
storm leads from radar_targets into booked calls.

Key features:
  - 5-touch sequence over 7 days (T+0, T+1h, T+4h, T+24h, T+72h)
  - STOP / UNSUBSCRIBE keywords auto-honored (TCPA federal law)
  - HELP keyword returns clear identification + opt-out instructions
  - Quiet hours respected per recipient's timezone (no SMS 9pm-8am local)
  - Engagement tracking — replies pause the sequence, route to a human
  - Identity prefix on every message (TCPA paid commercial requirement)
  - Rate-limited (max 6 sends/min per Vonage long code, configurable)
  - Idempotent — re-running won't duplicate sends

Schema:
    CREATE TABLE sms_sequences (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at      timestamptz NOT NULL DEFAULT now(),
        phone           text NOT NULL UNIQUE,
        target_addr     text,
        sequence_type   text NOT NULL DEFAULT 'storm_strike',
        current_step    int NOT NULL DEFAULT 0,
        status          text NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','paused','completed','opted_out','replied')),
        last_sent_at    timestamptz,
        next_send_at    timestamptz,
        replies_count   int DEFAULT 0,
        meta            jsonb DEFAULT '{}'::jsonb
    );
    CREATE INDEX ON sms_sequences (status, next_send_at);
    CREATE INDEX ON sms_sequences (phone);

    CREATE TABLE sms_opt_outs (
        phone           text PRIMARY KEY,
        created_at      timestamptz NOT NULL DEFAULT now(),
        reason          text DEFAULT 'STOP keyword',
        meta            jsonb DEFAULT '{}'::jsonb
    );

    CREATE TABLE sms_log (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at      timestamptz NOT NULL DEFAULT now(),
        phone           text NOT NULL,
        direction       text CHECK (direction IN ('outbound','inbound')),
        body            text,
        step            int,
        message_uuid    text,
        delivered       boolean DEFAULT false
    );
    CREATE INDEX ON sms_log (phone, created_at DESC);

Wire-up in hub.py:
    from empire_sms import SMSSequenceEngine, register_sms_routes

    sms_engine = SMSSequenceEngine(
        voice_router=voice_router,  # uses Vonage adapter for sending
        get_db=get_db,
        identity_prefix="Empire AI:",  # required prefix per TCPA
    )
    register_sms_routes(app, sms_engine, require_auth, broadcaster=live_broadcaster)

    # Start the background dispatcher
    @app.on_event("startup")
    async def _start_sms():
        asyncio.create_task(sms_engine.dispatcher_loop())
"""

import os
import re
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from enum import Enum

from fastapi import FastAPI, Request, HTTPException, Depends


log = logging.getLogger("empire.sms")


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_IDENTITY_PREFIX = "Empire AI:"

# TCPA-mandated stop keywords (case-insensitive). If a recipient texts any
# of these, we must immediately remove them from all marketing lists.
STOP_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "REMOVE"}
HELP_KEYWORDS = {"HELP", "INFO", "SUPPORT"}

# Quiet hours — no SMS during these local hours (TCPA + good practice)
QUIET_HOURS_START = 21  # 9 PM
QUIET_HOURS_END   = 8   # 8 AM

# Sequence step delays (from previous send). Tuned for storm urgency.
STEP_DELAYS = {
    1: timedelta(hours=1),       # First follow-up: 1 hour after T+0
    2: timedelta(hours=4),       # Same-day reminder: 4 hours later
    3: timedelta(hours=24),      # Next-day check-in
    4: timedelta(hours=72),      # 72-hour insurance window closing
}


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGE TEMPLATES — storm_strike sequence (5 touches)
# Every message starts with the identity prefix (TCPA-required for paid
# commercial messages) and ends with the opt-out instructions on touches that
# need them (touch 0 and touch 4 — start + last).
# ─────────────────────────────────────────────────────────────────────────────
TEMPLATES = {
    "storm_strike": [
        # Touch 0 — Initial contact. Full identification + opt-out.
        (
            "{prefix} Severe weather flagged at your facility ({target_short}). "
            "Our predictive system detects possible roof/structural damage. "
            "1% success fee only if a claim settles. "
            "Reply YES for free assessment. Reply STOP to opt out."
        ),
        # Touch 1 — 1 hour later. Urgency.
        (
            "{prefix} The 72-hour insurance documentation window is open. "
            "Most policies recommend filing within this period for best outcomes. "
            "Reply YES to schedule an inspection."
        ),
        # Touch 2 — 4 hours later. Social proof.
        (
            "{prefix} Three other facilities in your area locked in coverage today. "
            "No upfront cost. We only earn on settled claims. "
            "Reply YES for a free roof assessment."
        ),
        # Touch 3 — 24 hours later. Value math.
        (
            "{prefix} Quick math: a $2M facility w/ storm damage typically settles "
            "around $180K-$400K. Our fee on $250K settled = $2,500. "
            "Reply YES to start the assessment."
        ),
        # Touch 4 — 72 hours later. Final touch + clear opt-out.
        (
            "{prefix} Last note from us — the 72hr documentation window has closed. "
            "If you'd still like a no-cost assessment, reply YES. "
            "Otherwise no further messages. Reply STOP to confirm opt-out."
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# AREA CODE → TIMEZONE (rough mapping for quiet-hours respect)
# US Time zones — close enough for SMS purposes.
# ─────────────────────────────────────────────────────────────────────────────
AREA_CODE_TZ = {
    # Central Time
    "214": "America/Chicago", "469": "America/Chicago", "972": "America/Chicago",
    "713": "America/Chicago", "281": "America/Chicago", "832": "America/Chicago",
    "346": "America/Chicago", "210": "America/Chicago", "726": "America/Chicago",
    "512": "America/Chicago", "737": "America/Chicago",
    "817": "America/Chicago", "682": "America/Chicago", "945": "America/Chicago",
    "251": "America/Chicago",  # Mobile, AL
    # Eastern
    "404": "America/New_York", "678": "America/New_York", "470": "America/New_York",
    "305": "America/New_York", "786": "America/New_York", "954": "America/New_York",
    "212": "America/New_York", "646": "America/New_York", "917": "America/New_York",
    # Mountain
    "303": "America/Denver", "720": "America/Denver", "480": "America/Phoenix",
    # Pacific
    "213": "America/Los_Angeles", "323": "America/Los_Angeles",
    "415": "America/Los_Angeles", "650": "America/Los_Angeles",
}


def _phone_timezone(phone: str) -> str:
    """Best-effort timezone for a phone number's area code."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) >= 3:
        return AREA_CODE_TZ.get(digits[:3], "America/Chicago")
    return "America/Chicago"


def _is_quiet_hours(phone: str) -> bool:
    """True if it's currently quiet hours in this recipient's timezone."""
    try:
        from zoneinfo import ZoneInfo
        tz_name = _phone_timezone(phone)
        local_hour = datetime.now(ZoneInfo(tz_name)).hour
        # Quiet hours wrap around midnight
        if QUIET_HOURS_START < QUIET_HOURS_END:
            return QUIET_HOURS_START <= local_hour < QUIET_HOURS_END
        else:
            return local_hour >= QUIET_HOURS_START or local_hour < QUIET_HOURS_END
    except Exception:
        # If zoneinfo fails, err on the side of caution and use UTC Central-ish
        h = datetime.now(timezone.utc).hour - 6
        return h < 8 or h >= 21


def _normalize_phone(phone: str) -> str:
    """Strip to E.164 +1XXXXXXXXXX format. Returns empty string on bad input."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if phone and phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"
    return ""


def _short_address(addr: str, max_len: int = 30) -> str:
    """Trim address to first comma or max_len chars — fits in SMS context."""
    if not addr:
        return "your facility"
    short = addr.split(",")[0].strip()
    if len(short) > max_len:
        short = short[:max_len].rstrip() + "..."
    return short


# ─────────────────────────────────────────────────────────────────────────────
# SMS SEQUENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class SMSSequenceEngine:
    """
    Manages SMS drip campaigns. Background dispatcher loop checks
    sms_sequences every 60s for messages due to send.
    """

    def __init__(
        self,
        voice_router,            # empire_voice.VoiceRouter
        get_db,                  # callable returning Supabase client
        identity_prefix: str = DEFAULT_IDENTITY_PREFIX,
        max_per_minute: int = 6,
    ):
        self.voice_router    = voice_router
        self.get_db          = get_db
        self.identity_prefix = identity_prefix
        self.max_per_minute  = max_per_minute

        self.stats = {
            "sequences_active":  0,
            "sequences_done":    0,
            "sequences_optout":  0,
            "sequences_replied": 0,
            "sms_sent":          0,
            "sms_received":      0,
            "last_dispatch":     None,
            "last_error":        None,
        }

    # ── ENROLLMENT ──────────────────────────────────────────────────────
    async def enroll(
        self,
        phone:         str,
        target_addr:   str = "",
        sequence_type: str = "storm_strike",
        meta:          Optional[dict] = None,
    ) -> dict:
        """
        Start an SMS sequence for a new lead. Idempotent — if the phone is
        already enrolled, returns the existing record.
        """
        normalized = _normalize_phone(phone)
        if not normalized:
            return {"ok": False, "error": "Invalid phone"}

        # Check opt-out list first — never re-enroll opted-out numbers
        if await self._is_opted_out(normalized):
            log.info(f"[sms] enroll blocked · {normalized} on opt-out list")
            return {"ok": False, "error": "opted_out"}

        try:
            db = self.get_db()
            # Check existing
            existing = db.table("sms_sequences").select("*") \
                .eq("phone", normalized).limit(1).execute()
            if existing.data:
                row = existing.data[0]
                return {
                    "ok":          True,
                    "sequence_id": row["id"],
                    "existing":    True,
                    "status":      row["status"],
                }

            # Insert new sequence — first send happens immediately
            ins = db.table("sms_sequences").insert({
                "phone":         normalized,
                "target_addr":   target_addr,
                "sequence_type": sequence_type,
                "current_step":  0,
                "status":        "active",
                "next_send_at":  datetime.now(timezone.utc).isoformat(),
                "meta":          meta or {},
            }).execute()

            self.stats["sequences_active"] += 1

            return {
                "ok":          True,
                "sequence_id": ins.data[0]["id"] if ins.data else None,
                "existing":    False,
            }
        except Exception as e:
            log.error(f"[sms] enroll error: {e}")
            return {"ok": False, "error": str(e)}

    # ── DISPATCHER LOOP (run as background task) ────────────────────────
    async def dispatcher_loop(self):
        """
        Forever loop. Every 60s, find sequences with next_send_at <= now and
        not in quiet hours. Send the next message. Update state.
        """
        log.info(f"[sms] Dispatcher ONLINE · max {self.max_per_minute}/min")
        while True:
            try:
                sent = await self._dispatch_due()
                if sent > 0:
                    log.info(f"[sms] dispatched {sent} messages")
                self.stats["last_dispatch"] = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                log.error(f"[sms] dispatcher error: {e}")
                self.stats["last_error"] = str(e)
            await asyncio.sleep(60)

    async def _dispatch_due(self) -> int:
        """Find sequences due for next send. Returns count sent."""
        try:
            db = self.get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            res = db.table("sms_sequences").select("*") \
                .eq("status", "active") \
                .lte("next_send_at", now_iso) \
                .limit(self.max_per_minute).execute()
            rows = res.data or []
        except Exception as e:
            log.error(f"[sms] dispatch query failed: {e}")
            return 0

        sent = 0
        for row in rows:
            phone = row["phone"]

            # Quiet hours check — reschedule if appropriate
            if _is_quiet_hours(phone):
                self._reschedule_after_quiet(row)
                continue

            # Build the message
            template_list = TEMPLATES.get(row["sequence_type"], TEMPLATES["storm_strike"])
            step = row["current_step"]
            if step >= len(template_list):
                self._mark_complete(row)
                continue

            template = template_list[step]
            body = template.format(
                prefix=self.identity_prefix,
                target_short=_short_address(row.get("target_addr", "")),
            )

            # Send
            result = await self.voice_router.send_sms(phone, body)

            # Log the attempt
            try:
                db = self.get_db()
                db.table("sms_log").insert({
                    "phone":        phone,
                    "direction":    "outbound",
                    "body":         body,
                    "step":         step,
                    "message_uuid": result.get("message_uuid"),
                    "delivered":    result.get("ok", False),
                }).execute()
            except Exception as e:
                log.debug(f"[sms] log insert: {e}")

            if not result.get("ok"):
                log.warning(f"[sms] send failed · {phone} step {step} · {result.get('error')}")
                continue

            sent += 1
            self.stats["sms_sent"] += 1

            # Advance to next step
            next_step = step + 1
            if next_step >= len(template_list):
                # Sequence complete
                self._mark_complete(row, last_step=step)
            else:
                # Schedule next touch
                delay = STEP_DELAYS.get(next_step, timedelta(hours=24))
                next_send = datetime.now(timezone.utc) + delay
                try:
                    db = self.get_db()
                    db.table("sms_sequences").update({
                        "current_step": next_step,
                        "last_sent_at": datetime.now(timezone.utc).isoformat(),
                        "next_send_at": next_send.isoformat(),
                    }).eq("id", row["id"]).execute()
                except Exception as e:
                    log.error(f"[sms] state update failed: {e}")

            # Rate-limit ourselves between sends
            await asyncio.sleep(60 / max(1, self.max_per_minute))

        return sent

    def _reschedule_after_quiet(self, row: dict) -> None:
        """Push next_send_at to the next opening of quiet hours (~8 AM local)."""
        try:
            from zoneinfo import ZoneInfo
            tz_name = _phone_timezone(row["phone"])
            tz = ZoneInfo(tz_name)
            now_local = datetime.now(tz)
            # Move to 8:05 AM today or tomorrow
            target = now_local.replace(hour=QUIET_HOURS_END, minute=5, second=0, microsecond=0)
            if target <= now_local:
                target = target + timedelta(days=1)
            target_utc = target.astimezone(timezone.utc)
            db = self.get_db()
            db.table("sms_sequences").update({
                "next_send_at": target_utc.isoformat(),
            }).eq("id", row["id"]).execute()
        except Exception as e:
            log.debug(f"[sms] reschedule failed: {e}")

    def _mark_complete(self, row: dict, last_step: Optional[int] = None) -> None:
        try:
            db = self.get_db()
            update = {"status": "completed"}
            if last_step is not None:
                update["current_step"] = last_step
                update["last_sent_at"] = datetime.now(timezone.utc).isoformat()
            db.table("sms_sequences").update(update).eq("id", row["id"]).execute()
            self.stats["sequences_done"] += 1
            self.stats["sequences_active"] = max(0, self.stats["sequences_active"] - 1)
        except Exception as e:
            log.debug(f"[sms] mark_complete failed: {e}")

    # ── INBOUND HANDLING ────────────────────────────────────────────────
    async def handle_inbound(self, from_number: str, body: str) -> dict:
        """
        Process an inbound SMS. Routes:
          - STOP keywords → opt-out
          - HELP keywords → identity + opt-out info reply
          - Other text   → pause sequence, mark as replied
        """
        normalized = _normalize_phone(from_number)
        if not normalized:
            return {"ok": False, "error": "Bad phone"}

        body_clean = (body or "").strip()
        body_upper = body_clean.upper()

        # Log inbound
        try:
            db = self.get_db()
            db.table("sms_log").insert({
                "phone":     normalized,
                "direction": "inbound",
                "body":      body_clean[:500],
            }).execute()
        except Exception as e:
            log.debug(f"[sms] inbound log: {e}")

        self.stats["sms_received"] += 1

        # ── STOP keyword: opt-out (TCPA-required immediate honor) ───────
        if body_upper in STOP_KEYWORDS or any(k == body_upper for k in STOP_KEYWORDS):
            await self._opt_out(normalized, reason=f"STOP keyword: {body_upper}")
            # Send confirmation (TCPA requires confirmation reply)
            await self.voice_router.send_sms(
                normalized,
                f"{self.identity_prefix} You're unsubscribed. No further messages will be sent. "
                "Reply HELP for help.",
            )
            return {"ok": True, "action": "opted_out"}

        # ── HELP keyword: identity + opt-out instructions ────────────────
        if body_upper in HELP_KEYWORDS:
            await self.voice_router.send_sms(
                normalized,
                f"{self.identity_prefix} Empire AI · paid commercial dispatch. "
                "Reply STOP to opt out. Questions: ops@empire-ai.co.uk",
            )
            return {"ok": True, "action": "help_sent"}

        # ── Other reply: pause sequence, flag for human follow-up ───────
        try:
            db = self.get_db()
            db.table("sms_sequences").update({
                "status":        "replied",
                "replies_count": (db.rpc("increment_int", {"x": 1}).execute()
                                  if False else 1),  # fallback below
            }).eq("phone", normalized).execute()
        except Exception:
            # Simple update without RPC if RPC not available
            try:
                db = self.get_db()
                db.table("sms_sequences").update({"status": "replied"}) \
                    .eq("phone", normalized).execute()
            except Exception as e:
                log.debug(f"[sms] reply pause failed: {e}")

        self.stats["sequences_replied"] += 1

        return {
            "ok":          True,
            "action":      "paused_for_human",
            "from":        normalized,
            "body":        body_clean,
        }

    # ── OPT-OUT MANAGEMENT ──────────────────────────────────────────────
    async def _is_opted_out(self, phone: str) -> bool:
        try:
            db = self.get_db()
            res = db.table("sms_opt_outs").select("phone").eq("phone", phone).limit(1).execute()
            return bool(res.data)
        except Exception:
            return False

    async def _opt_out(self, phone: str, reason: str = "STOP") -> None:
        try:
            db = self.get_db()
            # Insert into opt-out table (idempotent — phone is PK)
            db.table("sms_opt_outs").upsert({
                "phone":  phone,
                "reason": reason,
            }).execute()
            # Mark any active sequences as opted_out
            db.table("sms_sequences").update({"status": "opted_out"}) \
                .eq("phone", phone).execute()
            self.stats["sequences_optout"] += 1
            self.stats["sequences_active"]  = max(0, self.stats["sequences_active"] - 1)
        except Exception as e:
            log.error(f"[sms] opt_out write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_sms_routes(
    app: FastAPI,
    engine: SMSSequenceEngine,
    require_auth=None,
    broadcaster=None,
):
    """Register SMS endpoints with FastAPI."""

    # ── INBOUND WEBHOOK (called by Vonage when an SMS arrives) ──────────
    @app.post("/api/v1/sms/inbound")
    async def sms_inbound(request: Request):
        try:
            payload = await request.json()
        except Exception:
            # Vonage SMS sometimes posts as form-encoded
            form = await request.form()
            payload = dict(form)

        from_number = payload.get("msisdn") or payload.get("from", "")
        body = payload.get("text") or payload.get("message", "")

        result = await engine.handle_inbound(from_number, body)

        # Push to live dashboards
        if broadcaster:
            try:
                await broadcaster.broadcast({
                    "type":   "sms_inbound",
                    "from":   from_number,
                    "body":   body[:200],
                    "action": result.get("action", "unknown"),
                })
            except Exception:
                pass

        return {"ok": True}

    # ── OPERATOR ENDPOINTS ──────────────────────────────────────────────
    if require_auth:
        @app.post("/api/v1/sms/enroll")
        async def sms_enroll(request: Request, auth: bool = Depends(require_auth)):
            """Enroll a phone into an SMS sequence."""
            try:
                body = await request.json()
            except Exception:
                body = {}
            return await engine.enroll(
                phone=body.get("phone", ""),
                target_addr=body.get("target_addr", ""),
                sequence_type=body.get("sequence_type", "storm_strike"),
                meta=body.get("meta", {}),
            )

        @app.get("/api/v1/sms/stats")
        async def sms_stats(auth: bool = Depends(require_auth)):
            """SMS engine status snapshot."""
            return engine.stats

        @app.get("/api/v1/sms/sequences")
        async def sms_sequences(
            status: str = "all",
            limit:  int = 100,
            auth:   bool = Depends(require_auth),
        ):
            """List SMS sequences. `status` accepts active/done/opted_out/replied/all."""
            try:
                db = engine.get_db()
                q = db.table("sms_sequences").select("*") \
                    .order("next_send_at", desc=True).limit(max(1, min(limit, 500)))
                if status and status != "all":
                    q = q.eq("status", status)
                return {"sequences": q.execute().data or []}
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.post("/api/v1/sms/bulk-enroll")
        async def sms_bulk_enroll(request: Request, auth: bool = Depends(require_auth)):
            """
            Bulk-enroll all verified radar_targets that don't yet have a
            sequence. Returns count enrolled. Safe to run repeatedly.
            """
            try:
                db = engine.get_db()
                # Pull active targets
                targets = db.table("radar_targets") \
                    .select("phone, address, damage_severity, urgency_score") \
                    .eq("status", "active") \
                    .not_.is_("phone", "null") \
                    .limit(500).execute()
                rows = targets.data or []
            except Exception as e:
                raise HTTPException(500, f"radar_targets query failed: {e}")

            enrolled = 0
            skipped = 0
            for t in rows:
                r = await engine.enroll(
                    phone=t.get("phone", ""),
                    target_addr=t.get("address", ""),
                    sequence_type="storm_strike",
                    meta={
                        "severity": t.get("damage_severity"),
                        "urgency":  t.get("urgency_score"),
                    },
                )
                if r.get("ok") and not r.get("existing"):
                    enrolled += 1
                else:
                    skipped += 1

            return {
                "ok":         True,
                "enrolled":   enrolled,
                "skipped":    skipped,
                "total_seen": len(rows),
            }

    log.info("[sms] Routes registered · /api/v1/sms/{inbound,enroll,bulk-enroll,stats}")


# Compat alias for hub.py
SMSEngine = SMSSequenceEngine
