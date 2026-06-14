"""Add POST /api/contractors/chat endpoint to hub.py after line 389."""
import re

with open("hub.py", "r") as f:
    content = f.read()

# Find the anchor: "register_contractor_routes(app)" then the next line
# We'll insert after the comment + registration block

anchor = "# ── Public contractor landing page (chat widget stub) ──────────────────\nregister_contractor_routes(app)\n\n"

chat_endpoint = '''# ── Public contractor landing page (chat widget stub) ──────────────────
register_contractor_routes(app)

# ── Chat widget endpoint — contractor-recruit Q&A via synthetic brain ─────
# POST /api/contractors/chat
# Accepts {session_id, message}, rate-limited to 30/hr per session.
# Calls synthetic_brain at localhost:8005/ask for LLM responses.
import time as _chat_time

_CHAT_RATE_LIMIT: dict = {}  # session_id -> [timestamps]
_CHAT_MAX_PER_WINDOW = 30
_CHAT_WINDOW_SEC = 3600

_CHAT_SYSTEM_PROMPT = (
    "You are Empire AI's contractor-recruit assistant. Answer "
    "questions about Empire AI's offer to commercial contractors:\\n"
    "- 3% referral fee on settled insurance claims\\n"
    "- First 2 closed deals are 100% complimentary (no fee)\\n"
    "- No contract, no exclusivity, no call required\\n"
    "- Self-onboard at this page in 90 seconds\\n"
    "- Dispatch via SMS or email when a storm-affected property owner replies YES\\n"
    "- Service areas currently: DFW, Houston, San Antonio, Austin\\n"
    "Be specific, brief (under 80 words), and always end with a "
    "call-to-action (self-onboard, watch the demo, or read the FAQ). "
    "If asked something you don't know, say so and offer to connect "
    "them with a human via email. Never invent numbers or terms."
)


@app.post("/api/contractors/chat")
async def contractors_chat(request: Request):
    """Public endpoint for the contractor-recruit chat widget.

    Accepts {session_id, message}. Rate-limited to 30 messages/hr
    per session_id. Calls synthetic_brain's /ask endpoint for the
    LLM response.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    session_id = (body.get("session_id") or "").strip()
    message = (body.get("message") or "").strip()

    if not session_id:
        return JSONResponse({"ok": False, "error": "missing_session_id"}, status_code=400)
    if not message:
        return JSONResponse({"ok": False, "error": "missing_message"}, status_code=400)
    if len(message) > 2000:
        return JSONResponse({"ok": False, "error": "message_too_long"}, status_code=400)

    # ── Rate limiting ───────────────────────────────────────────────────
    now = _chat_time.time()
    timestamps = _CHAT_RATE_LIMIT.get(session_id, [])
    timestamps = [t for t in timestamps if now - t < _CHAT_WINDOW_SEC]

    if len(timestamps) >= _CHAT_MAX_PER_WINDOW:
        _CHAT_RATE_LIMIT[session_id] = timestamps
        return JSONResponse({
            "ok": False, "error": "rate_limited",
            "count_remaining": 0,
            "reply": "You've asked a lot of questions \\u2014 feel free to self-onboard "
                     "and we'll email you a full breakdown.",
        }, status_code=429)

    timestamps.append(now)
    _CHAT_RATE_LIMIT[session_id] = timestamps
    remaining = _CHAT_MAX_PER_WINDOW - len(timestamps)

    # Periodic cleanup: sweep stale entries every 100 requests
    if len(_CHAT_RATE_LIMIT) > 500:
        cutoff = now - _CHAT_WINDOW_SEC
        _CHAT_RATE_LIMIT.clear()
        _CHAT_RATE_LIMIT[session_id] = timestamps
        log.debug("[contractors_chat] rate-limit cache swept")

    # ── Call synthetic brain ────────────────────────────────────────────
    try:
        async with _httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "http://localhost:8005/ask",
                json={"system": _CHAT_SYSTEM_PROMPT, "prompt": message},
            )
            if r.status_code < 500:
                data = r.json()
                reply = data.get("response", "")
            else:
                reply = ""
    except Exception as e:
        log.warning(f"[contractors_chat] brain call failed: {e}")
        reply = ""

    if not reply:
        return JSONResponse({
            "ok": False,
            "error": "brain_unavailable",
            "count_remaining": remaining,
            "reply": "I'm having a moment \\u2014 try again in 30 seconds or self-onboard "
                     "below and we'll get back to you.",
        }, status_code=503)

    return JSONResponse({
        "ok": True,
        "reply": reply,
        "count_remaining": remaining,
    })

'''

# Replace the old section with the new one
if anchor in content:
    content = content.replace(anchor, chat_endpoint, 1)
    with open("hub.py", "w") as f:
        f.write(content)
    print("OK: chat endpoint inserted after register_contractor_routes(app)")
else:
    print("ERROR: anchor not found!")
    # Try to find it differently
    idx = content.find("register_contractor_routes(app)")
    if idx >= 0:
        print(f"Found at position {idx}")
        print(repr(content[idx-10:idx+40]))
    else:
        print("Not found at all")
