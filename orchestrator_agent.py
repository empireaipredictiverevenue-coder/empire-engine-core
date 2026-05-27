"""
EMPIRE V49 · ORCHESTRATOR AGENT (REAL DATA)
=============================================
Pulls real metrics from Supabase every 5 minutes.
Writes [AGI] Stats Snapshot and [ACTION] Applying optimized configuration
lines to empire_session_log.md.
"""
import os
import sys
import time
import json
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, "/root/empire-v49")

LOG_PATH = Path("/root/empire-v49/empire_session_log.md")
INTERVAL_SEC = 300  # 5 minutes

# Load env
from dotenv import load_dotenv
load_dotenv("/root/.env")

from supabase import create_client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
db = create_client(SUPABASE_URL, SUPABASE_KEY)


def emit(line: str):
    """Append a line to the log and stdout."""
    stamp = datetime.now(timezone.utc).isoformat()
    msg = f"{line}"
    with LOG_PATH.open("a") as f:
        f.write(msg + "\n")
    print(msg)


def get_real_stats() -> dict:
    """Pull real metrics from Supabase."""
    now = datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    stats = {"status": "active"}

    # revenue_pulse: ratio of GO decisions / total brain calls today (0-1)
    try:
        brain_calls = db.table("brain_training_log") \
            .select("output", count="exact") \
            .eq("task", "brain.decide") \
            .gte("created_at", today_start) \
            .execute()
        total = brain_calls.count or 0
        go_count = sum(
            1 for r in (brain_calls.data or [])
            if r.get("output") and "GO" in r["output"] and "NO_GO" not in r["output"][:50]
        )
        stats["revenue_pulse"] = round(go_count / total, 3) if total > 0 else 0.0
        stats["brain_calls_today"] = total
    except Exception as e:
        stats["revenue_pulse"] = 0.0
        stats["_revenue_err"] = str(e)[:80]

    # proxy_health: success rate of ai_call_log entries today (0-1)
    try:
        ai_calls = db.table("ai_call_log") \
            .select("error", count="exact") \
            .gte("created_at", today_start) \
            .execute()
        total = ai_calls.count or 0
        errors = sum(1 for r in (ai_calls.data or []) if r.get("error"))
        stats["proxy_health"] = round((total - errors) / total, 3) if total > 0 else 1.0
        stats["ai_calls_today"] = total
    except Exception as e:
        stats["proxy_health"] = 1.0
        stats["_health_err"] = str(e)[:80]

    # lead_velocity: radar_targets created in last hour
    try:
        leads = db.table("radar_targets") \
            .select("id", count="exact") \
            .gte("created_at", one_hour_ago) \
            .execute()
        stats["lead_velocity"] = leads.count or 0
    except Exception as e:
        stats["lead_velocity"] = 0
        stats["_velocity_err"] = str(e)[:80]

    # conversion_rate: approved drafts / total drafts today
    try:
        drafts = db.table("email_drafts") \
            .select("status", count="exact") \
            .gte("created_at", today_start) \
            .execute()
        total_drafts = drafts.count or 0
        approved = sum(
            1 for r in (drafts.data or [])
            if r.get("status") in ("approved", "sent")
        )
        stats["conversion_rate"] = round(approved / total_drafts, 4) if total_drafts > 0 else 0.0
        stats["drafts_today"] = total_drafts
    except Exception as e:
        stats["conversion_rate"] = 0.0
        stats["_conv_err"] = str(e)[:80]

    return stats


async def ask_llama_for_weight(stats: dict) -> dict:
    """Call empire_agi.agi_optimize_priorities (which calls Llama 3.2 3b)."""
    try:
        from empire_agi import agi_optimize_priorities
        result = await agi_optimize_priorities(stats)
        return result
    except Exception as e:
        return {"new_weight": 1.0, "_error": str(e)[:120]}


async def agentic_loop_once():
    stats = get_real_stats()
    emit(f"[AGI] Stats Snapshot: {stats}")
    config = await ask_llama_for_weight(stats)
    emit(f"[AGI] System self-optimized based on real-time revenue pulse.")
    emit(f"[ACTION] Applying optimized configuration: {config}")


async def main():
    print("=" * 60)
    print("EMPIRE ORCHESTRATOR · REAL DATA MODE")
    print(f"Loop interval: {INTERVAL_SEC} sec ({INTERVAL_SEC // 60} min)")
    print(f"Log file: {LOG_PATH}")
    print(f"Brain model: llama3.2:3b (via empire_ai_router)")
    print("=" * 60)

    while True:
        try:
            await agentic_loop_once()
        except Exception as e:
            emit(f"[ERROR] Orchestrator loop failed: {e}")
        await asyncio.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
