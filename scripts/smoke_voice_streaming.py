#!/usr/bin/env python3
"""
Smoke test for the voice streaming layer.

Restarts the synthetic_brain worker with the new streaming code, then:
  1. POST /api/v1/synthetic/register_stream
  2. WebSocket-connect to the returned ws_url
  3. Verify L16 16kHz mono PCM audio bytes arrive (Vonage-compatible)
  4. Verify the {"event": "stop"} text frame is sent when done
"""
import os
import sys
import json
import time
import asyncio
import subprocess
import urllib.request
import urllib.error

# Make project root importable
ROOT = "/root/empire-v49"
sys.path.insert(0, ROOT)

# CRITICAL: set the env var BEFORE any import of synthetic_brain. The
# module reads SYNTHETIC_BRAIN_API_KEY into _STREAM_SECRET at import
# time, and _verify_voice_id() refuses all signatures when the secret
# is empty. The default here is the same key the worker is launched with
# in production-style smoke tests, so signing round-trips correctly.
API_KEY = "test-key-please-change-in-production"
os.environ["SYNTHETIC_BRAIN_API_KEY"] = API_KEY
os.environ.setdefault("SYNTHETIC_BRAIN_STREAM_SECRET", API_KEY)

SYNTHETIC_BRAIN_URL = "http://127.0.0.1:8005"
SYNTHETIC_BRAIN_WS = "ws://127.0.0.1:8005"
LOG_PATH = os.path.join(ROOT, "synthetic_brain.log")


def step(name):
    def deco(fn):
        def wrap():
            print(f"\n=== {name} ===")
            try:
                fn()
            except AssertionError as e:
                print(f"  FAIL: {e}")
                sys.exit(1)
            except Exception as e:
                print(f"  ERROR: {e}")
                sys.exit(1)
            print(f"  OK")
        return wrap
    return deco


# ── Step 0: import sanity (synchronous, no async) ──────────────────
@step("0. import sanity check")
def import_check():
    from synthetic_brain import (
        _register_stream, _pop_stream, _sign_voice_id, _verify_voice_id,
        _split_sentences, _synthesize_sentence, STREAM_SAMPLE_RATE,
        StreamRegistrationRequest, _get_kokoro, _get_registry,
    )
    from empire_voice import ncco_stream_tts, VoiceRouter
    from bots.voice_streaming_agent import (
        VoiceStreamingAgent, get_streaming_interval, _script_for_target,
    )
    from empire_agi_governor import _AGENT_INTERVAL_HOURS
    assert "voice_streaming_agent" in _AGENT_INTERVAL_HOURS
    assert STREAM_SAMPLE_RATE == 16000
    assert hasattr(VoiceRouter, "place_streaming_strike")


# ── Step 1: unit tests for helpers ─────────────────────────────────
@step("1. unit tests: sentence splitter + HMAC round-trip + script templates")
def unit_tests():
    os.environ.setdefault("SYNTHETIC_BRAIN_API_KEY", "test-key")
    from synthetic_brain import (
        _split_sentences, _register_stream, _pop_stream,
        _get_registry, _STREAM_TTL_SECONDS,
    )
    # sentence splitter
    parts = _split_sentences("Hello world. How are you? Fine!")
    assert parts == ["Hello world.", "How are you?", "Fine!"], f"unexpected: {parts}"
    # register -> pop round-trip (now via the StreamRegistry abstraction)
    rec = _register_stream("Test script. Second sentence.", "am_michael", public_base_url="")
    assert rec["voice_id"] and rec["signature"] and rec["ws_url"]
    assert "ws://127.0.0.1:8005" in rec["ws_url"]
    _get_registry().set(
        rec["voice_id"],
        {"script": rec["script"], "voice": rec["voice"]},
        _STREAM_TTL_SECONDS,
    )
    entry = _pop_stream(rec["voice_id"], rec["signature"])
    assert entry is not None, "pop returned None on valid sig"
    assert entry["script"] == "Test script. Second sentence."
    assert _pop_stream(rec["voice_id"], "bad-sig") is None, "bad sig should be rejected"

    # Verify both backends are reachable from the factory
    from synthetic_brain import StreamRegistry, InMemoryStreamRegistry
    reg = _get_registry()
    assert isinstance(reg, StreamRegistry)
    assert isinstance(reg, InMemoryStreamRegistry)  # default backend in dev (no REDIS_URL)
    print(f"  active backend: {type(reg).__name__}")

    # ncco_stream_tts
    from empire_voice import ncco_stream_tts
    ncco = ncco_stream_tts("wss://example.com/stream?voice_id=xyz")
    assert isinstance(ncco, list) and len(ncco) >= 1
    assert ncco[-1]["action"] == "stream"
    assert ncco[-1]["streamUrl"] == ["wss://example.com/stream?voice_id=xyz"]
    ncco2 = ncco_stream_tts("wss://x/y", operator_number="+18005551234")
    assert ncco2[0]["action"] == "connect"
    assert ncco2[0]["endpoint"][0]["number"] == "18005551234"

    # script templates
    from bots.voice_streaming_agent import _script_for_target
    high = _script_for_target(
        {"warehouse_name": "Acme", "city": "Wichita", "state": "KS"},
        {"decision": "GO", "confidence": 0.9},
    )
    assert "Predictive Cloud" in high and "severe storm activity" in high and "Wichita, KS" in high
    low = _script_for_target(
        {"warehouse_name": "Acme", "city": "Wichita", "state": "KS"},
        {"decision": "GO", "confidence": 0.5},
    )
    assert "recent weather activity" in low and "Predictive Cloud" not in low
    nog = _script_for_target({}, {"decision": "NO_GO", "confidence": 0.1})
    assert "Thank you for calling Empire AI" in nog


