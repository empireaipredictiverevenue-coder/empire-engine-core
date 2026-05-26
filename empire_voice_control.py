"""
EMPIRE V49 · VOICE CONTROL (server side)
=========================================
Receives transcribed text from browser SpeechRecognition,
routes through the existing SovereignConsole.
"""
import logging
from typing import Callable

log = logging.getLogger("empire.voice.control")


def register_voice_control_routes(app, console, require_auth):
    from fastapi import Depends, Body

    @app.post("/api/v1/voice/parse")
    async def voice_parse(payload: dict = Body(...), auth: bool = Depends(require_auth)):
        text = (payload.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "empty"}
        try:
            parsed = await console.parse(text)
            return {"ok": True, "text": text, "parsed": parsed}
        except Exception as e:
            log.error(f"[voice] parse failed: {e}")
            return {"ok": False, "error": str(e)}

    log.info("[voice.control] Routes registered - /api/v1/voice/parse")
