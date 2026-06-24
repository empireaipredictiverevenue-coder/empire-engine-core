#!/usr/bin/env python3
"""
EMPIRE V49 · BUFFY WORKER — RENDER EXECUTOR
============================================
Polls Supabase for RENDER_TRIGGERED jobs, claims them atomically, runs
the full render pipeline (via render_short.py), and updates the job status
to DONE or FAILED.

Works alongside bots/buffy_buffer.py:
  - Buffy Buffer manages the capacity gate (BUFFY_BUFFERED → RENDER_TRIGGERED)
  - Buffy Worker executes the released jobs (RENDER_TRIGGERED → PROCESSING → DONE)

PM2 entry:  buffy-worker (scale to 1-3 instances per BUFFY_MAX_CONCURRENT)
Run:        python3 -m bots.buffy_worker
"""

import os
import sys
import json
import time
import asyncio
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [buffy-worker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("buffy-worker")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
REPO = Path(__file__).resolve().parent.parent
RENDER_SCRIPT = REPO / "bots" / "render_short.py"
POLL_INTERVAL = int(os.environ.get("BUFFY_WORKER_POLL_SEC", "30"))
HEARTBEAT_INTERVAL = int(os.environ.get("BUFFY_WORKER_HEARTBEAT_SEC", "60"))
AGENT_NAME = "buffy.worker"
WORKER_ID = os.environ.get("BUFFY_WORKER_ID", f"buffy-worker-{os.getpid()}")

# ── Supabase ────────────────────────────────────────────────────────
if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Job lifecycle ────────────────────────────────────────────────────

def claim_next_job() -> dict | None:
    """Atomically claim the highest-priority RENDER_TRIGGERED job.

    Uses Supabase RPC if available, otherwise falls back to a
    read-then-update pattern with status guard.
    """
    try:
        # Prefer RPC if available
        try:
            r = sb.rpc("claim_video_render_job", {
                "p_worker_id": WORKER_ID,
            }).execute()
            if r.data and len(r.data) > 0:
                return r.data[0]
        except Exception:
            pass

        # Fallback: lock by update where status=RENDER_TRIGGERED
        now = datetime.now(timezone.utc).isoformat()
        r = sb.table("video_automation_jobs") \
            .select("*") \
            .eq("status", "RENDER_TRIGGERED") \
            .order("priority", desc=True) \
            .order("created_at") \
            .limit(1) \
            .execute()

        if not r.data:
            return None

        job = r.data[0]
        job_id = job["id"]

        # Try to claim atomically
        claim = sb.table("video_automation_jobs") \
            .update({
                "status": "PROCESSING",
                "started_at": now,
                "worker_id": WORKER_ID,
                "last_heartbeat": now,
                "updated_at": now,
            }) \
            .eq("id", job_id) \
            .eq("status", "RENDER_TRIGGERED") \
            .execute()

        if claim.data:
            return job
        return None

    except Exception as e:
        log.warning(f"claim_next_job failed: {e}")
        return None


def update_job(job_id: str, update: dict):
    """Update a job record in Supabase."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        update["updated_at"] = now
        sb.table("video_automation_jobs") \
            .update(update) \
            .eq("id", job_id) \
            .execute()
    except Exception as e:
        log.warning(f"update_job {job_id[:8]} failed: {e}")


def heartbeat():
    """Register in agent_registry."""
    try:
        sb.table("agent_registry").upsert({
            "agent_name": AGENT_NAME,
            "status": "ACTIVE",
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": ["buffy", "render", "video", "ffmpeg", "tts"],
            "task_types": ["buffy.render"],
            "metrics": {"worker_id": WORKER_ID},
        }, on_conflict="agent_name").execute()
    except Exception as e:
        log.debug(f"heartbeat failed: {e}")


# ── Render execution ─────────────────────────────────────────────────

async def execute_job(job: dict) -> dict:
    """Run the render pipeline for a single job.

    Calls render_short.py as a subprocess with the job's parameters.
    Updates job status to PROCESSING → DONE or FAILED.
    """
    job_id = job["id"]
    topic = job.get("topic", "")
    script_text = job.get("script_text", "")
    voice_provider = job.get("voice_provider", "kokoro")
    bg_video = job.get("bg_video", "")

    log.info(f"Rendering job {job_id[:8]}: '{topic[:60]}' ({voice_provider})")

    # Build command — prefix with Python interpreter since render_short.py
    # is a module without a shebang (called as a script by subprocess)
    cmd = [sys.executable, str(RENDER_SCRIPT)]
    if script_text:
        cmd.append(script_text)
    else:
        cmd.append("--topic")
        cmd.append(topic or "AI-powered storm detection for contractors")
    if voice_provider:
        cmd.append("--voice-provider")
        cmd.append(voice_provider)
    if bg_video:
        cmd.append("--bg")
        cmd.append(bg_video)
    # Tell render_short.py to report back to this job
    cmd += ["--buffy-job-id", job_id]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(REPO),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode == 0:
            # Parse output for result JSON
            output = stdout.decode() if stdout else ""
            result = extract_result(output)
            if result.get("ok"):
                update_job(job_id, {
                    "status": "DONE",
                    "output_path": result.get("output_path", ""),
                    "duration_s": result.get("duration_s", 0),
                    "size_kb": result.get("size_kb", 0),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": "",
                })
                log.info(f"Job {job_id[:8]} DONE  →  {result.get('output_path', '?')}")
                return {"ok": True, "job_id": job_id}
            else:
                err = result.get("error", "Render reported failure")
                update_job(job_id, {
                    "status": "FAILED",
                    "error": err[:2000],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                log.error(f"Job {job_id[:8]} FAILED: {err[:200]}")
                return {"ok": False, "error": err}
        else:
            err_text = stderr.decode() if stderr else "Unknown error"
            update_job(job_id, {
                "status": "FAILED",
                "error": err_text[:2000],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            log.error(f"Job {job_id[:8]} process failed ({proc.returncode})")
            return {"ok": False, "error": err_text[:500]}

    except asyncio.TimeoutError:
        update_job(job_id, {
            "status": "FAILED",
            "error": "Render timed out after 300s",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        log.error(f"Job {job_id[:8]} TIMEOUT")
        return {"ok": False, "error": "Render timed out after 300s"}

    except Exception as e:
        update_job(job_id, {
            "status": "FAILED",
            "error": f"{type(e).__name__}: {str(e)[:500]}",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        log.error(f"Job {job_id[:8]} exception: {e}")
        return {"ok": False, "error": str(e)[:500]}


def extract_result(output: str) -> dict:
    """Parse the JSON result from render_short.py output.

    render_short.py outputs json.dumps(result, indent=2) (multi-line JSON).
    This finds the first '{' and last '}' to extract the full JSON block.
    """
    try:
        start = output.index("{")
        end = output.rindex("}") + 1
        return json.loads(output[start:end])
    except (ValueError, json.JSONDecodeError):
        return {}


# ── Main loop ────────────────────────────────────────────────────────

async def run_loop():
    """Poll for RENDER_TRIGGERED jobs, claim and execute them."""
    log.info(f"BUFFY WORKER ONLINE  (worker_id={WORKER_ID}, poll={POLL_INTERVAL}s)")
    heartbeat()
    last_heartbeat = 0

    while True:
        try:
            now = int(time.time())

            # Heartbeat every HEARTBEAT_INTERVAL
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                heartbeat()
                last_heartbeat = now

            # Claim and execute one job at a time
            job = claim_next_job()
            if job:
                await execute_job(job)
            else:
                await asyncio.sleep(1)  # no job — quick sleep before next poll

        except Exception as e:
            log.error(f"Loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


def main():
    """Entry point for PM2 / direct execution."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
