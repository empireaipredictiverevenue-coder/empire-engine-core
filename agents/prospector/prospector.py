"""
Empire AI · Predictive Revenue
Prospector Agent (thin wrapper)
================================

Thin wrapper around `bots/prospector.py` (the URL/contractor discovery
tool) that:
  1. Calls prospector across all configured metros + niches
  2. Logs the run to agent_activity (so the kanban + dashboards can see it)
  3. Updates agent_config.last_run_at

The underlying bots/prospector.py writes to the `prospects` table.
agents/prospector_bridge reads from `prospects` and writes to `contractors`.
agents/contractor_outreach recruits from `contractors` into SMS sequences.

This is the upstream half of the contractor-acquisition chain. Without it,
prospector_bridge has nothing to bridge and contractor_outreach has nothing
to recruit.

Usage:
    python3 -m agents.prospector           # one run, exits
    python3 -m agents.prospector --dry-run # score and report but don't write
    python3 -m agents.prospector --status  # last run + stats
"""
import os
import sys
import json
import uuid
import logging
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.prospector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "prospector"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True}
    row = r.data[0]
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
    }


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_errored=0,
                  error=None, summary=None):
    finished_at = datetime.now(timezone.utc).isoformat()
    sb.table("agent_activity").insert({
        "agent_name": AGENT_NAME,
        "run_id": str(run_id),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at,
        "status": status,
        "rows_seen": rows_seen,
        "rows_processed": rows_processed,
        "rows_errored": rows_errored,
        "error": error,
        "summary": summary,
    }).execute()
    return finished_at


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


async def _run_prospector(dry_run: bool) -> dict:
    """Call bots/prospector.py run_multi() and return its summary dict."""
    from bots.prospector import run_multi
    return await run_multi(dry_run=dry_run)


def run_once(dry_run_override=None) -> dict:
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override

    if not cfg["enabled"]:
        msg = "agent disabled in agent_config — skipping"
        log.info(msg)
        _log_activity(sb, run_id, started_at, "skipped", summary=msg)
        return {"status": "skipped", "reason": msg}

    try:
        results = asyncio.run(_run_prospector(dry_run=dry_run))
        summary = (
            f"[{'DRY-RUN' if dry_run else 'LIVE'}] "
            f"found={results.get('total_found', 0)} "
            f"saved={results.get('total_saved', 0)} "
            f"metros={results.get('metros_scanned', 0)} "
            f"niches={results.get('niches_scanned', 0)}"
        )
        log.info(summary)
        finished_at = _log_activity(
            sb, run_id, started_at, "ok",
            rows_seen=results.get("total_found", 0),
            rows_processed=results.get("total_saved", 0),
            summary=summary,
        )
        _update_config(sb, "ok", finished_at)
        return {"status": "ok", **results}
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log.exception("prospector run failed")
        finished_at = _log_activity(
            sb, run_id, started_at, "error",
            error=err,
            summary=f"prospector failed: {err[:120]}",
        )
        _update_config(sb, "error", finished_at)
        return {"status": "error", "error": err}


def show_status():
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        print(f"agent:        {AGENT_NAME}")
        print(f"enabled:      {row.get('enabled')}")
        print(f"dry_run:      {row.get('dry_run')}")
        print(f"last_run_at:  {row.get('last_run_at')}")
        print(f"last_status:  {row.get('last_run_status')}")
    else:
        print(f"agent:        {AGENT_NAME}  (no agent_config row yet)")
    r2 = sb.table("agent_activity").select("started_at,status,rows_seen,rows_processed,summary").eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("recent runs:")
    for row in r2.data:
        sa = (row.get("started_at") or "")[:19]
        st = row.get("status") or ""
        rs = row.get("rows_seen", 0)
        rp = row.get("rows_processed", 0)
        sm = (row.get("summary") or "")[:80]
        print(f"  {sa}  {st:10}  seen={rs}  proc={rp}  {sm}")


def main():
    p = argparse.ArgumentParser(description="Empire AI Prospector Agent")
    p.add_argument("--dry-run", action="store_true", help="score and report, don't write")
    p.add_argument("--status", action="store_true", help="print last run + stats")
    args = p.parse_args()
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