# ── Step 2: kill old worker, start new one ─────────────────────────
@step("2. restart synthetic_brain worker with new streaming code")
def restart_worker():
    # Find and kill any process bound to :8005
    out = subprocess.run(["lsof", "-ti", ":8005"], capture_output=True, text=True)
    pids = [p for p in out.stdout.split() if p.strip()]
    for pid in pids:
        try:
            os.kill(int(pid), 15)
            print(f"  TERM {pid}")
        except ProcessLookupError:
            pass
    time.sleep(3)
    out = subprocess.run(["lsof", "-ti", ":8005"], capture_output=True, text=True)
    remaining = [p for p in out.stdout.split() if p.strip()]
    for pid in remaining:
        try:
            os.kill(int(pid), 9)
            print(f"  KILL -9 {pid}")
        except ProcessLookupError:
            pass
    time.sleep(2)

    # Start fresh worker
    with open(LOG_PATH, "w") as logf:
        pass  # truncate
    env = os.environ.copy()
    env["SYNTHETIC_BRAIN_API_KEY"] = API_KEY
    env["OLLAMA_MODEL"] = "llama3.2:3b"
    proc = subprocess.Popen(
        ["uvicorn", "synthetic_brain:app", "--host", "127.0.0.1", "--port", "8005", "--workers", "1"],
        cwd=ROOT, env=env, stdout=open(LOG_PATH, "a"), stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    print(f"  started uvicorn PID {proc.pid}")

    # Wait for /docs to be 200
    for i in range(1, 25):
        time.sleep(1)
        try:
            r = urllib.request.urlopen("http://127.0.0.1:8005/docs", timeout=2)
            if r.status == 200:
                print(f"  ready after {i}s")
                return
        except Exception:
            pass
    raise AssertionError("worker did not come up within 25s")


# ── Step 3: end-to-end (register + WebSocket + audio bytes) ────────
@step("3. end-to-end: register stream + WebSocket L16 audio + stop event")
def e2e_stream():
    import websockets
    import httpx

    async def main():
        # 1) Register
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(
                f"{SYNTHETIC_BRAIN_URL}/api/v1/synthetic/register_stream",
                json={
                    "script": "Storm alert for your facility. Hold while we connect you.",
                    "voice": "am_michael",
                },
                headers={"X-API-Key": API_KEY},
            )
            assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
            rec = r.json()
            print(f"  voice_id: {rec['voice_id'][:12]}...")
            print(f"  ws_url: {rec['ws_url']}")

        # 2) Connect WebSocket
        ws_url = rec["ws_url"]
        total = bytearray()
        stop_seen = False
        t0 = time.time()
        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024, ping_interval=None) as ws:
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=120)
                    if isinstance(msg, (bytes, bytearray)):
                        total.extend(msg)
                    else:
                        try:
                            data = json.loads(msg)
                        except Exception:
                            data = {}
                        if data.get("event") == "stop":
                            stop_seen = True
                            break
            except asyncio.TimeoutError:
                pass
        elapsed = time.time() - t0
        print(f"  WebSocket closed after {elapsed:.1f}s")
        print(f"  received {len(total)} bytes of L16 PCM")
        print(f"  stop event seen: {stop_seen}")
        assert len(total) > 0, "no audio received!"
        assert stop_seen, "no stop event sent!"
        # 1 sec of L16 16kHz mono = 16000 samples * 2 bytes = 32000 bytes
        secs = len(total) / 32000.0
        print(f"  estimated audio duration: {secs:.2f}s at 16kHz L16 mono")
        assert secs > 0.3, f"audio too short ({secs:.2f}s) — TTS may have failed silently"

    asyncio.run(main())


# ── Step 4: OpenAPI spec lists the new endpoints ───────────────────
@step("4. OpenAPI spec lists both new streaming endpoints")
def openapi_check():
    with urllib.request.urlopen(f"{SYNTHETIC_BRAIN_URL}/openapi.json", timeout=5) as r:
        spec = json.load(r)
    paths = list(spec.get("paths", {}).keys())
    print(f"  total endpoints: {len(paths)}")
    for p in sorted(paths):
        if "stream" in p or "synthetic" in p:
            print(f"  - {p}")
    assert any("register_stream" in p for p in paths), "register_stream endpoint missing from OpenAPI"
    assert any(p.endswith("/stream") for p in paths), "WebSocket /stream endpoint missing from OpenAPI"


# ── Step 5: confirm agent interval + worker env ───────────────────
@step("5. AGI governor has voice_streaming_agent registered + worker env OK")
def agent_check():
    from bots.voice_streaming_agent import get_streaming_interval
    v = get_streaming_interval()
    assert v == 0.5, f"unexpected interval: {v}"
    print(f"  voice_streaming_agent interval: {v}h")
    # Worker env check
    out = subprocess.run(["lsof", "-ti", ":8005"], capture_output=True, text=True)
    pid = out.stdout.split()[0] if out.stdout.strip() else None
    assert pid, "no worker on :8005"
    env_data = open(f"/proc/{pid}/environ", "rb").read().split(b"\x00")
    env = {kv.split(b"=", 1)[0].decode(): kv.split(b"=", 1)[1].decode()
           for kv in env_data if b"=" in kv}
    assert env.get("OLLAMA_MODEL") == "llama3.2:3b"
    assert env.get("SYNTHETIC_BRAIN_API_KEY")
    print(f"  worker PID {pid}: OLLAMA_MODEL={env['OLLAMA_MODEL']}")


def main():
    import_check()
    unit_tests()
    restart_worker()
    e2e_stream()
    openapi_check()
    agent_check()
    print("\n=== ALL STEPS PASSED ===")


if __name__ == "__main__":
    main()
