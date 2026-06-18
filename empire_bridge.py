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
    """Wire bridge API routes and the /bridge command dashboard page."""

    # ── BRIDGE HTML PAGE ────────────────────────────────────────────────
    @app.get("/bridge", response_class=HTMLResponse)
    async def bridge_html_page(auth: bool = Depends(require_auth)):
        """The JARVIS Command Bridge dashboard — full-screen voice-first command center."""
        return HTMLResponse(bridge_page())

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


# ═══════════════════════════════════════════════════════════════════════════
# JARVIS COMMAND BRIDGE DASHBOARD — The full-screen voice-activated command
# center. A rich, always-on interface where operators speak natural language
# commands and the system executes them in real-time. Think Iron Man's JARVIS.
# ═══════════════════════════════════════════════════════════════════════════

def bridge_page() -> str:
    """Return the Command Bridge dashboard HTML — JARVIS interface."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Empire AI · Command Bridge</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg-primary: #030812;
  --bg-surface: #0B1729;
  --bg-elevated: #11243F;
  --border: rgba(122,140,163,0.15);
  --border-active: rgba(68,229,184,0.35);
  --text-primary: #F0F4F8;
  --text-secondary: #94A3B8;
  --text-muted: #4A5A72;
  --accent: #44E5B8;
  --accent-dim: rgba(68,229,184,0.12);
  --amber: #F59E0B;
  --red: #F43F5E;
  --blue: #5AC8FA;
  --font-mono: 'SF Mono','Fira Code','JetBrains Mono',monospace;
  --font-display: 'Geist','Inter',system-ui,sans-serif;
}
html, body { height: 100%; background: var(--bg-primary); color: var(--text-primary); font-family: var(--font-display); overflow: hidden; }

/* ── LAYOUT ──────────────────────────────────────────────────── */
.bridge-wrap {
  display: flex; flex-direction: column;
  height: 100vh; max-width: 1400px; margin: 0 auto;
}

/* ── STATUS BAR ──────────────────────────────────────────────── */
.bridge-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
}
.bridge-logo {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.28em; text-transform: uppercase;
  color: var(--accent);
  display: flex; align-items: center; gap: 10px;
}
.bridge-logo .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent);
  animation: bridge-pulse 1.6s ease-in-out infinite;
}
@keyframes bridge-pulse {
  0%,100% { opacity:1; box-shadow:0 0 0 0 rgba(68,229,184,0.4); }
  50% { opacity:.6; box-shadow:0 0 0 6px rgba(68,229,184,0); }
}
.bridge-topbar-right {
  display: flex; align-items: center; gap: 16px;
  font-family: var(--font-mono); font-size: 9px;
  color: var(--text-muted); letter-spacing: 0.12em;
}
.bridge-topbar-right .status-item {
  display: flex; align-items: center; gap: 6px;
}
.bridge-topbar-right .status-dot {
  width: 5px; height: 5px; border-radius: 50%;
}
.bridge-topbar-right .status-dot.green { background: var(--accent); }
.bridge-topbar-right .status-dot.amber { background: var(--amber); }

/* ── QUICK ACTIONS ───────────────────────────────────────────── */
.bridge-actions {
  display: flex; gap: 6px; padding: 10px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.bridge-action-btn {
  flex-shrink: 0;
  font-family: var(--font-mono); font-size: 9px;
  letter-spacing: 0.12em; text-transform: uppercase;
  padding: 6px 14px;
  background: var(--accent-dim);
  border: 1px solid var(--border-active);
  color: var(--accent);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.bridge-action-btn:hover {
  background: var(--accent);
  color: var(--bg-primary);
  transform: translateY(-1px);
}
.bridge-action-btn.amber {
  border-color: rgba(245,158,11,0.3);
  background: rgba(245,158,11,0.08);
  color: var(--amber);
}
.bridge-action-btn.amber:hover {
  background: var(--amber);
  color: var(--bg-primary);
}
.bridge-action-btn.blue {
  border-color: rgba(90,200,250,0.3);
  background: rgba(90,200,250,0.08);
  color: var(--blue);
}
.bridge-action-btn.blue:hover {
  background: var(--blue);
  color: var(--bg-primary);
}

/* ── MAIN CONTENT ────────────────────────────────────────────── */
.bridge-main {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; position: relative;
}

/* ── TRANSCRIPT THREAD ───────────────────────────────────────── */
.bridge-thread {
  flex: 1; overflow-y: auto; padding: 20px 24px 80px;
  scroll-behavior: smooth;
}
.bridge-thread::-webkit-scrollbar { width: 4px; }
.bridge-thread::-webkit-scrollbar-track { background: transparent; }
.bridge-thread::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.bridge-empty-state {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 100%; text-align: center;
  color: var(--text-muted);
}
.bridge-empty-state .jarvis-icon {
  font-size: 56px; margin-bottom: 20px;
  opacity: 0.6;
}
.bridge-empty-state h2 {
  font-weight: 200; font-size: 28px;
  letter-spacing: -0.03em;
  margin-bottom: 8px;
  color: var(--text-primary);
}
.bridge-empty-state h2 em { font-style: italic; color: var(--accent); font-weight: 500; }
.bridge-empty-state p {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--text-muted); max-width: 480px;
  line-height: 1.8;
}

/* ── MESSAGE CARDS ───────────────────────────────────────────── */
.msg { margin-bottom: 16px; animation: msg-in 0.2s ease-out both; }
@keyframes msg-in { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }

.msg-user {
  display: flex; gap: 12px; align-items: flex-start;
}
.msg-user .avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  font-size: 12px;
}
.msg-user .bubble {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px 16px;
  font-family: var(--font-mono); font-size: 12px;
  color: var(--text-primary);
  line-height: 1.6;
  max-width: 75%;
}

.msg-assistant {
  display: flex; gap: 12px; align-items: flex-start;
}
.msg-assistant .avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--accent-dim);
  border: 1px solid var(--border-active);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  font-size: 14px;
}
.msg-assistant .bubble {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-left: 2px solid var(--accent);
  border-radius: 4px;
  padding: 14px 18px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  max-width: 75%;
}
.msg-assistant .bubble strong {
  color: var(--text-primary);
  font-weight: 500;
}

.bubble .badge {
  display: inline-flex; align-items: center;
  font-family: var(--font-mono); font-size: 8px;
  letter-spacing: 0.14em; text-transform: uppercase;
  padding: 2px 8px; border-radius: 2px;
  margin-right: 8px;
}
.badge-green { background: var(--accent-dim); color: var(--accent); border: 1px solid var(--border-active); }
.badge-amber { background: rgba(245,158,11,0.1); color: var(--amber); border: 1px solid rgba(245,158,11,0.25); }
.badge-red   { background: rgba(244,63,94,0.1); color: var(--red); border: 1px solid rgba(244,63,94,0.25); }
.badge-blue  { background: rgba(90,200,250,0.1); color: var(--blue); border: 1px solid rgba(90,200,250,0.25); }

.bubble .page-link {
  display: inline-block; margin-top: 8px;
  font-family: var(--font-mono); font-size: 11px;
  color: var(--accent); text-decoration: none;
  padding: 4px 12px;
  background: var(--accent-dim);
  border: 1px solid var(--border-active);
  transition: all 0.15s;
}
.bubble .page-link:hover {
  background: var(--accent);
  color: var(--bg-primary);
}

/* Stats grid inside bubble */
.bubble-stats {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 8px; margin-top: 10px;
}
.bubble-stat {
  background: rgba(0,0,0,0.2);
  padding: 8px 10px; border-radius: 3px;
  border-left: 2px solid var(--accent);
}
.bubble-stat-label {
  font-family: var(--font-mono); font-size: 8px;
  color: var(--text-muted); letter-spacing: 0.14em;
  text-transform: uppercase; margin-bottom: 2px;
}
.bubble-stat-value {
  font-family: var(--font-mono); font-size: 16px;
  color: var(--text-primary); font-weight: 500;
}
.bubble-stat-value.accent { color: var(--accent); }
.bubble-stat-value.amber { color: var(--amber); }
.bubble-stat-value.red { color: var(--red); }

/* ── INPUT AREA ──────────────────────────────────────────────── */
.bridge-input-area {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 16px 24px 20px;
  background: linear-gradient(0deg, var(--bg-primary) 60%, transparent);
}
.bridge-input-row {
  display: flex; align-items: center; gap: 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 4px 4px 18px;
  transition: border-color 0.2s;
}
.bridge-input-row:focus-within {
  border-color: var(--border-active);
  box-shadow: 0 0 0 1px var(--border-active);
}
.bridge-input {
  flex: 1;
  background: transparent; border: none; outline: none;
  font-family: var(--font-mono); font-size: 13px;
  color: var(--text-primary);
  padding: 10px 0;
}
.bridge-input::placeholder { color: var(--text-muted); }

.bridge-mic-btn {
  width: 36px; height: 36px; display: flex;
  align-items: center; justify-content: center;
  background: var(--accent-dim);
  border: 1px solid var(--border-active);
  border-radius: 4px;
  cursor: pointer;
  color: var(--accent);
  font-size: 16px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.bridge-mic-btn:hover { background: var(--accent); color: var(--bg-primary); }
.bridge-mic-btn.listening {
  background: rgba(90,200,250,0.15);
  border-color: rgba(90,200,250,0.4);
  color: var(--blue);
  animation: bridge-pulse 1.2s ease-in-out infinite;
}

.bridge-send-btn {
  padding: 10px 20px;
  background: var(--accent);
  border: none; border-radius: 4px;
  cursor: pointer;
  font-family: var(--font-mono); font-size: 10px;
  font-weight: 600; letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--bg-primary);
  transition: all 0.15s;
  flex-shrink: 0;
}
.bridge-send-btn:hover { background: #5BEFC8; transform: translateY(-1px); }
.bridge-send-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

/* ── LIST IN BUBBLE ──────────────────────────────────────────── */
.bubble-table {
  width: 100%; border-collapse: collapse;
  margin-top: 8px; font-family: var(--font-mono); font-size: 10px;
}
.bubble-table th {
  text-align: left; color: var(--text-muted);
  padding: 4px 8px; border-bottom: 1px solid var(--border);
  font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase;
  font-size: 8px;
}
.bubble-table td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(122,140,163,0.06);
  color: var(--text-secondary);
}
.bubble-table td:first-child { color: var(--text-primary); font-weight: 500; }
.bubble-table tr:last-child td { border-bottom: none; }

/* ── LISTENING INDICATOR ─────────────────────────────────────── */
.listening-bar {
  display: none; align-items: center; gap: 8px;
  padding: 8px 0 4px;
  font-family: var(--font-mono); font-size: 9px;
  color: var(--blue); letter-spacing: 0.12em;
}
.listening-bar.visible { display: flex; }
.listening-bar .wave {
  display: flex; gap: 3px; align-items: center;
}
.listening-bar .wave span {
  width: 3px; height: 12px;
  background: var(--blue); border-radius: 1px;
  animation: wave 0.8s ease-in-out infinite alternate;
}
.listening-bar .wave span:nth-child(2) { animation-delay: 0.15s; height: 18px; }
.listening-bar .wave span:nth-child(3) { animation-delay: 0.3s; height: 14px; }
.listening-bar .wave span:nth-child(4) { animation-delay: 0.45s; height: 20px; }
.listening-bar .wave span:nth-child(5) { animation-delay: 0.6s; height: 10px; }
@keyframes wave {
  from { height: 8px; opacity: 0.5; }
  to   { height: 20px; opacity: 1; }
}

/* ── TYPING INDICATOR ────────────────────────────────────────── */
.typing-indicator {
  display: none; align-items: center; gap: 8px;
  padding: 8px 18px;
  font-family: var(--font-mono); font-size: 9px;
  color: var(--text-muted); letter-spacing: 0.06em;
}
.typing-indicator.visible { display: flex; }
.typing-dots span {
  display: inline-block; width: 4px; height: 4px;
  border-radius: 50%; background: var(--text-muted);
  margin: 0 2px; animation: typing 1.2s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing {
  0%,80%,100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ── RESPONSIVE ──────────────────────────────────────────────── */
@media (max-width: 720px) {
  .msg-user .bubble, .msg-assistant .bubble { max-width: 88%; font-size: 12px; }
  .bridge-actions { padding: 8px 14px; }
  .bridge-thread { padding: 14px 14px 80px; }
  .bridge-input-area { padding: 12px 14px 16px; }
}
</style>
</head>
<body>
<div class="bridge-wrap">
  <!-- Top Bar -->
  <div class="bridge-topbar">
    <div class="bridge-logo">
      <span class="dot"></span>
      COMMAND BRIDGE · JARVIS
    </div>
    <div class="bridge-topbar-right">
      <span class="status-item">
        <span class="status-dot green" id="bridge-status-indicator"></span>
        <span id="bridge-status-text">ONLINE</span>
      </span>
      <span id="bridge-session-info">0 commands · 0 errors</span>
    </div>
  </div>

  <!-- Quick Actions -->
  <div class="bridge-actions" id="bridge-quick-actions">
    <button class="bridge-action-btn" data-cmd="build a storm page for Dallas TX" onclick="sendQuick(this)">
      🌪️ Dallas Storm Page
    </button>
    <button class="bridge-action-btn amber" data-cmd="show system status" onclick="sendQuick(this)">
      📊 System Status
    </button>
    <button class="bridge-action-btn blue" data-cmd="generate a predictive revenue report" onclick="sendQuick(this)">
      💰 Revenue Report
    </button>
    <button class="bridge-action-btn" data-cmd="list generated pages" onclick="sendQuick(this)">
      📄 Generated Pages
    </button>
    <button class="bridge-action-btn" data-cmd="build a storm page for Houston TX" onclick="sendQuick(this)">
      🌪️ Houston Page
    </button>
    <button class="bridge-action-btn amber" data-cmd="show hot leads in Dallas" onclick="sendQuick(this)">
      🔥 Hot Leads
    </button>
  </div>

  <!-- Main Content -->
  <div class="bridge-main">
    <div class="bridge-thread" id="bridge-thread">
      <div class="bridge-empty-state" id="bridge-empty">
        <div class="jarvis-icon">◈</div>
        <h2>What would you like <em>me</em> to build?</h2>
        <p>
          Speak or type a command. I can generate storm landing pages for any city,
          pull system status, show revenue reports, list generated content, and more.
        </p>
        <div style="margin-top:20px;font-family:var(--font-mono);font-size:9px;color:var(--text-muted);letter-spacing:0.12em;">
          "build a storm page for Dallas" · "show system status" · "generate revenue report"
        </div>
      </div>
      <div id="bridge-messages"></div>
      <div class="typing-indicator" id="typing-indicator">
        <span>JARVIS is thinking</span>
        <span class="typing-dots"><span></span><span></span><span></span></span>
      </div>
    </div>

    <!-- Input -->
    <div class="bridge-input-area">
      <div class="listening-bar" id="listening-bar">
        <span class="wave"><span></span><span></span><span></span><span></span><span></span></span>
        <span>Listening...</span>
      </div>
      <div class="bridge-input-row">
        <input class="bridge-input" id="bridge-input" type="text"
          placeholder="Say something like 'Build a storm page for Dallas'"
          autocomplete="off" spellcheck="false"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendCommand()}">
        <button class="bridge-mic-btn" id="bridge-mic-btn" onclick="toggleMic()" title="Voice input">🎙</button>
        <button class="bridge-send-btn" id="bridge-send-btn" onclick="sendCommand()">Send</button>
      </div>
    </div>
  </div>
</div>

<script>
(function() {
  const TOKEN = localStorage.getItem('hub_token') || '';
  const thread = document.getElementById('bridge-thread');
  const messages = document.getElementById('bridge-messages');
  const empty = document.getElementById('bridge-empty');
  const input = document.getElementById('bridge-input');
  const sendBtn = document.getElementById('bridge-send-btn');
  const micBtn = document.getElementById('bridge-mic-btn');
  const typing = document.getElementById('typing-indicator');
  const listeningBar = document.getElementById('listening-bar');
  let sessionId = null;
  let recognition = null;
  let listening = false;
  let isProcessing = false;

  // ── Initialize session ────────────────────────────────────────────
  async function initSession() {
    try {
      const r = await fetch('/api/bridge/session', {
        headers: { 'Authorization': 'Bearer ' + TOKEN }
      });
      const d = await r.json();
      if (d && d.id) {
        sessionId = d.id;
        updateStats(d);
      }
    } catch (e) {}
  }
  initSession();

  function updateStats(s) {
    const info = document.getElementById('bridge-session-info');
    if (s) info.textContent = (s.commands_count || 0) + ' commands · 0 errors';
  }

  // ── Send command ───────────────────────────────────────────────────
  async function sendCommand() {
    if (isProcessing) return;
    const cmd = input.value.trim();
    if (!cmd) return;
    if (listening) toggleMic();
    await executeCommand(cmd);
    input.value = '';
  }
  window.sendCommand = sendCommand;

  // ── Quick action buttons ───────────────────────────────────────────
  window.sendQuick = function(btn) {
    const cmd = btn.getAttribute('data-cmd');
    if (cmd) executeCommand(cmd);
  };

  async function executeCommand(cmd) {
    isProcessing = true;
    sendBtn.disabled = true;
    empty.style.display = 'none';

    // Add user message
    addUserMessage(cmd);

    // Show typing
    typing.classList.add('visible');
    scrollBottom();

    try {
      // Try the bridge command API first, fall back to console parse
      let response;
      try {
        const r = await fetch('/api/bridge/command', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + TOKEN,
          },
          body: JSON.stringify({
            command: cmd,
            session_id: sessionId || 'new'
          }),
        });
        response = await r.json();
        // If bridge returned error or noop, try the console API
        if (!response || response.action === 'unknown' || response.action === 'noop' || response.action === 'error') {
          throw new Error('bridge_fallback');
        }
      } catch (e) {
        // Fall back to console parse + execute
        const p = await fetch('/api/v1/console/parse', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + TOKEN,
          },
          body: JSON.stringify({ command: cmd }),
        });
        const parsed = await p.json();
        if (parsed.ok && parsed.action) {
          const ex = await fetch('/api/v1/console/execute', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ' + TOKEN,
            },
            body: JSON.stringify({ action: parsed.action, params: parsed.params }),
          });
          response = await ex.json();
          const result = response.result || response;
          response = {
            text: result.message || result.executive_summary || JSON.stringify(result).slice(0,200),
            action: parsed.action,
            data: result,
          };
        } else {
          response = { text: parsed.error || 'Command not understood', action: 'error' };
        }
      }

      typing.classList.remove('visible');

      // Add assistant message
      addAssistantMessage(response);

    } catch (e) {
      typing.classList.remove('visible');
      addAssistantMessage({
        text: 'Error: ' + (e.message || 'Failed to process command'),
        action: 'error',
      });
    }

    isProcessing = false;
    sendBtn.disabled = false;
    scrollBottom();
  }

  function addUserMessage(cmd) {
    const div = document.createElement('div');
    div.className = 'msg msg-user';
    div.innerHTML = '<div class="avatar">👤</div><div class="bubble">' + escapeHtml(cmd) + '</div>';
    messages.appendChild(div);
  }

  function addAssistantMessage(res) {
    const div = document.createElement('div');
    div.className = 'msg msg-assistant';

    let content = '<div class="avatar">◈</div><div class="bubble">';
    
    if (res.action === 'generate_storm_page' && res.data) {
      const d = res.data || res;
      content += '<span class="badge badge-green">✅ Page Generated</span>';
      content += '<strong>' + escapeHtml(d.message || d.title || 'Done') + '</strong>';
      if (d.url) {
        content += '<br><a class="page-link" href="' + d.url + '" target="_blank">' +
          'Open /storm/' + escapeHtml(d.slug || '') + ' →</a>';
      }
    } else if (res.action === 'show_system_status' && res.data) {
      const s = res.data.status || res.data;
      content += '<span class="badge badge-blue">📊 System Status</span>';
      content += '<div class="bubble-stats">';
      if (s.revenue) {
        content += '<div class="bubble-stat">' +
          '<div class="bubble-stat-label">Revenue 24h</div>' +
          '<div class="bubble-stat-value accent">$' + (s.revenue.revenue_24h || 0).toFixed(2) + '</div></div>';
        content += '<div class="bubble-stat">' +
          '<div class="bubble-stat-label">Projected MRR</div>' +
          '<div class="bubble-stat-value accent">$' + (s.revenue.mrr_projected || 0).toFixed(2) + '</div></div>';
        content += '<div class="bubble-stat">' +
          '<div class="bubble-stat-label">Active Buyers</div>' +
          '<div class="bubble-stat-value">' + (s.revenue.active_buyers || 0) + '</div></div>';
        content += '<div class="bubble-stat">' +
          '<div class="bubble-stat-label">Active Lanes</div>' +
          '<div class="bubble-stat-value">' + (s.revenue.lanes_active || 0) + '</div></div>';
      }
      content += '</div>';
      if (s.agents && s.agents.length) {
        content += '<table class="bubble-table"><thead><tr>' +
          '<th>Agent</th><th>Status</th><th>Role</th></tr></thead><tbody>';
        s.agents.slice(0, 15).forEach(function(a) {
          const ok = a.status === 'ACTIVE' || a.status === 'online';
          content += '<tr><td>' + escapeHtml(a.name || '') + '</td>' +
            '<td style="color:' + (ok ? 'var(--accent)' : 'var(--red)') + '">' +
            escapeHtml(a.status || '') + '</td>' +
            '<td>' + escapeHtml(a.role || '') + '</td></tr>';
        });
        content += '</tbody></table>';
      }
    } else if (res.action === 'generate_predictive_report' && res.data) {
      const d = res.data || res;
      content += '<span class="badge badge-amber">💰 Revenue Report</span>';
      content += '<strong>' + escapeHtml(d.executive_summary || 'Revenue Report') + '</strong>';
      if (d.totals) {
        content += '<div class="bubble-stats">';
        content += '<div class="bubble-stat"><div class="bubble-stat-label">24h Revenue</div>' +
          '<div class="bubble-stat-value accent">$' + (d.totals.revenue_24h || 0).toFixed(2) + '</div></div>';
        content += '<div class="bubble-stat"><div class="bubble-stat-label">Projected MRR</div>' +
          '<div class="bubble-stat-value accent">$' + (d.totals.mrr_projected || 0).toFixed(2) + '</div></div>';
        content += '<div class="bubble-stat"><div class="bubble-stat-label">Health</div>' +
          '<div class="bubble-stat-value ' + ((d.health || {}).status === 'healthy' ? 'accent' : 'amber') + '">' +
          ((d.health || {}).status || '—') + '</div></div>';
        content += '</div>';
      }
      if (d.risks && d.risks.length) {
        content += '<div style="margin-top:8px;font-size:10px;color:var(--amber)">⚠ Risks: ' +
          d.risks.join('; ') + '</div>';
      }
      if (d.advice) {
        content += '<div style="margin-top:6px;font-size:10px;color:var(--accent)">→ ' +
          escapeHtml(d.advice) + '</div>';
      }
    } else if (res.action === 'list_generated_pages' && res.data) {
      const d = res.data || res;
      const rows = d.rows || [];
      content += '<span class="badge badge-blue">📄 Generated Pages</span>';
      if (rows.length) {
        content += '<table class="bubble-table"><thead><tr>' +
          '<th>City</th><th>Type</th><th>Status</th><th>URL</th></tr></thead><tbody>';
        rows.forEach(function(r) {
          content += '<tr><td>' + escapeHtml(r.city || '') + '</td>' +
            '<td>' + escapeHtml(r.type || '') + '</td>' +
            '<td>' + escapeHtml(r.status || '') + '</td>' +
            '<td><a href="' + escapeHtml(r.url || '') + '" style="color:var(--accent);text-decoration:none;" target="_blank">open</a></td></tr>';
        });
        content += '</tbody></table>';
      } else {
        content += '<div style="margin-top:8px;font-family:var(--font-mono);font-size:10px;color:var(--text-muted)">No generated pages yet</div>';
      }
    } else if (res.text) {
      // Simple text response
      content += escapeHtml(res.text);
    } else {
      content += escapeHtml(JSON.stringify(res.data || res).slice(0, 300));
    }
    content += '</div>';
    div.innerHTML = content;
    messages.appendChild(div);
    scrollBottom();
  }

  function scrollBottom() {
    setTimeout(function() {
      thread.scrollTop = thread.scrollHeight;
    }, 50);
  }

  // ── Voice Input (Web Speech API) ───────────────────────────────────
  function setupVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = function() {
      listening = true;
      micBtn.classList.add('listening');
      listeningBar.classList.add('visible');
      micBtn.title = 'Listening...';
    };
    recognition.onresult = function(e) {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        text += e.results[i][0].transcript;
      }
      input.value = text;
    };
    recognition.onend = function() {
      listening = false;
      micBtn.classList.remove('listening');
      listeningBar.classList.remove('visible');
      micBtn.title = 'Voice input';
      if (input.value.trim()) {
        executeCommand(input.value.trim());
        input.value = '';
      }
    };
    recognition.onerror = function(e) {
      listening = false;
      micBtn.classList.remove('listening');
      listeningBar.classList.remove('visible');
      micBtn.title = 'Voice input';
    };
  }

  window.toggleMic = function() {
    if (!recognition) setupVoice();
    if (!recognition) return;
    if (listening) {
      recognition.stop();
    } else {
      try { recognition.start(); } catch (e) {}
    }
  };
  setupVoice();

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;');
  }
})();
</script>
</body>
</html>"""
