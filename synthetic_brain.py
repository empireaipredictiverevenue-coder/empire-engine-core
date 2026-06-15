import os
import re
import json
import hmac
import hashlib
import http.client
import subprocess
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Literal, Optional
import numpy as np
import soundfile as sf
from fastapi import Depends, FastAPI, HTTPException, Security, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field, ValidationError
from kokoro_onnx import Kokoro

log = logging.getLogger("synthetic_brain")

# scipy is used for resampling Kokoro's native 24kHz output down to Vonage's
# required 16kHz L16 mono for the `stream` NCCO action. We import lazily
# inside the streaming endpoint so a missing scipy in a minimal env doesn't
# break the file-based video render path.
try:
    from scipy.signal import resample_poly
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False

app = FastAPI(title="Empire_AI_Synthetic_Intelligence_Brain")

# ── API KEY AUTH ──────────────────────────────────────────────────
# All requests must include `X-API-Key: <SYNTHETIC_BRAIN_API_KEY>`.
# The expected value is read from the env var at import time. If the
# env var is unset the dependency raises 500 at request time (intentional
# fail-closed — we never want to run with auth disabled).
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)

def _expected_api_key() -> str:
    key = os.environ.get("SYNTHETIC_BRAIN_API_KEY", "")
    if not key:
        # Fail-closed: refuse to serve if no key is configured
        raise HTTPException(
            status_code=500,
            detail="SYNTHETIC_BRAIN_API_KEY env var is not set — refusing to serve unauthenticated requests",
        )
    return key

async def require_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    expected = _expected_api_key()
    # Constant-time comparison to defeat timing attacks
    if not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=403, detail="Invalid or missing X-API-Key")
    return api_key

# System path configurations
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates" / "videos"
OUTPUT_DIR = BASE_DIR / "builds" / "production_vault"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── KOKORO SINGLETON (cached per process) ─────────────────────────
# Loading the Kokoro model from disk takes ~3-5s, so we cache it at module
# level and reuse across requests. If the model file is missing, _get_kokoro()
# returns None and the caller falls back to raising 500.
_KOKORO: Optional[Kokoro] = None
_KOKORO_LOCK = False  # tiny lock-equivalent for concurrent first-load

def _get_kokoro() -> Kokoro:
    global _KOKORO, _KOKORO_LOCK
    if _KOKORO is None and not _KOKORO_LOCK:
        _KOKORO_LOCK = True
        try:
            _KOKORO = Kokoro(
                str(BASE_DIR / "kokoro-v1.0.onnx"),
                str(BASE_DIR / "voices-v1.0.bin"),
            )
        finally:
            _KOKORO_LOCK = False
    if _KOKORO is None:
        raise RuntimeError("Kokoro model failed to load — check kokoro-v1.0.onnx and voices-v1.0.bin")
    return _KOKORO

# ── STREAMING REGISTRY (queue for live phone calls) ───────────────
# The voice_streaming_agent registers a TTS request here BEFORE placing
# the Vonage call. The synthetic_brain WebSocket handler pops it when
# Vonage connects, synthesizes Kokoro sentence-by-sentence, and streams
# L16 16kHz mono PCM back to Vonage for live playback on the call.
#
# Two backends via the StreamRegistry abstraction:
#   - InMemoryStreamRegistry (default): single-worker, no extra deps
#   - RedisStreamRegistry: multi-worker (uvicorn --workers N) via SETEX
# Pick via env: REDIS_URL=redis://... (auto-selects Redis if set).
# Override: STREAM_REGISTRY_BACKEND=redis|memory.
_STREAM_TTL_SECONDS = 300  # auto-expire unclaimed entries after 5 min
# HMAC secret for signing voice_ids. Reuses API key by default; can be
# overridden via SYNTHETIC_BRAIN_STREAM_SECRET env var.
_STREAM_SECRET = os.environ.get(
    "SYNTHETIC_BRAIN_STREAM_SECRET",
    os.environ.get("SYNTHETIC_BRAIN_API_KEY", ""),
)
# Vonage `stream` action requires this exact audio format:
#   L16 (signed 16-bit little-endian PCM), 16kHz, mono.
STREAM_SAMPLE_RATE = 16000
STREAM_VOICES = Literal["am_michael", "af_sarah"]


