"""
EMPIRE V49 · STORM ALERT REVIEW TOOL
=====================================
Daily human-review tool for the NWS storm scraper. Lists NEW alerts
in the local SQLite DB with a clean view for the operator to:
  - see what storm just hit which target zone
  - read the headline + description
  - mark an alert as VERIFIED (real commercial property hit) or
    REJECTED (false positive / not a real warehouse target)
  - add a short note (e.g. "owner: X Roofing, called 2026-06-12")

Run:
  python3 scripts/review_storm_alerts.py                # show NEW
  python3 scripts/review_storm_alerts.py --status all   # show everything
  python3 scripts/review_storm_alerts.py --verify <event_id> --note "..."
  python3 scripts/review_storm_alerts.py --reject <event_id> --note "..."
  python3 scripts/review_storm_alerts.py --verify-all --note "..."  # bulk-verify all NEW
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/root/empire-v49/data/storm_alerts.sqlite")


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}. Run storm_scraper.py first.")
        sys.exit(1)
    return sqlite3.connect(str(DB_PATH))


def show_alerts(status: str = "NEW") -> int:
    conn = get_conn()
    cur = conn.execute("""
        SELECT event_id, event_type, severity, area_desc,
               zip_codes, headline, effective, expires,
               first_seen, last_seen, status, notes
        FROM storm_alerts
        WHERE status = ? OR ? = 'all'
        ORDER BY first_seen DESC
    """, (status, status))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"\nNo alerts with status={status!r}.\n")
        return 0

    print(f"\n{'='*78}")
    print(f"  STORM ALERTS — status={status} — {len(rows)} row(s)")
    print(f"{'='*78}\n")

    for i, (eid, etype, sev, area, zips, headline, eff, exp,
            first, last, st, notes) in enumerate(rows, 1):
        zips_list = json.loads(zips) if zips else []
        print(f"[{i}] {etype}  ·  severity={sev}  ·  status={st}")
        print(f"    event_id : {eid}")
        print(f"    area     : {(area or '')[:120]}")
        print(f"    zips     : {', '.join(zips_list) or '(none)'}")
        print(f"    effective: {eff}")
        print(f"    expires  : {exp}")
        print(f"    first    : {first}")
        print(f"    headline : {(headline or '')[:200]}")
        if notes:
            print(f"    notes    : {notes}")
        print()

    print("-" * 78)
    print("To mark one: --verify <event_id> [--note '...']   or   --reject ...")
    print("-" * 78)
    return len(rows)


def mark_alert(event_id: str, new_status: str, note: str, trigger_hub: bool = True) -> int:
    if new_status not in ("VERIFIED", "REJECTED"):
        print(f"Refusing: status must be VERIFIED or REJECTED, got {new_status!r}")
        return 1
    conn = get_conn()
    cur = conn.execute("SELECT 1 FROM storm_alerts WHERE event_id = ?", (event_id,))
    if not cur.fetchone():
        print(f"No alert with event_id={event_id!r}")
        conn.close()
        return 1
    if note:
        conn.execute(
            "UPDATE storm_alerts SET status = ?, notes = ? WHERE event_id = ?",
            (new_status, note, event_id),
        )
    else:
        conn.execute(
            "UPDATE storm_alerts SET status = ? WHERE event_id = ?",
            (new_status, event_id),
        )
    conn.commit()
    conn.close()
    print(f"Marked {event_id} as {new_status}.")

    # If VERIFIED, trigger the hub to process this alert through
    # the full strike engine pipeline (scout -> satellite -> strike_log).
    if new_status == "VERIFIED" and trigger_hub:
        _trigger_hub_pipeline(event_id)

    return 0


def verify_all(note: str = "") -> int:
    """Bulk-verify all NEW alerts at once. Marks each as VERIFIED and
    triggers the hub pipeline once for the batch."""
    conn = get_conn()
    cur = conn.execute(
        "SELECT event_id FROM storm_alerts WHERE status = 'NEW' ORDER BY first_seen DESC"
    )
    ids = [row[0] for row in cur.fetchall()]

    if not ids:
        conn.close()
        print("No NEW alerts to verify.")
        return 0

    print(f"\nBulk-verifying {len(ids)} NEW alert(s) in a single transaction...\n")

    conn.execute("BEGIN")
    for eid in ids:
        conn.execute(
            "UPDATE storm_alerts SET status = 'VERIFIED', notes = ? WHERE event_id = ?",
            (note, eid),
        )
    conn.commit()
    conn.close()

    print(f"{len(ids)} alert(s) verified.\n")

    # Trigger hub once for the full batch (single POST, idempotent)
    _trigger_hub_pipeline("batch")
    return 0


def _trigger_hub_pipeline(event_id: str) -> None:
    """POST to the hub's /api/v1/storm/process-sqlite endpoint to push
    the newly VERIFIED alert into the strike engine pipeline."""
    import urllib.request
    import os
    hub_url = os.environ.get(
        "EMPIRE_HUB_URL",
        "http://localhost:8001",
    ).rstrip("/")
    hub_token = os.environ.get("HUB_TOKEN", "dev-token-insecure")
    endpoint = f"{hub_url}/api/v1/storm/process-sqlite"
    try:
        req = urllib.request.Request(
            endpoint,
            method="POST",
            headers={
                "Authorization": f"Bearer {hub_token}",
                "Content-Type": "application/json",
            },
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                print(f"  -> Hub notified: strike pipeline triggered for {event_id}")
            else:
                print(f"  -> Hub returned {resp.status} (pipeline may not have triggered)")
    except urllib.error.HTTPError as e:
        # Hub may not be running locally — that's OK, the tick() poll will
        # pick up VERIFIED alerts on its next cycle.
        print(f"  -> Hub unreachable (HTTP {e.code}): pipeline will pick up on next poll cycle")
    except Exception as e:
        print(f"  -> Hub unreachable ({e}): pipeline will pick up on next poll cycle")


def main() -> int:
    p = argparse.ArgumentParser(description="Review NWS storm alerts")
    p.add_argument("--status", default="NEW",
                   help="Filter by status: NEW | VERIFIED | REJECTED | all (default: NEW)")
    p.add_argument("--verify", metavar="EVENT_ID", help="Mark alert as VERIFIED")
    p.add_argument("--verify-all", action="store_true",
                   help="Bulk-verify ALL NEW alerts at once")
    p.add_argument("--reject", metavar="EVENT_ID", help="Mark alert as REJECTED")
    p.add_argument("--note", help="Optional note to attach to --verify/--reject/--verify-all")
    args = p.parse_args()

    if args.verify:
        return mark_alert(args.verify, "VERIFIED", args.note or "")
    if args.verify_all:
        return verify_all(args.note or "")
    if args.reject:
        return mark_alert(args.reject, "REJECTED", args.note or "")

    n = show_alerts(args.status)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
