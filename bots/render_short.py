"""
EMPIRE V49 · SHORTS RENDER
===========================
Standalone render pipeline: Kokoro TTS → WhisperX alignment → ASS captions → FFmpeg 1080×1920.
Takes a script text and optional background video, outputs a vertical Shorts MP4.

Usage:
  python3 bots/render_short.py "Script text here"
  python3 bots/render_short.py "Script text" --bg templates/videos/storm.mp4 --output my_short.mp4
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
import soundfile as sf
import numpy as np
from pathlib import Path

# Deepgram TTS uses httpx for API calls
import httpx

# Load env vars so DEEPGRAM_API_KEY is available
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

REPO = Path(__file__).resolve().parent.parent

# ── Config ───────────────────────────────────────────────────────────
MEDIA_ENGINE_DIR = Path(os.environ.get("MEDIA_ENGINE_DIR", "/root/empire_media_engine"))
DEFAULT_BG = str(MEDIA_ENGINE_DIR / "templates/videos/fallback.mp4")
OUTPUT_DIR = REPO / "youtube_shorts_output"
OUTPUT_DIR.mkdir(exist_ok=True)

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_TTS_MODEL = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-asteria-en")

# ── Render Pipeline ──────────────────────────────────────────────────

# ── TTS Providers ────────────────────────────────────────────────────

def _tts_kokoro(text: str, wav_path: str, speed: float = 1.0) -> float:
    """Generate TTS audio using local Kokoro model.
    Args:
        text: Text to speak
        wav_path: Output WAV path
        speed: Speaking speed multiplier (0.5-2.0, default 1.0)
    Returns duration in seconds.
    """
    from kokoro import KPipeline
    pipeline = KPipeline(lang_code="a", model="af_heart")
    audio_gen = pipeline(text, voice="af_heart", speed=speed)
    all_audio = []
    for gs, ps, audio in audio_gen:
        all_audio.append(audio)
    if not all_audio:
        raise RuntimeError("Kokoro TTS produced no audio")
    full = np.concatenate(all_audio)
    sf.write(wav_path, full, 24000)
    return len(full) / 24000


def _tts_deepgram(text: str, wav_path: str, speed: float = 1.0) -> float:
    """Generate TTS audio using Deepgram Aura API.
    Args:
        text: Text to speak
        wav_path: Output WAV path
        speed: Speaking speed multiplier (0.7-1.5, default 1.0)
    Returns duration in seconds.
    Requires DEEPGRAM_API_KEY in environment.
    """
    if not DEEPGRAM_API_KEY:
        raise RuntimeError(
            "DEEPGRAM_API_KEY not set. Add it to /root/.env or pass --voice-provider kokoro"
        )

    url = f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_TTS_MODEL}&encoding=linear16&sample_rate=24000&speed={speed}"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}

    resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Deepgram TTS failed ({resp.status_code}): {resp.text[:200]}")

    # Convert linear16 raw PCM to proper WAV using soundfile
    raw = np.frombuffer(resp.content, dtype=np.int16)
    sf.write(wav_path, raw, 24000)
    return len(raw) / 24000


TTS_PROVIDERS = {
    "kokoro": _tts_kokoro,
    "deepgram": _tts_deepgram,
}


# ── Render Pipeline ──────────────────────────────────────────────────

def render_short(script_text: str, bg_video: str = "", output_path: str = "",
                 voice_provider: str = "", voice_speed: float = 1.0) -> dict:
    """Run the full render pipeline: TTS → WhisperX → ASS → FFmpeg.

    Args:
        script_text: The text to be spoken in the video.
        bg_video: Path to background video (default: fallback.mp4 from media engine).
        output_path: Where to save the MP4 (default: youtube_shorts_output/).
        voice_provider: "deepgram" (API), "kokoro" (local), or BUFFY_DEFAULT_VOICE env var.
        voice_speed: Speaking speed multiplier (0.5-2.0, default 1.0).
    """
    if not voice_provider:
        voice_provider = os.environ.get("BUFFY_DEFAULT_VOICE", "deepgram")

    import whisperx

    bg = bg_video or DEFAULT_BG
    if not os.path.exists(bg):
        return {"ok": False, "error": f"Background video not found: {bg}"}

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in script_text[:30])
        output_path = str(OUTPUT_DIR / f"short_{safe}_{ts}.mp4")

    builds_dir = OUTPUT_DIR / "builds"
    builds_dir.mkdir(exist_ok=True)

    try:
        # ── Step 1: TTS ──────────────────────────────────────────────
        tts_fn = TTS_PROVIDERS.get(voice_provider)
        if not tts_fn:
            return {"ok": False, "error": f"Unknown voice provider: {voice_provider}. Choose from: {', '.join(TTS_PROVIDERS.keys())}"}

        print(f"1/4 Generating voice ({voice_provider})...")
        wav_path = str(builds_dir / f"voice_{os.getpid()}.wav")
        duration = tts_fn(script_text, wav_path, speed=voice_speed)
        print(f"  ✓ {duration:.1f}s audio  (speed={voice_speed})")

        # ── Step 2: WhisperX word alignment ─────────────────────────
        print("2/4 Aligning words (WhisperX)...")
        model = whisperx.load_model("tiny", device="cpu", compute_type="int8")
        audio = whisperx.load_audio(wav_path)
        res = model.transcribe(audio, batch_size=4)
        ma, meta = whisperx.load_align_model(language_code=res["language"], device="cpu")
        aligned = whisperx.align(res["segments"], ma, meta, audio, "cpu")
        print(f"  ✓ {len(aligned['segments'])} segments")

        # ── Step 3: Build ASS captions ──────────────────────────────
        print("3/4 Building captions...")
        ass_path = str(builds_dir / f"captions_{os.getpid()}.ass")
        KEYWORDS = {"lead", "smart", "instant", "roof", "roofs",
                     "storm", "storms", "hail", "damage", "damages",
                     "free", "claim", "claims", "no", "no-risk", "yes",
                     "empire", "ai", "dollar", "dollars", "12", "000",
                     "fees", "money", "k"}
        with open(ass_path, "w") as f:
            f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n")
            f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
                    "BackColour, Bold, Underline, BorderStyle, Outline, Shadow, "
                    "Alignment, MarginL, MarginR, MarginV, AlphaLevel\n")
            f.write("Style: Default,Arial,48,&H00FFFFFF,&H00000000,0,0,1,2,2,2,"
                    "10,10,10,0\n")
            f.write("Style: Highlight,Arial,48,&H0014FF39,&H00000000,0,0,1,2,2,2,"
                    "10,10,10,0\n")
            f.write("[Events]\nFormat: Layer, Start, End, Style, Name, "
                    "MarginL, MarginR, MarginV, Effect, Text\n")
            for seg in aligned["segments"]:
                for w in seg.get("words", []):
                    ws = w.get("start", seg["start"])
                    we = w.get("end", seg["end"])
                    wt = w.get("word", "").strip().lower()
                    if wt:
                        style = "Highlight" if wt.strip(".,!?").lower() in KEYWORDS else "Default"
                        f.write(f"Dialogue: 0,{ws:.2f},{we:.2f},{style},,"
                                f"0,0,0,,{w.get('word','').strip()}\n")
        print(f"  ✓ {ass_path}")

        # ── Step 4: FFmpeg render ───────────────────────────────────
        print("4/4 Rendering...")
        vf = f"scale=1080:1920:force_original_aspect_ratio=increase," \
             f"crop=1080:1920," \
             f"ass={ass_path}"
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", bg,
            "-i", wav_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{duration:.2f}",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {"ok": False, "error": f"FFmpeg failed: {result.stderr[-500:]}"}

        size_kb = os.path.getsize(output_path) // 1024
        print(f"  ✓ {output_path} ({size_kb}KB)")

        # Clean up temp files
        for tmp in [wav_path, ass_path]:
            try:
                os.remove(tmp)
            except OSError:
                pass

        return {
            "ok": True,
            "output_path": output_path,
            "duration_s": round(duration, 1),
            "size_kb": size_kb,
            "voice_provider": voice_provider,
            "voice_speed": voice_speed,
            "bg_used": bg,
        }

    except ImportError as e:
        return {"ok": False, "error": f"Missing dependency: {e}. Install with: pip install httpx kokoro whisperx soundfile numpy"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Render a Shorts video from script text")
    p.add_argument("script", nargs="?", default="", help="Script text to render")
    p.add_argument("--bg", default="", help="Background video path")
    p.add_argument("--output", default="", help="Output MP4 path")
    p.add_argument("--topic", default="", help="Generate a topic-based Short")
    p.add_argument("--voice-provider", default=os.environ.get("BUFFY_DEFAULT_VOICE", "deepgram"),
                    choices=list(TTS_PROVIDERS.keys()),
                    help="TTS engine: deepgram (API) or kokoro (local) (default: $BUFFY_DEFAULT_VOICE)")
    p.add_argument("--voice-speed", type=float, default=1.0,
                    help="Speaking speed multiplier (0.5-2.0, default 1.0). Deepgram: 0.7-1.5, Kokoro: 0.5-2.0")
    p.add_argument("--voice-rate", type=float, default=None,
                    help="Alias for --voice-speed (kept for compatibility)")
    p.add_argument("--buffy-job-id", default="",
                    help="If set, reports status back to the video_automation_jobs table (Buffy Buffer)")
    args = p.parse_args()

    script = args.script or ""
    if args.topic and not script:
        script = (
            f"{args.topic}. "
            "Empire AI uses artificial intelligence to detect storms "
            "and deliver qualified leads to restoration contractors. "
            "Visit empire-ai.co.uk to get started free."
        )

    if not script:
        script = (
            "Most contractors miss out on storm damage leads because they "
            "can't detect opportunities fast enough. Empire AI's predictive "
            "technology scans weather data in real-time. When a storm hits "
            "your area, you get an SMS with a qualified lead within minutes. "
            "No cold calling. No guessing. Visit empire-ai.co.uk and get "
            "your first 2 deals free. No contract. No risk."
        )

    print(f"Rendering: {script[:80]}...")
    speed = args.voice_rate if args.voice_rate is not None else args.voice_speed
    result = render_short(script, args.bg, args.output, voice_provider=args.voice_provider, voice_speed=speed)
    print(json.dumps(result, indent=2))

    # Report status back to Buffy if --buffy-job-id was provided
    if args.buffy_job_id:
        try:
            from supabase import create_client
            sb = create_client(
                os.environ.get("SUPABASE_URL", ""),
                os.environ.get("SUPABASE_SERVICE_KEY", "")
            )
            now = datetime.now().isoformat()
            if result.get("ok"):
                sb.table("video_automation_jobs").update({
                    "status": "DONE",
                    "output_path": result.get("output_path", ""),
                    "duration_s": result.get("duration_s", 0),
                    "size_kb": result.get("size_kb", 0),
                    "completed_at": now,
                    "error": "",
                }).eq("id", args.buffy_job_id).execute()
            else:
                sb.table("video_automation_jobs").update({
                    "status": "FAILED",
                    "error": result.get("error", "Unknown error")[:2000],
                    "completed_at": now,
                }).eq("id", args.buffy_job_id).execute()
            print(f"  (reported to buffy job {args.buffy_job_id[:8]})")
        except Exception as e:
            print(f"  (buffy status report failed: {e})")

    if result.get("ok"):
        print(f"\n✓ Video ready: {result['output_path']}")
    else:
        print(f"\n✗ Render failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