# ── STREAM REGISTRY ABSTRACTION (multi-worker safe) ─────────────────
# Same `set / get_and_delete / sweep_expired` API for two backends so the
# call sites don't care which one is active. The `_get_registry()` factory
# picks the backend at first-use based on env (REDIS_URL present -> Redis,
# else in-memory). This lets us run:
#   - dev: single worker, in-memory (default, no extra services)
#   - prod (Hetzner --workers 2): Redis-backed, shared across workers
#   - prod (single worker, many regions): in-memory still fine
import time as _registry_time


class StreamRegistry:
    """Abstract interface for the streaming voice_id -> script queue.

    All backends must support:
      set(voice_id, payload, ttl_seconds) -> None
          Store the payload under voice_id with a TTL. The payload is a
          dict with at minimum {script, voice}. Implementations may add
          metadata (e.g. registered_at for the in-memory backend).
      get_and_delete(voice_id) -> Optional[dict]
          Atomically read + remove the entry. Returns None if missing.
          Vonage's WebSocket connects at most once per voice_id, so a
          GETDEL semantics is correct (no replay possible).
      sweep_expired() -> int
          Drop expired entries; return the count dropped. For Redis,
          this is a no-op (Redis TTL handles expiry automatically).
    """

    def set(self, voice_id: str, payload: dict, ttl_seconds: int) -> None:
        raise NotImplementedError

    def get_and_delete(self, voice_id: str) -> Optional[dict]:
        raise NotImplementedError

    def sweep_expired(self) -> int:
        raise NotImplementedError


class InMemoryStreamRegistry(StreamRegistry):
    """In-process dict — single-worker only. Default fallback.

    Wraps the original per-process voice_id -> payload dict in the
    StreamRegistry interface so the call sites don't care which
    backend is active.
    """
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def set(self, voice_id: str, payload: dict, ttl_seconds: int) -> None:
        self._store[voice_id] = {**payload, "registered_at": _registry_time.time()}

    def get_and_delete(self, voice_id: str) -> Optional[dict]:
        return self._store.pop(voice_id, None)

    def sweep_expired(self) -> int:
        cutoff = _registry_time.time() - _STREAM_TTL_SECONDS
        stale = [vid for vid, entry in self._store.items()
                 if entry.get("registered_at", 0) < cutoff]
        for vid in stale:
            self._store.pop(vid, None)
        return len(stale)


class RedisStreamRegistry(StreamRegistry):
    """Redis-backed registry — works across N uvicorn workers.

    Uses SETEX (atomic set-with-TTL) and GETDEL (atomic read+delete).
    Both are Redis 6.2+ commands; redis-py 5+ supports them.
    Connection pooling is handled by redis.from_url() so a single RedisStreamRegistry
    instance can be shared across all requests in a worker.
    """
    def __init__(self, redis_url: str) -> None:
        import redis  # lazy import — dev envs without redis don't fail at module load
        self._client = redis.from_url(redis_url, decode_responses=True)
        # Probe the connection once at construction so misconfigured REDIS_URL
        # fails fast (at first use) rather than on the first register_stream call.
        self._client.ping()
        self._url = redis_url

    def set(self, voice_id: str, payload: dict, ttl_seconds: int) -> None:
        import json as _json
        self._client.setex(voice_id, ttl_seconds, _json.dumps(payload))

    def get_and_delete(self, voice_id: str) -> Optional[dict]:
        import json as _json
        raw = self._client.getdel(voice_id)
        if raw is None:
            return None
        return _json.loads(raw)

    def sweep_expired(self) -> int:
        # Redis TTL handles expiry automatically; no manual sweep needed.
        return 0


