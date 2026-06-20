"""
Empire AI · Predictive Revenue
Warp Scout (Storm Risk Predictor) Agent
========================================

Thin wrapper around bots/storm_predictor.py that:
  1. Calls storm_predictor.assess() to get per-metro storm risk for days 1-3
  2. Writes per-run rows to storm_risk_log (history table)
  3. Logs the run to agent_activity
  4. Updates agent_config.last_run_at / last_run_status
  5. Pings Telegram if any metro goes to Slight or higher (so we can
     pre-warm lead-gen for high-risk metros)

The original bots/storm_predictor.py was a `while True` daemon with
single-row upsert storage. This wrapper turns it into a cron-friendly
one-shot with proper history and alerts.

Cron: every 6h on :50 (offset from other agents)

Usage:
    python3 -m agents.warp_scout
    python3 -m agents.warp_scout --dry-run
    python3 -m agents.warp_scout --status
"""
import os
import sys
import json
import uuid
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client
from agents.event_emitter import emit_agent_event

log = logging.getLogger("empire.warp_scout")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "warp_scout"

# Risk levels that warrant a Telegram alert (Slight or higher)
ALERT_THRESHOLD_RANK = 4  # Slight=4 in bots.storm_predictor.RISK_RANK
DEFAULT_INTERVAL_SECONDS = 7200  # 2 hours


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "alert_below_rank": ALERT_THRESHOLD_RANK}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "alert_below_rank": cfg.get("alert_below_rank", ALERT_THRESHOLD_RANK),
    }


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_errored=0,
                  error=None, summary=None):
    return emit_agent_event(
        sb=sb, agent_name=AGENT_NAME, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_errored=rows_errored, error=error, summary=summary,
    )


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


def _write_risk_log(sb, forecasts, run_id):
    """Write per-forecast rows to storm_risk_log."""
    if not forecasts:
        return 0
    rows = [
        {
            "source":     AGENT_NAME,
            "run_id":     str(run_id),
            "metro":      f.get("metro"),
            "day":        f.get("day"),
            "risk_level": f.get("risk_level"),
            "risk_rank":  f.get("risk_rank"),
            "lat":        f.get("lat"),
            "lon":        f.get("lon"),
        }
        for f in forecasts
    ]
    sb.table("storm_risk_log").insert(rows).execute()
    return len(rows)


def _ping_telegram(message: str) -> bool:
    """Best-effort Telegram ping via ntfy (the project's existing channel)."""
    ntfy_url = os.getenv("NTFY_URL", "")
    ntfy_topic = os.getenv("NTFY_TOPIC", "")
    if not ntfy_url or not ntfy_topic:
        return False
    try:
        import httpx
        httpx.post(
            f"{ntfy_url.rstrip('/')}/{ntfy_topic}",
            data=message.encode("utf-8"),
            headers={"Title": "Warp Scout: storm risk detected", "Priority": "high"},
            timeout=10,
        )
        return True
    except Exception as e:
        log.warning(f"telegram/ntfy ping failed: {e}")
        return False


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
        from bots.storm_predictor import assess
        forecasts = assess()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log.exception("assess() failed")
        finished_at = _log_activity(
            sb, run_id, started_at, "error", error=err,
            summary=f"assess() failed: {err[:120]}",
        )
        _update_config(sb, "error", finished_at)
        return {"status": "error", "error": err}

    rows_written = 0
    if not dry_run and forecasts:
        rows_written = _write_risk_log(sb, forecasts, run_id)

    # Alert on any Slight+ risk
    alertable = [f for f in forecasts if f.get("risk_rank", 0) >= cfg["alert_below_rank"]]
    telegram_pinged = False
    if alertable and not dry_run:
        msg = f"Storm risk detected for {len(alertable)} metro(s):\n"
        for f in alertable[:5]:
            msg += f"  - {f['metro']} (day {f['day']}): {f['risk_level']}\n"
        telegram_pinged = _ping_telegram(msg)

    summary = (
        f"[{'DRY-RUN' if dry_run else 'LIVE'}] "
        f"forecasts={len(forecasts)} "
        f"written={rows_written} "
        f"alertable={len(alertable)} "
        f"telegram_pinged={telegram_pinged}"
    )
    log.info(summary)
    finished_at = _log_activity(
        sb, run_id, started_at, "ok",
        rows_seen=len(forecasts),
        rows_processed=rows_written,
        summary=summary[:500],
    )
    _update_config(sb, "ok", finished_at)
    return {
        "status": "ok",
        "forecasts": forecasts,
        "rows_written": rows_written,
        "alertable": alertable,
        "telegram_pinged": telegram_pinged,
    }


# ── Loop mode ───────────────────────────────────────────────────────────

async def run_loop(interval_seconds: Optional[int] = None):
    """Run warp_scout.run_once() in an infinite loop."""
    delay = interval_seconds or DEFAULT_INTERVAL_SECONDS
    log.info(f"[{AGENT_NAME}] running in loop mode (interval={delay}s)")
    while True:
        started = datetime.now(timezone.utc)
        try:
            result = run_once(dry_run_override=None)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            log.info(f"[{AGENT_NAME}] cycle done in {elapsed:.1f}s — status={result.get('status')}")
        except Exception as e:
            log.exception(f"[{AGENT_NAME}] cycle failed: {e}")
        slept = (datetime.now(timezone.utc) - started).total_seconds()
        await asyncio.sleep(max(10, delay - slept))


def show_status():
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        cfg = row.get("config_json") or {}
        print(f"agent:        {AGENT_NAME}")
        print(f"enabled:      {row.get('enabled')}")
        print(f"dry_run:      {row.get('dry_run')}")
        print(f"alert_below:  rank>={cfg.get('alert_below_rank', ALERT_THRESHOLD_RANK)} (Slight=4)")
        print(f"last_run_at:  {row.get('last_run_at')}")
        print(f"last_status:  {row.get('last_run_status')}")
    else:
        print(f"agent:        {AGENT_NAME}  (no agent_config row yet)")
    r2 = sb.table("agent_activity").select("started_at,status,rows_seen,rows_processed,summary").eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("recent runs:")
    for row in r2.data:
        sa = (row.get("started_at") or "")[:19]
        st = (row.get("status") or "")
        rs = row.get("rows_seen", 0)
        rp = row.get("rows_processed", 0)
        sm = (row.get("summary") or "")[:80]
        print(f"  {sa}  {st:10}  seen={rs}  written={rp}  {sm}")
    r3 = sb.table("storm_risk_log").select("created_at,metro,day,risk_level,risk_rank").order("created_at", desc=True).limit(8).execute()
    print("recent risk rows:")
    for row in r3.data:
        ca = (row.get("created_at") or "")[:19]
        m = (row.get("metro") or "")
        d = row.get("day", 0)
        rl = (row.get("risk_level") or "")
        rr = row.get("risk_rank", 0)
        print(f"  {ca}  {m:18}  day={d}  {rl:12}  rank={rr}")


def main():
    p = argparse.ArgumentParser(description="Empire AI Warp Scout (storm risk predictor)")
    p.add_argument("--dry-run", action="store_true", help="score and report, don't write")
    p.add_argument("--status", action="store_true", help="print last run + stats")
    p.add_argument("--loop", action="store_true", help="run in loop mode (replaces cron)")
    p.add_argument("--interval", type=int, default=None,
                   help=f"loop interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})")
    args = p.parse_args()
    if args.loop:
        asyncio.run(run_loop(interval_seconds=args.interval))
        return
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
