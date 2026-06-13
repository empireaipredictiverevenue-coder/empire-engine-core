"""
EMPIRE V49 · BRIDGE VIEW (Phase 8 · Track 3)
===============================================
Full-screen voice-first experience. The Bridge is the showpiece — a
single-screen interface where the operator speaks natural language
commands and the system executes them.

ARCHITECTURE
────────────
  /bridge (SPA route)        → full-screen iframe or standalone page
      │
  POST /api/bridge/command   → VoiceController.process_command()
  GET  /api/bridge/session   → active session for current operator
  POST /api/bridge/session   → start new session
  PATCH /api/bridge/session  → end session, save transcript
  GET  /api/bridge/history   → recent bridge session history
  GET  /api/bridge/status    → bridge health + active session count

  The SPA uses Web Speech API for recognition and streams text to
  /api/bridge/command. Responses render as inline cards.

SUPABASE SCHEMA
───────────────
  migrations/004_bridge_sessions.sql
    CREATE TABLE bridge_sessions (
      id              uuid PRIMARY KEY,
      created_at      timestamptz,
      ended_at        timestamptz,
      operator_id     uuid,
      duration_sec    int,
      actions_taken   int,
      commands_count  int,
      transcript      jsonb,
      meta            jsonb
    );

INTERACTION MODEL
─────────────────
  1. Operator opens /bridge (or clicks bridge nav item)
  2. SPA starts Web Speech API recognition (continuous mode)
  3. When speech is detected, text is sent to POST /api/bridge/command
  4. Response is rendered as an inline transcript card
  5. Destructive actions show confirmation card
  6. Esc closes the bridge view, returns to normal SPA
"""

import os
import uuid
import logging
import json
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse

log = logging.getLogger("empire.bridge")


