#!/usr/bin/env python3
"""
EMPIRE V49 · PULSE REFRESH CRON
================================
Standalone PM2-managed process that refreshes the pulse_rollup_hourly
materialized view every N seconds (default 300 = 5 min).

Designed as a backup/redundant cron to the hub's built-in _pulse_refresh_loop.
If the hub is down for any reason, this keeps the pulse data fresh.

PM2 usage:
    pm2 start scripts/pulse_refresh_cron.py --name empire-pulse-cron \
        --interpreter python3 \
        -- --interval 300

Or with PM2 ecosystem:
    {
      name: "empire-pulse-cron",
      script: "scripts/pulse_refresh_cron.py",
      interpreter: "python3",
      args: "--interval 300",
      env: {
        PULSE_REFRESH_INTERVAL_SEC: "300"
      }
    }
"""

import os
import sys
import time
import signal
import argparse
import logging
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("pulse.cron")


def _handle_sigterm(signum, frame):
    log.info("Received SIGTERM, shutting down")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Pulse materialized view refresh cron")
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("PULSE_REFRESH_INTERVAL_SEC", "300")),
        help="Refresh interval in seconds (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for testing / one-off refreshes)",
    )
    args = parser.parse_args()

    interval = args.interval
    if interval < 10:
        log.warning(f"Interval {interval}s is very short — minimum recommended is 60s")
        interval = max(interval, 10)

    # ── Connect to Supabase ──────────────────────────────────────
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not supabase_key:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        sys.exit(1)

    db = create_client(supabase_url, supabase_key)
    log.info(f"Pulse refresh cron starting (interval={interval}s)")

    if args.once:
        _refresh(db)
        log.info("One-off refresh complete")
        return

    # ── Continuous loop ──────────────────────────────────────────
    log.info(f"Continuous mode: refreshing every {interval}s")
    while True:
        try:
            _refresh(db)
        except Exception as e:
            log.error(f"Refresh failed: {e}")
        time.sleep(interval)


def _refresh(db):
    """Execute the materialized view refresh via Supabase RPC."""
    try:
        rpc_fn = "refresh_pulse_rollup"
        result = db.rpc(rpc_fn).execute()

        # Verify — check row count
        count_res = db.table("pulse_rollup_hourly") \
            .select("revenue", count="exact") \
            .limit(1) \
            .execute()
        row_count = getattr(count_res, "count", len(count_res.data or []))

        now = datetime.now(timezone.utc).isoformat()
        log.info(f"Refreshed OK · {row_count} rows in view · {now}")
    except Exception as e:
        # Fallback: try direct REFRESH via SQL if RPC fails
        log.warning(f"RPC refresh failed ({e}), trying direct SQL...")
        try:
            supabase_url = os.environ.get("SUPABASE_URL", "")
            supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            import httpx

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{supabase_url}/rest/v1/rpc/refresh_pulse_rollup",
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code < 300:
                    log.info(f"Direct SQL refresh OK (HTTP {resp.status_code})")
                else:
                    log.warning(f"Direct SQL refresh returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e2:
            log.error(f"Direct SQL refresh also failed: {e2}")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    main()
