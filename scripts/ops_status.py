"""
EMPIRE V49 · OPS STATUS (1-page operator view)
==============================================
Single command for "what's happening right now" across the legal
lane pipeline. Designed to be the one page you look at each
morning to know if the lane is healthy.

Prints:
  - 5 legal sub_niches: how many active buyers, how many have a
    real destination_phone, last call time, calls attempted /
    accepted / rejected last 24h
  - Storm lane: alerts in the local SQLite DB by status
  - Migration state: any pending migrations

Reads from:
  - supabase buyers table (legal buyers)
  - supabase call_ledger (call outcomes, if the table exists)
  - local SQLite storm_alerts.db
  - local filesystem (migration state via run_migrations.py --status)

Outputs plain text (no rich formatting) so it works in any terminal
or can be piped into a log file / sent over a chat.

Usage:
  python3 scripts/ops_status.py                # default, last 24h
  python3 scripts/ops_status.py --since 7d     # last 7 days
  python3 scripts/ops_status.py --json         # machine-readable output
  python3 scripts/ops_status.py --watch        # re-print every 30s
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Manual .env loader (sniper_env may not have python-dotenv).
ENV_PATH = "/root/.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _v = _v.strip()
            if (_v.startswith('"') and _v.endswith('"')) or (_v.startswith("'") and _v.endswith("'")):
                _v = _v[1:-1]
            os.environ[_k.strip()] = _v


LEGAL_SUB_NICHES = [
    "Pharma Liability", "Medical Device", "Consumer Product", "Class Action", "Mass Tort",
]


# ── DATA SOURCES ────────────────────────────────────────────────────────
def _legal_buyers():
    """Return list of active Legal buyers (one per sub_niche, ideally)."""
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    res = (
        sb.table("buyers")
        .select("id, buyer_name, sub_niche, destination_phone, is_active, "
                "calls_today, calls_accepted, calls_offered, updated_at")
        .eq("niche", "Legal")
        .eq("is_active", True)
        .order("sub_niche")
        .execute()
    )
    return res.data


def _call_ledger_counts(since_iso: str):
    """Return {sub_niche: {attempted, accepted, rejected}} from call_logs
    (the actual table name in supabase; call_ledger does not exist).
    Returns {} if the query fails or env not set.
    """
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        return {}
    try:
        from supabase import create_client
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        sample = sb.table("call_logs").select("*").limit(1).execute()
        if not sample.data:
            return {}
        cols = list(sample.data[0].keys())
        sub_niche_col = "sub_niche" if "sub_niche" in cols else (
            "niche" if "niche" in cols else None
        )
        status_col = "status" if "status" in cols else None
        ts_col = "created_at" if "created_at" in cols else (
            "ts" if "ts" in cols else None
        )
        if not status_col or not ts_col:
            return {}
        select_cols = f"{status_col},{sub_niche_col},{ts_col}" if sub_niche_col else f"{status_col},{ts_col}"
        res = (
            sb.table("call_logs")
            .select(select_cols)
            .gte(ts_col, since_iso)
            .execute()
        )
        from collections import Counter
        out = {}
        for r in res.data:
            sn = r.get(sub_niche_col) if sub_niche_col else "_all"
            st = (r.get(status_col) or "").lower()
            bucket = out.setdefault(sn, {"attempted": 0, "accepted": 0, "rejected": 0})
            bucket["attempted"] += 1
            if st in ("accepted", "completed", "ok", "success"):
                bucket["accepted"] += 1
            elif st in ("rejected", "blocked", "no-answer", "failed", "compliance_block", "compliance"):
                bucket["rejected"] += 1
        return out
    except Exception as e:
        return {"_error": str(e)}


def _storm_db_counts():
    """Return {NEW, VERIFIED, REJECTED} counts from the local SQLite."""
    path = Path("/root/empire-v49/data/storm_alerts.sqlite")
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(str(path))
        cur = conn.execute("SELECT status, count(*) FROM storm_alerts GROUP BY status")
        counts = {row[0] or "NULL": row[1] for row in cur.fetchall()}
        conn.close()
        return counts
    except Exception:
        return None


# ── FORMATTING ──────────────────────────────────────────────────────────
def _format_human(since_label, legal_buyers, call_counts, storm_counts):
    lines = []
    lines.append(f"EMPIRE V49 · OPS STATUS  ·  window: last {since_label}")
    lines.append(f"generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 78)
    lines.append("")

    # ── Legal lane ──────────────────────────────────────────────────
    lines.append("LEGAL LANE")
    lines.append("-" * 78)
    lines.append(f"  {'sub_niche':<20} {'buyer':<35} {'phone':<6} {'att':<4} {'acc':<4} {'rej':<4}")
    by_sub = {b.get("sub_niche"): b for b in (legal_buyers or [])}
    for sn in LEGAL_SUB_NICHES:
        b = by_sub.get(sn)
        if b is None:
            lines.append(f"  {sn:<20} {'(no active buyer)':<35} {'-':<6} {'-':<4} {'-':<4} {'-':<4}")
            continue
        phone = "yes" if b.get("destination_phone") else "no"
        c = call_counts.get(sn, {}) if isinstance(call_counts, dict) else {}
        att = c.get("attempted", 0)
        acc = c.get("accepted", 0)
        rej = c.get("rejected", 0)
        # Also show the all-time counter from the buyer row if no call_ledger data.
        if not c:
            att = b.get("calls_offered", 0) or 0
            acc = b.get("calls_accepted", 0) or 0
            rej = att - acc
        lines.append(f"  {sn:<20} {b.get('buyer_name',''):<35} {phone:<6} {att:<4} {acc:<4} {rej:<4}")
    lines.append("")

    if isinstance(call_counts, dict) and call_counts.get("_error"):
        lines.append(f"  [call_ledger query failed: {call_counts['_error']}]")
        lines.append("  [falling back to buyer-row counters shown above]")
        lines.append("")

    # ── Storm lane ──────────────────────────────────────────────────
    lines.append("STORM LANE")
    lines.append("-" * 78)
    if storm_counts is None:
        lines.append("  (no SQLite DB at /root/empire-v49/data/storm_alerts.sqlite)")
    else:
        lines.append(f"  alerts by status: {storm_counts}")
    lines.append("")

    # ── Migration state ─────────────────────────────────────────────
    lines.append("MIGRATIONS")
    lines.append("-" * 78)
    lines.append("  (see: python3 scripts/run_migrations.py --status)")
    lines.append("")

    return "\n".join(lines)


def _format_json(legal_buyers, call_counts, storm_counts):
    return json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "legal_buyers": legal_buyers or [],
        "call_counts_last_window": call_counts or {},
        "storm_alerts_by_status": storm_counts,
    }, indent=2, default=str)


# ── MAIN ────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Empire V49 one-page ops status")
    p.add_argument("--since", default="24h", help="Time window (e.g. 24h, 7d, 1h)")
    p.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    p.add_argument("--watch", action="store_true", help="Re-print every 30s")
    args = p.parse_args()

    # Parse --since to a timedelta
    unit = args.since[-1]
    n = int(args.since[:-1])
    delta = {"h": timedelta(hours=n), "d": timedelta(days=n), "m": timedelta(minutes=n)}.get(unit, timedelta(hours=24))
    since_iso = (datetime.now(timezone.utc) - delta).isoformat()

    while True:
        legal_buyers = _legal_buyers()
        call_counts = _call_ledger_counts(since_iso)
        storm_counts = _storm_db_counts()

        if args.json:
            print(_format_json(legal_buyers, call_counts, storm_counts))
        else:
            print(_format_human(args.since, legal_buyers, call_counts, storm_counts))

        if not args.watch:
            return 0
        time.sleep(30)
        # Clear screen for next iteration (works in most terminals)
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
