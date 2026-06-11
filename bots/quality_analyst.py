"""
EMPIRE V49 · QUALITY ANALYST BOT
=================================
Transcribes call recordings from call_logs, scores them via Ollama on
qualification accuracy, sentiment, and churn risk, then writes results
back to call_logs for the Profitability dashboard.

Flow:
  1. Query call_logs for unscored records with recording_url
  2. Download + transcribe via OpenAI Whisper API
  3. Score transcript via Ollama (llama3.2:3b) on 3 axes
  4. Write scores back to call_logs
  5. Log to brain_training_log for the learning loop

Run manually:  python3 bots/quality_analyst.py
Run via mesh:  schedule as a recurring agent task
"""

import os
import sys
import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

import httpx
from supabase import create_client

log = logging.getLogger("empire.quality")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── CONFIG ──────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
WHISPERX_MODEL = os.environ.get("WHISPERX_MODEL", "base")
WHISPERX_DEVICE = os.environ.get("WHISPERX_DEVICE", "cpu")
WHISPERX_BATCH_SIZE = int(os.environ.get("WHISPERX_BATCH_SIZE", "8"))
WHISPERX_COMPUTE_TYPE = os.environ.get("WHISPERX_COMPUTE_TYPE", "float16" if WHISPERX_DEVICE == "cuda" else "int8")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("AI_MODEL_ENRICH", "llama3.2:3b")
BATCH_LIMIT = 5          # max calls to process per run
POLL_INTERVAL = 300      # seconds between runs (when used as loop)

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── SCORING PROMPT ──────────────────────────────────────────────────
SCORING_PROMPT = """You are an expert call quality analyst for a roofing/restoration dispatch service.
Analyze the following call transcript and score it on three axes from 0.0 to 1.0.

Rules:
- qualification_score: How well did the agent follow the script? Did they identify
  the property damage, explain the free inspection offer, and attempt to book?
  1.0 = perfect script adherence, 0.0 = completely off-script.
- sentiment_score: Customer satisfaction. Did the homeowner sound engaged,
  positive, or interested? 1.0 = very positive, 0.0 = hostile/hang-up.
- churn_risk: Likelihood the buyer drops the call early or doesn't convert.
  Higher = more risk. 1.0 = certain churn, 0.0 = highly likely to convert.

Respond with ONLY valid JSON:
{"qualification_score": 0.XX, "sentiment_score": 0.XX, "churn_risk": 0.XX, "reasoning": "brief one-sentence note about the call quality"}

Transcript:
"""


# ── TRANSCRIPTION ───────────────────────────────────────────────────
# ── WHISPERX LOCAL MODEL CACHE ──────────────────────────────────────────
_whisperx_model = None


def _get_whisperx_model():
    """Lazy-load the local WhisperX model. Model is cached after first load."""
    global _whisperx_model
    if _whisperx_model is not None:
        return _whisperx_model
    try:
        import whisperx
        log.info(f"[quality] loading WhisperX model '{WHISPERX_MODEL}' on {WHISPERX_DEVICE}...")
        _whisperx_model = whisperx.load_model(
            WHISPERX_MODEL,
            device=WHISPERX_DEVICE,
            compute_type=WHISPERX_COMPUTE_TYPE,
            asr_options={"word_timestamps": False},
        )
        log.info(f"[quality] WhisperX model loaded")
    except Exception as e:
        log.error(f"[quality] WhisperX load failed: {e}")
        _whisperx_model = None
    return _whisperx_model


async def _transcribe_audio(recording_url: str) -> Optional[str]:
    """Download and transcribe a recording.
    Uses local WhisperX if available (no external API calls → local sovereignty).
    Falls back to OpenAI Whisper API if WhisperX unavailable and API key configured.
    Falls back to stub text if neither is available."""
    if not recording_url:
        return None

    # Strategy 1: Local WhisperX (preferred — no external calls)
    local_model = _get_whisperx_model()
    if local_model is not None:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(recording_url, follow_redirects=True)
                if r.status_code != 200:
                    log.warning(f"[quality] download failed: HTTP {r.status_code} for {recording_url[:60]}")
                    return None

                # Save audio to temp file for WhisperX
                import tempfile
                import os as _os
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.write(r.content)
                tmp.close()

                try:
                    # Run WhisperX transcription (blocking, run in thread pool)
                    import asyncio as _asyncio
                    result = await _asyncio.to_thread(
                        lambda: local_model.transcribe(tmp.name, batch_size=WHISPERX_BATCH_SIZE)
                    )
                    segments = result.get("segments", [])
                    text = " ".join(seg["text"] for seg in segments if seg.get("text"))
                    log.info(f"[quality] WhisperX transcribed {len(text)} chars from {recording_url[:40]}...")
                    return text
                finally:
                    try:
                        _os.unlink(tmp.name)
                    except Exception:
                        pass
        except Exception as e:
            log.warning(f"[quality] WhisperX transcription error: {e}, falling back")

    # Strategy 2: OpenAI Whisper API (external, requires API key)
    if OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(recording_url, follow_redirects=True)
                if r.status_code != 200:
                    log.warning(f"[quality] download failed: HTTP {r.status_code} for {recording_url[:60]}")
                    return None

                files = {"file": ("audio.mp3", r.content, "audio/mpeg")}
                data = {"model": "whisper-1", "response_format": "json"}
                wr = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files=files,
                    data=data,
                    timeout=120.0,
                )
                if wr.status_code == 200:
                    result = wr.json()
                    text = result.get("text", "")
                    log.info(f"[quality] Whisper API transcribed {len(text)} chars from {recording_url[:40]}...")
                    return text
                else:
                    log.warning(f"[quality] Whisper API error: HTTP {wr.status_code}")
                    return None
        except Exception as e:
            log.error(f"[quality] Whisper API error: {e}")
            return None

    log.info(f"[quality] No transcription available for {recording_url[:60]}")
    return "[transcription unavailable]"


