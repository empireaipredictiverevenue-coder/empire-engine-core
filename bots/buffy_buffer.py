#!/usr/bin/env python3
"""
EMPIRE V49 · BUFFY BUFFER — THE QUEUE CONTROLLER
================================================
Concurrency manager for the video render pipeline. Prevents server lockouts
by monitoring active render lanes and buffering excess jobs.

Option 1 from the Buffy Engine spec:
  "Protects Hetzner hardware by buffering rendering spikes."

Protocol:
  1. Poll every 3 seconds
  2. Count active PROCESSING jobs
  3. If active < MAX_CONCURRENT (3), release oldest BUFFY_BUFFERED → RENDER_TRIGGERED
  4. Log queue metrics to video_automation_jobs and agent_activity
  5. Flag jobs stuck in buffer > 15 minutes for alerting

PM2 entry:  buffy-buffer
Run:        python3 -m bots.buffy_buffer
"""

import os
import sys
import json
import time
import asyncio
import logging
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
    format="%(asctime)s [buffy] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("buffy")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
MAX_CONCURRENT = int(os.environ.get("BUFFY_MAX_CONCURRENT", "3"))
POLL_INTERVAL = int(os.environ.get("BUFFY_POLL_SEC", "3"))
STUCK_THRESHOLD_MIN = int(os.environ.get("BUFFY_STUCK_MINUTES", "15"))
AGENT_NAME = "buffy.buffer"

# ── Supabase client ─────────────────────────────────────────────────
if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Helpers ──────────────────────────────────────────────────────────

def _count_processing() -> int:
    """Count jobs currently in PROCESSING state."""
    try:
        r = sb.table("video_automation_jobs") \
            .select("id", count="exact") \
            .eq("status", "PROCESSING") \
            .execute()
        return r.count or 0
    except Exception as e:
        log.warning(f"count_processing failed: {e}")
        return 0


def _release_buffered_job() -> bool:
    """Release the oldest BUFFY_BUFFERED job → RENDER_TRIGGERED.
    Returns True if a job was released.
    """
    try:
        # Find oldest buffered job
        r = sb.table("video_automation_jobs") \
            .select("id") \
            .eq("status", "BUFFY_BUFFERED") \
            .order("priority", desc=True) \
            .order("created_at") \
            .limit(1) \
            .execute()
        if not r.data:
            return False

        job_id = r.data[0]["id"]
        now = datetime.now(timezone.utc).isoformat()

        # Atomically update
        result = sb.table("video_automation_jobs") \
            .update({
                "status": "RENDER_TRIGGERED",
                "released_at": now,
                "updated_at": now,
            }) \
            .eq("id", job_id) \
            .eq("status", "BUFFY_BUFFERED") \
            .execute()

        if result.data:
            log.info(f"Released {job_id} from buffer  (lane slot opened)")
            return True
        return False
    except Exception as e:
        log.warning(f"release_buffered_job failed: {e}")
        return False


def _check_stuck_jobs():
    """Flag jobs stuck in buffer > STUCK_THRESHOLD_MIN."""
    try:
        cutoff = int(time.time()) - (STUCK_THRESHOLD_MIN * 60)
        stuck = sb.table("video_automation_jobs") \
            .select("id, topic, buffered_at") \
            .eq("status", "BUFFY_BUFFERED") \
            .lt("buffered_at", datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()) \
            .execute()
        if stuck.data:
            for job in stuck.data:
                log.warning(
                    f"⚠ STUCK {job['id'][:8]} — buffer >{STUCK_THRESHOLD_MIN}min "
                    f"(topic: {job.get('topic', '?')[:60]})"
                )
                # Update with a note
                sb.table("video_automation_jobs") \
                    .update({"error": f"stuck_in_buffer_{STUCK_THRESHOLD_MIN}+min"}) \
                    .eq("id", job["id"]) \
                    .execute()
    except Exception as e:
        log.warning(f"stuck_job_check failed: {e}")


def _log_metrics(active: int, buffered: int, released: int):
    """Write queue metrics to agent_activity table."""
    try:
        sb.table("agent_activity").insert({
            "agent_name": AGENT_NAME,
            "activity_type": "buffy.metrics",
            "summary": json.dumps({
                "active_renders": active,
                "buffered_jobs": buffered,
                "released_this_cycle": released,
                "max_concurrent": MAX_CONCURRENT,
            }),
            "meta": {
                "active": active,
                "buffered": buffered,
                "released": released,
                "max_concurrent": MAX_CONCURRENT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }).execute()
    except Exception as e:
        log.debug(f"metrics_log failed: {e}")


def register_heartbeat():
    """Register/ping in agent_registry table."""
    try:
        sb.table("agent_registry").upsert({
            "agent_name": AGENT_NAME,
            "status": "ACTIVE",
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": [
                "buffy", "buffer", "concurrency", "queue_controller",
            ],
            "task_types": ["buffy.manage"],
        }, on_conflict="agent_name").execute()
    except Exception as e:
        log.debug(f"heartbeat failed: {e}")


