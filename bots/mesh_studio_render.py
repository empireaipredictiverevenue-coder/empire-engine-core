"""
EMPIRE V49 · MESH STUDIO RENDER (HERMES PROTOCOL · STUDIO TEAM B)
=================================================================
Render Pro agent. Monitors the agent_task_queue for 'studio.render_reel'
tasks. When found, grabs the script and executes the local FFmpeg build
via the media engine's render_pro.py to produce the final video reel.

Moves the ticket to 'Done' with the output path, or 'Failed' on error.

Local sovereignty: All processing is local FFmpeg — no external API calls.
"""

import os
import sys
import json
import asyncio
import subprocess
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("mesh.studio.render")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
MEDIA_ENGINE_DIR = "/root/empire_media_engine"
RENDER_SCRIPT = "render_pro.py"
DEFAULT_BG = "templates/videos/pexels_test.mp4"

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)


async def run_ffmpeg_render(script: str, metro: str, bg_path: str = "") -> Optional[Dict]:
    """
    Execute the FFmpeg render via render_pro.py.
    Returns dict with output_path, duration_s, status, or None on failure.
    """
    if not os.path.exists(MEDIA_ENGINE_DIR):
        log.warning(f"[render] media engine dir not found: {MEDIA_ENGINE_DIR}")
        return None

    bg_arg = bg_path.replace(MEDIA_ENGINE_DIR + "/", "") if bg_path else DEFAULT_BG

    cmd = ["python3", RENDER_SCRIPT, bg_arg, script]
    log.info(f"[render] running: cd {MEDIA_ENGINE_DIR} && {' '.join(cmd)}")

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            cwd=MEDIA_ENGINE_DIR,
            timeout=120,
        )

        if proc.returncode == 0:
            output = proc.stdout.strip()
            log.info(f"[render] FFmpeg success for {metro}")
            return {
                "status": "success",
                "returncode": 0,
                "output": output[:500],
                "stdout_tail": output[-200:] if len(output) > 200 else output,
            }
        else:
            log.warning(f"[render] FFmpeg error (code {proc.returncode}) for {metro}")
            return {
                "status": "failed",
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-500:],
            }
    except subprocess.TimeoutExpired:
        log.error(f"[render] FFmpeg timeout for {metro}")
        return {"status": "timeout", "error": "FFmpeg exceeded 120s timeout"}
    except Exception as e:
        log.error(f"[render] FFmpeg exception: {e}")
        return {"status": "error", "error": str(e)}


async def process_task(task: Dict, dry_run: bool = False) -> Dict:
    """
    Process one render task: run FFmpeg build, mark complete.
    Returns result dict.
    """
    ticket_id = task.get("ticket_id")
    payload = task.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    metro = payload.get("metro", "unknown")
    script = payload.get("script", "")
    headline = payload.get("headline", "")
    niche = payload.get("niche", "roofing")

    log.info(f"[render] processing task {ticket_id[:8]} for {metro}")
    log.info(f"[render] script: {script[:80]}...")

    if dry_run:
        log.info(f"[render] DRY RUN: would render reel for {metro}")
        log.info(f"[render]   script: {script}")
        log.info(f"[render]   headline: {headline}")
        return {
            "ticket_id": ticket_id,
            "status": "dry_run",
            "metro": metro,
        }

    # Run the FFmpeg render
    render_result = await run_ffmpeg_render(script, metro)

    if not render_result:
        # Try to update task status
        try:
            _sb.table("agent_task_queue").update({
                "status": "Failed",
                "error": "FFmpeg render pipeline unavailable (media engine not found)",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
        except Exception:
            pass
        return {"ticket_id": ticket_id, "status": "failed", "error": "media engine not found"}

    if render_result.get("status") == "success":
        # Also log the ad spend to spend_logs
        try:
            _sb.table("spend_logs").insert({
                "niche": niche,
                "metro": metro,
                "source": "mesh.render",
                "amount_spent": 15.0,  # estimated CPM cost
                "cost_type": "cpm_estimate",
                "meta": json.dumps({
                    "script": script[:100],
                    "headline": headline,
                    "source_task": ticket_id,
                    "render_result": render_result.get("output", "")[:100],
                }),
            }).execute()
        except Exception as e:
            log.warning(f"[render] spend_log error: {e}")

        # Mark Done
        try:
            _sb.table("agent_task_queue").update({
                "status": "Done",
                "result": json.dumps({
                    "metro": metro,
                    "render_status": "success",
                    "script": script[:200],
                    "output": render_result.get("output", "")[:300],
                }),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
            log.info(f"[render] task {ticket_id[:8]} completed → Done")
        except Exception as e:
            log.error(f"[render] status update error: {e}")

        return {
            "ticket_id": ticket_id,
            "status": "done",
            "metro": metro,
            "render_status": "success",
        }
    else:
        # Mark Failed
        error_msg = render_result.get("stderr_tail", render_result.get("error", "unknown error"))
        try:
            _sb.table("agent_task_queue").update({
                "status": "Failed",
                "error": str(error_msg)[:1000],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
        except Exception:
            pass
        return {"ticket_id": ticket_id, "status": "failed", "error": error_msg[:200]}


async def run_once(dry_run: bool = False, max_tasks: int = 2) -> Dict:
    """
    Main entry point: claim 'studio.render_reel' tasks and process them.
    """
    results = {"claimed": 0, "completed": 0, "failed": 0}

    try:
        tasks_processed = 0
        while tasks_processed < max_tasks:
            r = _sb.rpc("claim_next_task", {
                "p_agent_name": "mesh.render",
                "p_task_types": ["studio.render_reel"],
            }).execute()

            if not r.data:
                break  # No more tasks

            task = r.data
            task["payload"] = json.loads(task.get("payload", "{}")) if isinstance(task.get("payload"), str) else task.get("payload", {})
            results["claimed"] += 1

            result = await process_task(task, dry_run=dry_run)
            if result.get("status") == "done":
                results["completed"] += 1
            else:
                results["failed"] += 1

            tasks_processed += 1

    except Exception as e:
        log.error(f"[render] run_once error: {e}")
        results["error"] = str(e)

    log.info(f"[render] run complete: {results}")
    return results


async def run_loop(interval_sec: int = 30):
    """Run the render pro in a background loop."""
    log.info(f"[render] starting background loop (interval={interval_sec}s)")
    while True:
        try:
            results = await run_once()
            if results["claimed"] > 0:
                log.info(f"[render] cycle: {results}")
        except Exception as e:
            log.error(f"[render] cycle error: {e}")
        await asyncio.sleep(interval_sec)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        results = asyncio.run(run_once(dry_run=dry))
        print(json.dumps(results, indent=2))