# ── SCORING ─────────────────────────────────────────────────────────
async def _score_transcript(transcript: str) -> Optional[dict]:
    """Score a transcript via Ollama. Returns dict with scores or None."""
    if not transcript or transcript.startswith("[transcription skipped"):
        return None

    prompt = SCORING_PROMPT + transcript

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 256},
                },
            )
            if r.status_code != 200:
                log.warning(f"[quality] Ollama error: HTTP {r.status_code}")
                return None

            resp_text = r.json().get("response", "")
            # Extract JSON from the response (Ollama might wrap in markdown)
            json_str = resp_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            scores = json.loads(json_str)
            # Validate and clamp
            for key in ["qualification_score", "sentiment_score", "churn_risk"]:
                val = scores.get(key)
                if val is not None:
                    scores[key] = max(0.0, min(1.0, float(val)))
                else:
                    scores[key] = 0.0

            log.info(f"[quality] scored: qual={scores.get('qualification_score')}, "
                     f"sent={scores.get('sentiment_score')}, churn={scores.get('churn_risk')}")
            return scores
    except Exception as e:
        log.error(f"[quality] scoring error: {e}")
        return None


# ── MAIN PIPELINE ───────────────────────────────────────────────────
async def run_once(dry_run: bool = False) -> dict:
    """Run the quality analyst pipeline once. Returns summary dict."""
    results = {"processed": 0, "transcribed": 0, "scored": 0, "errors": 0}

    # 1. Find unscored call_logs with recording URLs
    try:
        query = _sb.table("call_logs") \
            .select("id,vonage_call_id,recording_url,created_at") \
            .is_("scored_at", "null") \
            .not_.is_("recording_url", "null") \
            .order("created_at", desc=True) \
            .limit(BATCH_LIMIT) \
            .execute()
    except Exception as e:
        # recording_url column might not exist yet — check schema
        log.info(f"[quality] query failed (column may not exist): {e}")
        return results

    calls = query.data or []
    if not calls:
        log.info("[quality] no unscored calls with recordings found")
        return results

    log.info(f"[quality] found {len(calls)} calls to process")

    for call in calls:
        call_id = call["id"]
        recording_url = call.get("recording_url", "")
        if not recording_url:
            continue

        try:
            # 2. Transcribe
            transcript = await _transcribe_audio(recording_url)
            if not transcript:
                results["errors"] += 1
                continue
            results["transcribed"] += 1

            # 3. Score
            scores = await _score_transcript(transcript)
            if not scores:
                results["errors"] += 1
                continue
            results["scored"] += 1

            # 4. Write back to call_logs
            if not dry_run:
                update = {
                    "transcript_text": transcript[:5000],  # cap at 5k chars
                    "quality_score": scores.get("qualification_score", 0),
                    "qualification_score": scores.get("qualification_score", 0),
                    "sentiment_score": scores.get("sentiment_score", 0),
                    "churn_risk": scores.get("churn_risk", 0),
                    "scored_at": datetime.now(timezone.utc).isoformat(),
                }
                _sb.table("call_logs").update(update).eq("id", call_id).execute()

                # Also log to brain_training_log
                try:
                    _sb.table("brain_training_log").insert({
                        "lead_source": "quality_analyst",
                        "decision": "SCORED",
                        "reasoning": scores.get("reasoning", ""),
                        "meta": json.dumps({
                            "call_id": call_id,
                            "scores": scores,
                        }),
                    }).execute()
                except Exception:
                    pass  # table may not exist

            results["processed"] += 1
            log.info(f"[quality] processed call {call_id[:8]}: {scores}")

        except Exception as e:
            log.error(f"[quality] error processing call {call_id[:8]}: {e}")
            results["errors"] += 1

    return results


async def run_loop():
    """Run the quality analyst in a loop, suitable for background tasks."""
    log.info("[quality] starting background loop (interval=%ds)", POLL_INTERVAL)
    while True:
        try:
            results = await run_once()
            log.info(f"[quality] cycle complete: {results}")
        except Exception as e:
            log.error(f"[quality] cycle error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


# ── MESH INTEGRATION (HERMES PROTOCOL) ──────────────────────────────

async def process_mesh_task(task: dict, dry_run: bool = False) -> dict:
    """
    Process a 'revenue.score_call' task from the agent_task_queue.
    Delegates to run_once() and updates the mesh ticket status.
    """
    results = await run_once(dry_run=dry_run)

    # Update the mesh ticket if we have one
    ticket_id = task.get("ticket_id") if isinstance(task, dict) else None
    if ticket_id and not dry_run:
        try:
            status = "Done" if results.get("scored", 0) > 0 else "Done"
            _sb.table("agent_task_queue").update({
                "status": status,
                "result": json.dumps(results),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
        except Exception as e:
            log.warning(f"[quality] mesh ticket update error: {e}")

    return results


# ── ENTRY POINT ─────────────────────────────────────────────────────
if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        results = asyncio.run(run_once(dry_run=dry))
        print(json.dumps(results, indent=2))