# Module-level registry singleton (lazy-init). The factory picks the
# backend based on env:
#   - STREAM_REGISTRY_BACKEND=redis|memory  (explicit override)
#   - REDIS_URL set  (auto-selects Redis)
#   - else  (in-memory, default)
# Falls back to in-memory if Redis init fails (so a misconfigured REDIS_URL
# doesn't take down the worker).
_streaming_registry_instance: Optional[StreamRegistry] = None


def _get_registry() -> StreamRegistry:
    global _streaming_registry_instance
    if _streaming_registry_instance is None:
        backend = os.environ.get("STREAM_REGISTRY_BACKEND", "").lower().strip()
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if backend == "redis" or (not backend and redis_url):
            try:
                url = redis_url or "redis://127.0.0.1:6379/0"
                _streaming_registry_instance = RedisStreamRegistry(url)
                log.info(f"[stream-registry] using Redis backend at {url}")
            except Exception as e:
                log.warning(
                    f"[stream-registry] Redis init failed ({e}), "
                    f"falling back to in-memory (single-worker only)"
                )
                _streaming_registry_instance = InMemoryStreamRegistry()
        else:
            _streaming_registry_instance = InMemoryStreamRegistry()
            if backend == "memory" or not backend:
                log.info("[stream-registry] using in-memory backend (single-worker only)")
    return _streaming_registry_instance


def _split_sentences(text: str) -> List[str]:
    """Split script on sentence boundaries, dropping empties and whitespace.
    Returns a list of clean sentence strings ready for Kokoro synthesis."""
    if not text:
        return []
    # Split on .!? followed by whitespace or end-of-string. Keep the
    # delimiter with the preceding sentence (so "Hello." stays "Hello.").
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sign_voice_id(voice_id: str) -> str:
    """Return the HMAC-SHA256 signature for a voice_id, used as the auth
    proof on the WebSocket URL. Vonage can't send custom headers, so the
    signature is embedded in the URL itself."""
    return hmac.new(
        _STREAM_SECRET.encode(), voice_id.encode(), hashlib.sha256
    ).hexdigest()[:32]


def _verify_voice_id(voice_id: str, signature: str) -> bool:
    if not _STREAM_SECRET:
        return False
    expected = _sign_voice_id(voice_id)
    return hmac.compare_digest(expected, signature)


def _register_stream(script: str, voice: str, public_base_url: str = "") -> Dict[str, Any]:
    """Create a new streaming request. Returns {voice_id, signature, ws_url}.
    The voice_streaming_agent calls this via the /register_stream endpoint,
    then places the Vonage call with the ws_url as the `stream` NCCO action's
    target. Vonage connects to the WebSocket and we start synthesizing."""
    voice_id = uuid.uuid4().hex
    sig = _sign_voice_id(voice_id)
    if voice not in ("am_michael", "af_sarah"):
        voice = "am_michael"
    # Truncate script to 1000 chars to bound synthesis time
    script = (script or "")[:1000]
    if not script.strip():
        script = "Hello. Thank you for calling Empire AI."

    base = (public_base_url or "").rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://"):]
    else:
        # Local default — caller can override by passing public_base_url
        ws_base = "ws://127.0.0.1:8005"

    ws_path = f"/api/v1/synthetic/stream?voice_id={voice_id}&sig={sig}"
    return {
        "voice_id": voice_id,
        "signature": sig,
        "ws_url": f"{ws_base}{ws_path}",
        "voice": voice,
        "script": script,
    }


def _pop_stream(voice_id: str, signature: str) -> Optional[Dict[str, Any]]:
    """Atomically pop a registered stream after verifying the HMAC signature.
    Returns None if the entry is unknown, expired, or has a bad signature.

    Delegates to the active StreamRegistry backend for the atomic get+delete,
    then enforces the wall-clock TTL on the returned entry as a safety net.
    The Redis backend auto-expires via SETEX, so this check is a no-op there.
    The in-memory backend may hold entries past their TTL between sweeps,
    so this check is what actually catches those stale pops.
    """
    if not _verify_voice_id(voice_id, signature):
        return None
    entry = _get_registry().get_and_delete(voice_id)
    if entry is None:
        return None
    # Wall-clock TTL check: catches in-memory entries that haven't been
    # swept yet. The Redis backend's entries never have `registered_at`
    # (it stores raw payloads), so this branch is a safe no-op for Redis.
    registered_at = entry.get("registered_at")
    if registered_at is not None:
        if _registry_time.time() - registered_at > _STREAM_TTL_SECONDS:
            return None
    return entry