# ── Submit API (called by scripts/cron, not the daemon loop) ──────────

def submit_job(
    topic: str = "",
    script_text: str = "",
    voice_provider: str = "",
    source: str = "cli",
    priority: int = 0,
) -> dict:
    """Submit a render job to the buffer queue.

    Buffy decides: if capacity available → RENDER_TRIGGERED,
    otherwise → BUFFY_BUFFERED.

    Returns the job record dict.
    """
    if not voice_provider:
        voice_provider = os.environ.get("BUFFY_DEFAULT_VOICE", "deepgram")
    active = _count_processing()
    now = datetime.now(timezone.utc).isoformat()

    if active >= MAX_CONCURRENT:
        # No capacity — buffer it
        status = "BUFFY_BUFFERED"
        data = {
            "topic": topic,
            "script_text": script_text,
            "voice_provider": voice_provider,
            "source": source,
            "priority": priority,
            "status": status,
            "buffered_at": now,
            "created_at": now,
            "updated_at": now,
        }
        log.info(
            f"Submit: server full ({active}/{MAX_CONCURRENT}) — "
            f"buffering '{topic[:50]}'"
        )
    else:
        # Capacity available — release directly
        status = "RENDER_TRIGGERED"
        data = {
            "topic": topic,
            "script_text": script_text,
            "voice_provider": voice_provider,
            "source": source,
            "priority": priority,
            "status": status,
            "released_at": now,
            "created_at": now,
            "updated_at": now,
        }
        log.info(
            f"Submit: lane open ({active}/{MAX_CONCURRENT}) — "
            f"releasing '{topic[:50]}'"
        )

    try:
        r = sb.table("video_automation_jobs").insert(data).execute()
        if r.data:
            job = r.data[0]
            log.info(f"Job {job['id'][:8]} created → {status}")
            return job
        return {"error": "Insert returned no data"}
    except Exception as e:
        log.error(f"submit_job failed: {e}")
        return {"error": str(e)}


# ── Main loop ────────────────────────────────────────────────────────

async def run_loop():
    """Main daemon loop: poll every 3s, manage buffer, release jobs."""
    log.info(
        f"BUFFY BUFFER ONLINE  "
        f"(max_concurrent={MAX_CONCURRENT}, "
        f"poll={POLL_INTERVAL}s, "
        f"stuck_threshold={STUCK_THRESHOLD_MIN}min)"
    )

    register_heartbeat()
    metrics_interval = 10  # log metrics every 10 cycles
    cycle = 0

    while True:
        try:
            register_heartbeat()

            # 1. Count active renders
            active = _count_processing()
            buffered_count = 0
            released_this = 0

            # 2. Check for stuck jobs (every cycle)
            _check_stuck_jobs()

            # 3. Release buffered jobs if capacity is open
            if active < MAX_CONCURRENT:
                # Keep releasing until capacity fills or buffer is empty
                while True:
                    released = _release_buffered_job()
                    if not released:
                        break
                    released_this += 1
                    active += 1
                    if active >= MAX_CONCURRENT:
                        break

            # Count remaining buffered
            try:
                br = sb.table("video_automation_jobs") \
                    .select("id", count="exact") \
                    .eq("status", "BUFFY_BUFFERED") \
                    .execute()
                buffered_count = br.count or 0
            except Exception:
                pass

            # 4. Log metrics periodically
            cycle += 1
            if cycle % metrics_interval == 0:
                _log_metrics(active, buffered_count, released_this)
                log.info(
                    f"Metrics: {active}/{MAX_CONCURRENT} active, "
                    f"{buffered_count} buffered, "
                    f"{released_this} released this cycle"
                )

        except Exception as e:
            log.error(f"Loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


def main():
    """Entry point for PM2 / direct execution."""
    asyncio.run(run_loop())


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "submit":
        # CLI submission: python3 -m bots.buffy_buffer submit --topic "..."
        import argparse
        p = argparse.ArgumentParser(description="Submit a job to the Buffy buffer")
        p.add_argument("--topic", default="", help="Video topic/hook")
        p.add_argument("--script", default="", help="Full script text")
        p.add_argument("--voice", default=os.environ.get("BUFFY_DEFAULT_VOICE", "deepgram"),
                            choices=["kokoro", "deepgram"])
        p.add_argument("--source", default="cli")
        p.add_argument("--priority", type=int, default=0)
        args = p.parse_args()
        result = submit_job(
            topic=args.topic,
            script_text=args.script,
            voice_provider=args.voice,
            source=args.source,
            priority=args.priority,
        )
        print(json.dumps(result, indent=2, default=str))
    else:
        main()