# ─────────────────────────────────────────────────────────────────────────────
# BRIDGE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class BridgeEngine:
    """
    Manages bridge sessions and routes natural-language commands to
    the VoiceController for execution.
    """

    def __init__(
        self,
        *,
        get_db: Callable,
        voice_controller=None,
        broadcaster=None,
    ):
        self.get_db = get_db
        self.voice_controller = voice_controller
        self.broadcaster = broadcaster
        self.stats = {
            "sessions_started": 0,
            "commands_processed": 0,
            "errors": 0,
        }

    # ── SESSION MANAGEMENT ──────────────────────────────────────────────
    async def get_active_session(self, operator_id: str = "") -> Optional[dict]:
        """Return the active bridge session for this operator (if any)."""
        try:
            db = self.get_db()
            q = db.table("bridge_sessions").select("*") \
                .is_("ended_at", "null") \
                .order("created_at", desc=True).limit(1)
            if operator_id:
                q = q.eq("operator_id", operator_id)
            res = q.execute()
            return res.data[0] if res.data else None
        except Exception as e:
            log.debug(f"[bridge] get_active_session: {e}")
            return None

    async def start_session(self, operator_id: str = "") -> dict:
        """Start a new bridge session. Returns the session dict."""
        session_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            db = self.get_db()
            row = {
                "id": session_id,
                "created_at": now_iso,
                "operator_id": operator_id if operator_id else None,
                "duration_sec": 0,
                "actions_taken": 0,
                "commands_count": 0,
                "transcript": [],
                "meta": {"user_agent": "", "referrer": ""},
            }
            db.table("bridge_sessions").insert(row).execute()
            self.stats["sessions_started"] += 1
            return row
        except Exception as e:
            log.error(f"[bridge] start_session failed: {e}")
            self.stats["errors"] += 1
            raise HTTPException(500, f"Failed to start session: {e}")

    async def end_session(self, session_id: str) -> dict:
        """End a bridge session. Calculates duration and saves transcript."""
        try:
            db = self.get_db()
            res = db.table("bridge_sessions").select("*") \
                .eq("id", session_id).limit(1).execute()
            if not res.data:
                raise HTTPException(404, "Session not found")
            session = res.data[0]
            created = session.get("created_at")
            duration_sec = 0
            if created:
                try:
                    if isinstance(created, str):
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    else:
                        created_dt = created
                    duration_sec = int((datetime.now(timezone.utc) - created_dt).total_seconds())
                except Exception:
                    pass

            db.table("bridge_sessions").update({
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "duration_sec": duration_sec,
            }).eq("id", session_id).execute()

            # Broadcast session end
            if self.broadcaster:
                try:
                    await self.broadcaster.broadcast({
                        "type": "bridge_session_end",
                        "session_id": session_id,
                        "duration_sec": duration_sec,
                    })
                except Exception:
                    pass

            return {"ok": True, "session_id": session_id, "duration_sec": duration_sec}
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[bridge] end_session failed: {e}")
            self.stats["errors"] += 1
            raise HTTPException(500, str(e))

    async def append_transcript(
        self,
        session_id: str,
        role: str,
        text: str,
    ) -> dict:
        """Append a transcript entry to the session log."""
        try:
            db = self.get_db()
            res = db.table("bridge_sessions").select("transcript") \
                .eq("id", session_id).limit(1).execute()
            if not res.data:
                return {"ok": False, "error": "session not found"}

            transcript = list(res.data[0].get("transcript") or [])
            transcript.append({
                "role": role,
                "text": text[:2000],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            db.table("bridge_sessions").update({
                "transcript": transcript,
                "commands_count": len(transcript),
            }).eq("id", session_id).execute()
            return {"ok": True}
        except Exception as e:
            log.debug(f"[bridge] append_transcript: {e}")
            return {"ok": False, "error": str(e)}

    async def process_command(
        self,
        session_id: str,
        command: str,
    ) -> dict:
        """
        Process a natural-language command through the VoiceController.
        Logs to the session transcript.
        """
        self.stats["commands_processed"] += 1

        # Log user command to transcript
        await self.append_transcript(session_id, "user", command)

        # Process via VoiceController
        response = {"text": "Command received but no voice controller wired.", "action": "noop"}
        if self.voice_controller:
            try:
                response = await self.voice_controller.process_command(command, session_id)
            except Exception as e:
                log.error(f"[bridge] command error: {e}")
                self.stats["errors"] += 1
                response = {"text": f"Error: {e}", "action": "error"}

        # Log response to transcript
        await self.append_transcript(session_id, "assistant", response.get("text", ""))

        # Update actions taken count
        if response.get("action") not in ("error", "unknown", "help", "noop"):
            try:
                db = self.get_db()
                # Read current transcript length and use that as actions_taken
                s_res = db.table("bridge_sessions").select("actions_taken").eq("id", session_id).limit(1).execute()
                s_cur = (s_res.data[0]["actions_taken"] if s_res.data else 0) or 0
                db.table("bridge_sessions").update({
                    "actions_taken": s_cur + 1
                }).eq("id", session_id).execute()
            except Exception:
                pass

        # Broadcast to live dashboards
        if self.broadcaster and response.get("action") != "noop":
            try:
                await self.broadcaster.broadcast({
                    "type": "bridge_command",
                    "session_id": session_id,
                    "command": command[:120],
                    "action": response.get("action"),
                    "text": response.get("text", "")[:200],
                })
            except Exception:
                pass

        return response

    async def get_history(self, limit: int = 20) -> list:
        """Return recent bridge sessions."""
        try:
            db = self.get_db()
            res = db.table("bridge_sessions").select("*") \
                .order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            log.warning(f"[bridge] history fetch failed: {e}")
            return []

    async def status(self) -> dict:
        """Bridge health snapshot."""
        active_count = 0
        try:
            db = self.get_db()
            res = db.table("bridge_sessions").select("id", count="exact") \
                .is_("ended_at", "null").limit(1).execute()
            active_count = getattr(res, "count", 0) or 0
        except Exception:
            pass

        return {
            "enabled": True,
            "active_sessions": active_count,
            "total_sessions": self.stats["sessions_started"],
            "commands_processed": self.stats["commands_processed"],
            "errors": self.stats["errors"],
            "voice_controller_wired": self.voice_controller is not None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ROUTES
# ─────────────────────────────────────────────────────────────────────────────
def register_bridge_routes(
    app: FastAPI,
    engine: BridgeEngine,
    *,
    require_auth: Callable,
    public_base_url: str = "",
):
    """Wire bridge API routes."""

    # ── BRIDGE STATUS ──────────────────────────────────────────────────
    @app.get("/api/bridge/status")
    async def bridge_status(auth: bool = Depends(require_auth)):
        return await engine.status()

    # ── SESSION MANAGEMENT ─────────────────────────────────────────────
    @app.get("/api/bridge/session")
    async def bridge_get_session(auth: bool = Depends(require_auth)):
        """Get the active session, or create one."""
        session = await engine.get_active_session()
        if not session:
            session = await engine.start_session()
        return session

    @app.post("/api/bridge/session")
    async def bridge_start_session(request: Request, auth: bool = Depends(require_auth)):
        """Start a new bridge session."""
        operator_id = ""
        try:
            body = await request.json()
            operator_id = body.get("operator_id", "")
        except Exception:
            pass
        return await engine.start_session(operator_id=operator_id)

    @app.patch("/api/bridge/session")
    async def bridge_end_session(request: Request, auth: bool = Depends(require_auth)):
        """End the current bridge session."""
        try:
            body = await request.json()
            session_id = body.get("session_id", "")
        except Exception:
            raise HTTPException(400, "session_id required")
        return await engine.end_session(session_id)

    # ── COMMAND PROCESSING ─────────────────────────────────────────────
    @app.post("/api/bridge/command")
    async def bridge_command(request: Request, auth: bool = Depends(require_auth)):
        """
        Process a natural-language voice command.

        Body: {command: "call +12145551234", session_id: "uuid"}
        Returns: {text, action, data?}
        """
        try:
            body = await request.json()
            command = body.get("command", "").strip()
            session_id = body.get("session_id", "")
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        if not command:
            raise HTTPException(400, "command is required")
        if not session_id:
            session = await engine.get_active_session()
            if not session:
                session = await engine.start_session()
            session_id = session.get("id", "")

        result = await engine.process_command(session_id, command)
        return result

    # ── HISTORY ─────────────────────────────────────────────────────────
    @app.get("/api/bridge/history")
    async def bridge_history(
        limit: int = Query(20, ge=1, le=100),
        auth: bool = Depends(require_auth),
    ):
        sessions = await engine.get_history(limit=limit)
        return {"sessions": sessions}

    # ── TRANSCRIPT (for a specific session) ─────────────────────────────
    @app.get("/api/bridge/transcript/{session_id}")
    async def bridge_transcript(
        session_id: str,
        auth: bool = Depends(require_auth),
    ):
        try:
            db = engine.get_db()
            res = db.table("bridge_sessions").select("transcript, created_at, duration_sec") \
                .eq("id", session_id).limit(1).execute()
            if not res.data:
                raise HTTPException(404, "Session not found")
            return res.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    log.info("[bridge] Routes registered · /api/bridge/{status,session,command,history,transcript}")