def _sweep_expired_streams() -> int:
    """Background sweeper — drops registry entries older than _STREAM_TTL_SECONDS.
    Called opportunistically from the /register_stream endpoint so we don't
    need a separate asyncio task. For the Redis backend this is a no-op
    (Redis TTL handles expiry automatically).
    Returns the number of entries evicted (0 for Redis)."""
    return _get_registry().sweep_expired()


def _synthesize_sentence(samples: np.ndarray, sample_rate: int) -> bytes:
    """Convert a Kokoro float32 samples array into L16 16kHz mono PCM bytes
    suitable for Vonage's `stream` NCCO action."""
    if sample_rate != STREAM_SAMPLE_RATE:
        if not _HAS_SCIPY:
            raise RuntimeError("scipy required for resampling Kokoro output to 16kHz")
        # resample_poly is faster + higher quality than librosa for this
        from math import gcd
        g = gcd(sample_rate, STREAM_SAMPLE_RATE)
        up = STREAM_SAMPLE_RATE // g
        down = sample_rate // g
        samples = resample_poly(samples, up, down)
    # Convert float32 → int16 (clipping to avoid wrap-around)
    if samples.dtype != np.float32:
        samples = samples.astype(np.float32)
    audio_int16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
    return audio_int16.tobytes()


class AGICommand(BaseModel):
    objective: str # e.g., "Build a high-impact roofing ad for Atlanta. Use +18885551234."


class ChatAskRequest(BaseModel):
    """Request to the synthetic brain's general-purpose Q&A endpoint.
    Used by the contractor-recruit chat widget (chat.js)."""
    system: str = Field(
        "",
        description="System prompt to set the LLM context and persona.",
    )
    prompt: str = Field(
        ..., min_length=1, max_length=4000,
        description="User message to answer.",
    )


class SynthesizeRequest(BaseModel):
    script: str = Field(..., min_length=1, max_length=2000,
                        description="Text to synthesize into speech.")
    voice: STREAM_VOICES = Field("am_michael",
                                  description="Kokoro voice profile (am_michael or af_sarah).")
    speed: float = Field(1.1, ge=0.5, le=2.0,
                          description="Speech speed multiplier.")

# ── STRATEGY MODEL (validation + grammar-constrained sampling) ─────
# This single Pydantic model is the source of truth for BOTH the
# runtime validation (Pydantic) AND the JSON Schema we hand to Ollama
# for grammar-constrained sampling (via `Strategy.model_json_schema()`).
# No risk of schema drift between the two — they're the same object.
# Literal types auto-generate the JSON Schema `enum` constraint, and
# Field() descriptions get passed through to the LLM as semantic context.
class Strategy(BaseModel):
    """Pydantic model for the LLM's strategy output. Validates the
    type-flakiness bug we observed where the LLM returns dicts/None
    instead of strings for string-typed fields. Pydantic's strict
    type coercion + Literal enum types catch this before the render
    pipeline runs, and `model_json_schema()` auto-generates the JSON
    Schema for grammar-constrained Ollama sampling.
    """
    script_copy: str = Field(
        ..., min_length=1, max_length=1000,
        description="Max 3 punchy sentences for the ad voiceover.",
    )
    chosen_template: str = Field(
        ..., min_length=1,
        description="Filename of the video template, must be from the available assets list.",
    )
    target_phone: str = Field(
        ..., min_length=1, max_length=50,
        description="Outbound phone route for the ad (e.g. +18005551234).",
    )
    voice_profile: Literal["am_michael", "af_sarah"] = Field(
        ...,
        description="Kokoro TTS voice profile.",
    )
    text_overlay_color: Literal["yellow", "white", "green"] = Field(
        ...,
        description="ffmpeg drawtext fontcolor.",
    )

