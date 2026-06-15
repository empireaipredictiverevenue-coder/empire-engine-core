"""
Empire AI · A/B Monitor
======================

Runs the A/B reply-rate comparison every 6h and writes the result to
agent_activity so the operator SPA can chart it. Real organic replies
arrive hours-to-days after SMS sends, so the signal builds up over
time. This monitor is the polling arm — the dispatcher does the firing.
"""
import os, sys, json
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path("/root/empire-v49").resolve()))

from supabase import create_client
import uuid
import httpx

AGENT_NAME = "ab_monitor"
HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8000")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "")


def run_once() -> dict:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    started_at = datetime.now(timezone.utc)

    # pull the latest A/B result via the hub endpoint
    try:
        r = httpx.get(
            f"{HUB_URL}/api/v1/ab-test/results?days=7",
            headers={"Authorization": f"Bearer {HUB_TOKEN}"},
            timeout=10,
        )
        ab = r.json() if r.status_code == 200 else {}
    except Exception as e:
        ab = {"error": str(e)}

    a = ab.get("cohort_a", {})
    b = ab.get("cohort_b", {})
    n_replies = ab.get("n_replies", 0)
    winner = ab.get("winner", "no_data")

    summary = (
        f"AB-test: A={a.get('name')}({a.get('reply_rate_pct')}% reply, {a.get('replied')}/{a.get('terminal')}) "
        f"B={b.get('name')}({b.get('reply_rate_pct')}% reply, {b.get('replied')}/{b.get('terminal')}) "
        f"winner={winner} n_replies={n_replies}"
    )

    # log to agent_activity for the operator SPA
    sb.table("agent_activity").insert({
        "agent_name": AGENT_NAME,
        "run_id": str(uuid.uuid4()),
        "started_at": started_at.isoformat(),
        "finished_at": started_at.isoformat(),
        "status": "ok",
        "rows_seen": 0,
        "rows_processed": n_replies,
        "rows_errored": 0,
        "error": None,
        "summary": summary[:500],
    }).execute()
    print(summary)
    return {"status": "ok", "summary": summary, "ab": ab}


if __name__ == "__main__":
    run_once()