class LocalBrainContext:
    @staticmethod
    def inspect_system_environment() -> List[str]:
        """Scans local media assets so the intelligence layer knows what it can use."""
        return [f.name for f in TEMPLATES_DIR.glob("*.mp4")]

    @staticmethod
    def ask_local_llm(
        system_prompt: str,
        user_prompt: str,
        format_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Queries local Qwen/Llama instance through a direct low-overhead
        loopback socket.

        If `format_schema` is provided, it's passed to Ollama as the `format`
        payload so the server does grammar-constrained sampling — the LLM
        physically cannot emit tokens that don't conform to the schema. This
        is much more reliable than a free-form "return JSON" instruction in
        the system prompt.

        When `format_schema` is None, the LLM returns plain text by default
        (no JSON constraint). The response is returned as {"response": text}.
        When a schema is provided, the LLM returns structured JSON matching
        that schema.
        """
        conn = http.client.HTTPConnection("localhost", 11434)
        headers = {"Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
        }
        # Only set format when a schema is provided; otherwise the LLM
        # returns plain text (the default Ollama behavior).
        if format_schema is not None:
            payload["format"] = format_schema

        try:
            conn.request("POST", "/api/chat", json.dumps(payload), headers)
            response = conn.getresponse()
            raw = response.read().decode()
            res_data = json.loads(raw)
            content = res_data["message"]["content"]
            # If a schema was provided, parse content as JSON; otherwise
            # return the plain text response.
            if format_schema is not None:
                return json.loads(content)
            return {"response": content}
        except Exception as e:
            return {"error": f"LLM Connection failed: {str(e)}"}
        finally:
            conn.close()

# -------------------------------------------------------------------------
# SYNTHETIC INTELLIGENCE EXECUTION LOOP
# -------------------------------------------------------------------------
@app.post("/api/v1/synthetic/run")
async def execute_autonomous_media_loop(
    payload: AGICommand,
    api_key: str = Depends(require_api_key),
):
    # Step 1: Brain audits the bare-metal machine assets
    available_templates = LocalBrainContext.inspect_system_environment()

    # Step 2: System Formulates Execution Strategy
    orchestrator_system_rules = (
        "You are the Core Synthetic Brain for Empire AI. You analyze a business objective alongside "
        "available server assets, then output a strict execution strategy plan. "
        "Your response must be standard JSON containing exactly these keys: "
        "script_copy (max 3 punchy sentences), chosen_template (must pick from available assets list), "
        "target_phone, voice_profile ('am_michael' or 'af_sarah'), text_overlay_color ('yellow' or 'white')."
    )

    user_context = f"Objective: {payload.objective} \n Available System Templates: {json.dumps(available_templates)}"

    # Step 2.1: Build strategy with grammar-constrained JSON Schema +
    # Pydantic validation. On any validation failure we retry once with a
    # corrective message appended to the user prompt; if that still fails
    # we fall back to safe defaults. The result is a guaranteed-valid dict.
    def _default_strategy() -> Dict[str, Any]:
        return {
            "script_copy": "Call us today for your property needs.",
            "chosen_template": "fallback.mp4",
            "target_phone": "Contact Us Now",
            "voice_profile": "am_michael",
            "text_overlay_color": "yellow",
        }

    strategy: Dict[str, Any] = _default_strategy()
    last_err: Optional[str] = None
    for attempt in (1, 2):
        attempt_user_ctx = user_context
        if attempt == 2 and last_err:
            # Corrective retry — tell the LLM exactly what went wrong
            attempt_user_ctx = (
                f"{user_context}\n\n"
                f"NOTE: Your previous response failed schema validation: {last_err}\n"
                f"You MUST return ALL 5 required fields with the EXACT correct types. "
                f"Each string field must be a plain string (not a dict, list, or null). "
                f"voice_profile MUST be 'am_michael' or 'af_sarah'. "
                f"text_overlay_color MUST be 'yellow', 'white', or 'green'."
            )
        raw = LocalBrainContext.ask_local_llm(
            orchestrator_system_rules, attempt_user_ctx, format_schema=Strategy.model_json_schema(),
        )
        if "error" in raw:
            last_err = raw["error"]
            continue  # retry once on connection error
        try:
            validated = Strategy.model_validate(raw)
            strategy = validated.model_dump()
            break  # success — stop retrying
        except ValidationError as e:
            last_err = str(e)[:300]
            # loop continues if attempt < 2

    # `strategy` is now guaranteed to be a valid dict (either the validated
    # Pydantic output, or the safe defaults after both attempts failed).
    script = strategy["script_copy"]
    template_filename = strategy["chosen_template"]
    phone = strategy["target_phone"]
    voice = strategy["voice_profile"]
    color = strategy["text_overlay_color"]

    # Handle missing assets dynamically without crashing out
    template_path = TEMPLATES_DIR / template_filename if template_filename else TEMPLATES_DIR / "roofing.mp4"
    if not template_path.exists():
        # System dynamically renders a placeholder background canvas on the fly
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(template_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step 3: Run Audio Synthesis Layer via Kokoro-ONNX
    # Use uuid4 (122 random bits) instead of os.urandom(3).hex (24 bits = 16M
    # possibilities) to eliminate collision risk under load.
    campaign_dir = OUTPUT_DIR / f"synthetic_{uuid.uuid4().hex}"
    campaign_dir.mkdir(parents=True, exist_ok=True)
    audio_path = campaign_dir / "voiceover.wav"

    try:
        kokoro = _get_kokoro()
        samples, sample_rate = kokoro.create(script, voice=voice, speed=1.1, lang="en-us")
        sf.write(str(audio_path), samples, sample_rate)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice synthesis block failure: {str(e)}")

    # Step 4: Run Video Assembly Framework via Native FFmpeg
    output_video_path = campaign_dir / "rendered_output.mp4"

    # Escape single-quotes in the phone string for safe ffmpeg drawtext
    # interpolation. Without this, a phone like `+1'800'555'3344` would
    # break the ffmpeg filter expression (or, worse, inject arbitrary
    # filter directives in the ffmpeg context).
    phone_safe = phone.replace("'", r"'\''")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", str(template_path),
        "-i", str(audio_path),
        "-vf", f"scale=1080:1920,drawtext=fontfile=/usr/share/fonts/truetype/msttcorefonts/Arial.ttf:text='{phone_safe}':fontcolor={color}:fontsize=72:box=1:boxcolor=black@0.7:x=(w-text_w)/2:y=h-350",
        "-c:v", "libx264", "-preset", "veryfast", "-shortest",
        str(output_video_path)
    ]

    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step 5: The Diagnostic Critic Self-Correction Evaluation Layer
    critic_system_rules = (
        "You are the Quality Control System for Empire AI. Review the compiled metrics "
        "and determine if the production generation passed successfully. "
        "Return JSON with: verified (true or false), diagnostic_log (brief statement)."
    )

    audit_payload = f"Generated Script: {script} | File Created: {output_video_path.name} | File Size: {output_video_path.stat().st_size if output_video_path.exists() else 0} bytes"
    audit_result = LocalBrainContext.ask_local_llm(critic_system_rules, audit_payload)

    return {
        "status": "COMPLETED" if audit_result.get("verified") else "REQUIRES_RE-RUN",
        "agent_diagnostics": audit_result.get("diagnostic_log", "No log provided"),
        "meta": {
            "script_executed": script,
            "voice_profile": voice,
            "system_template_used": str(template_path),
            "production_location": str(output_video_path)
        }
    }

# -------------------------------------------------------------------------
# VOICE STREAMING (live phone-call TTS)
# -------------------------------------------------------------------------
# The voice_streaming_agent calls /register_stream to queue a TTS request
# BEFORE placing the Vonage outbound call. The call's NCCO includes a
# `stream` action pointing at /api/v1/synthetic/stream?voice_id=...
# When Vonage answers, it opens a WebSocket to that URL; we synthesize
# the script sentence-by-sentence and push L16 16kHz mono PCM bytes
# back to Vonage for live playback on the call.
#
# Auth: the voice_id is signed with HMAC-SHA256(secret) — the signature
# travels in the URL because Vonage can't send custom WebSocket headers.
# The secret reuses SYNTHETIC_BRAIN_API_KEY by default; can be overridden
# via SYNTHETIC_BRAIN_STREAM_SECRET.
class StreamRegistrationRequest(BaseModel):
    script: str = Field(..., min_length=1, max_length=1000,
                        description="Script to synthesize on the live call.")
    voice: STREAM_VOICES = Field("am_michael",
                                  description="Kokoro TTS voice profile.")
    public_base_url: str = Field("",
                                  description="Optional public https URL of "
                                              "this synthetic_brain (e.g. "
                                              "https://brain.empire-ai.co.uk). "
                                              "Used to build the wss:// URL "
                                              "that Vonage will connect to. "
                                              "Leave blank for local dev.")


class StreamRegistrationResponse(BaseModel):
    voice_id: str
    signature: str
    ws_url: str
    voice: str
    script: str


@app.post("/api/v1/synthetic/register_stream",
           response_model=StreamRegistrationResponse)
async def register_stream(
    payload: StreamRegistrationRequest,
    api_key: str = Depends(require_api_key),
):
    """
    Queue a TTS request for a forthcoming Vonage call. The caller (typically
    bots/voice_streaming_agent.py) places the Vonage call immediately after,
    passing the returned ws_url in a `stream` NCCO action.

    The entry lives in the in-process registry for up to 5 minutes — long
    enough for Vonage to connect after the call is answered. Unclaimed
    entries are auto-expired.
    """
    rec = _register_stream(
        script=payload.script,
        voice=payload.voice,
        public_base_url=payload.public_base_url,
    )
    # Opportunistic TTL sweep — drop any expired entries before adding the
    # new one. Keeps the in-memory registry bounded; a no-op for the
    # Redis backend (TTL handles expiry there).
    _sweep_expired_streams()
    # Store via the active backend. The backend manages the TTL.
    _get_registry().set(
        rec["voice_id"],
        {"script": rec["script"], "voice": rec["voice"]},
        _STREAM_TTL_SECONDS,
    )
    return StreamRegistrationResponse(**rec)


# ── GENERAL-PURPOSE Q&A ─────────────────────────────────────────
# Used by the contractor-recruit chat widget and any caller needing
# a simple LLM response without the full AGI execution loop.
@app.post("/ask", include_in_schema=False)
async def chat_ask(
    payload: ChatAskRequest,
):
    """
    General-purpose Q&A endpoint. Accepts {system, prompt} and returns
    {response}. No API key required — intended for the public
    contractor-recruit chat widget.

    The system prompt sets the LLM persona (e.g. contractor-recruit
    assistant). The prompt is the user's message. The response is a
    plain-text answer.
    """
    result = LocalBrainContext.ask_local_llm(
        payload.system or "You are a helpful assistant.",
        payload.prompt,
    )
    if "error" in result:
        return JSONResponse({"ok": False, "error": result["error"]}, status_code=503)
    # ask_local_llm returns plain text (~{"response": text}) when no
    # format_schema is provided (the default for this endpoint). Extract
    # the response field, or fall back to any known key, or serialize.
    if isinstance(result, dict):
        response = result.get("response") or result.get("answer") or result.get("reply") or json.dumps(result)
    else:
        response = str(result)
    return {"ok": True, "response": response}


# ── STANDALONE AUDIO SYNTHESIS (no video) ─────────────────────────
# The Swarm Gate and voice pipeline use this endpoint for audio-only
# output (e.g., phone call voiceovers, SMS voice notes, audio ads).
# Returns the WAV file path so callers can use it downstream.
@app.post("/api/v1/synthetic/synthesize")
async def synthesize_audio(
    payload: SynthesizeRequest,
    api_key: str = Depends(require_api_key),
):
    """
    Synthesize text to a WAV audio file via Kokoro TTS.

    Returns {status, audio_path, duration_s, voice, sample_rate}.
    The audio file is written to builds/production_vault/synth_<uuid>/voiceover.wav.

    Used by:
      - bots/swarm_worker.py (standalone per-lane audio)
      - empire_swarm_gate.py (GodModeSwarmGate._run_kokoro_audio)
      - Any caller needing audio-only output (phone calls, voice notes)
    """
    script = payload.script
    voice = payload.voice
    speed = payload.speed

    # Write to a unique directory so multiple concurrent requests don't collide
    synth_dir = OUTPUT_DIR / f"synth_{uuid.uuid4().hex}"
    synth_dir.mkdir(parents=True, exist_ok=True)
    audio_path = synth_dir / "voiceover.wav"

    try:
        kokoro = _get_kokoro()
        samples, sample_rate = kokoro.create(script, voice=voice, speed=speed, lang="en-us")
        sf.write(str(audio_path), samples, sample_rate)
        duration_s = len(samples) / sample_rate if sample_rate > 0 else 0.0
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Kokoro synthesis failed: {str(e)}",
        )

    return {
        "status": "OK",
        "audio_path": str(audio_path),
        "duration_s": round(duration_s, 2),
        "voice": voice,
        "sample_rate": sample_rate,
    }


@app.websocket("/api/v1/synthetic/stream")
async def tts_stream(
    websocket: WebSocket,
    voice_id: str,
    sig: str,
):
    """
    WebSocket endpoint that streams Kokoro TTS audio to Vonage for live
    playback on a phone call. Protocol:

      Vonage \u2192 us (text):  {"event": "start", ...}  (after call answers)
      Vonage \u2192 us (text):  {"event": "stop",  ...}  (caller hung up)
      us \u2192 Vonage (binary): L16 16kHz mono PCM chunks (one per sentence)
      us \u2192 Vonage (text):  {"event": "stop"}        (we're done streaming)

    The voice_id + sig URL params authenticate the connection (Vonage
    can't send custom headers on WebSocket upgrade). We pop the entry
    from the registry so it can't be replayed.
    """
    await websocket.accept()
    entry = _pop_stream(voice_id, sig)
    if entry is None:
        await websocket.close(code=4001, reason="unknown or expired voice_id")
        return
    if not _HAS_SCIPY:
        await websocket.close(code=4002, reason="scipy required for streaming")
        return

    script: str = entry["script"]
    voice: str = entry["voice"]
    sentences = _split_sentences(script)
    if not sentences:
        await websocket.send_text(json.dumps({"event": "stop"}))
        await websocket.close()
        return

    try:
        kokoro = _get_kokoro()
    except Exception as e:
        await websocket.close(code=4003, reason=f"kokoro load failed: {e}")
        return

    try:
        for sentence in sentences:
            # Kokoro can occasionally take 5-10s on a long sentence.
            # We synthesize synchronously per sentence so the first chunk
            # is sent as soon as it's ready (true streaming UX).
            samples, sample_rate = kokoro.create(
                sentence, voice=voice, speed=1.1, lang="en-us"
            )
            pcm_bytes = _synthesize_sentence(samples, sample_rate)
            if pcm_bytes:
                await websocket.send_bytes(pcm_bytes)
        # Tell Vonage playback is complete so the call flow advances.
        await websocket.send_text(json.dumps({"event": "stop"}))
        # Hold the connection open until Vonage disconnects (caller hangup
        # or the platform sends a final stop event). This keeps the stream
        # NCCO action alive so timing is clean.
        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    data = json.loads(msg)
                except Exception:
                    data = {}
                if data.get("event") == "stop":
                    break
        except WebSocketDisconnect:
            pass
    except WebSocketDisconnect:
        # Caller hung up mid-stream \u2014 fine, exit cleanly.
        pass
    except Exception as e:
        # Best-effort: notify Vonage + close. We don't surface the error
        # via HTTP because we're already past the upgrade.
        try:
            await websocket.send_text(json.dumps({"event": "stop", "error": str(e)[:200]}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

