"""
Empire AI · Predictive Revenue
Lead Scanner Agent
==========================

First of three agents in the lead-gen pipeline.

Reads fresh radar_targets (status=active, created since last run), copies
qualifying rows into enriched_leads with status=pending_enrichment.

Idempotent on (radar_target_id) — re-running is safe.

Usage:
    python3 -m agents.lead_scanner           # one run, exits
    python3 -m agents.lead_scanner --dry-run # same as config dry_run=True
    python3 -m agents.lead_scanner --status  # print last run + stats
"""
import os
import sys
import json
import uuid
import logging
import argparse
from datetime import datetime, timezone, timedelta
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

log = logging.getLogger("empire.lead_scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _read_config(sb, default_max=100, default_lookback=2):
    """Read the agent's config row. Returns dict with sensible defaults."""
    r = sb.table("agent_config").select("*").eq("agent_name", "lead_scanner").limit(1).execute()
    if not r.data:
        return {
            "enabled": True,
            "dry_run": True,
            "max_per_run": default_max,
            "lookback_hours": default_lookback,
        }
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", default_max),
        "lookback_hours": cfg.get("lookback_hours", default_lookback),
    }


def _log_activity(sb, agent_name, run_id, started_at, status, rows_seen=0,
                  rows_processed=0, rows_errored=0, error=None, summary=None):
    finished_at = datetime.now(timezone.utc).isoformat()
    sb.table("agent_activity").insert({
        "agent_name": agent_name,
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


def _update_config(sb, agent_name, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", agent_name).execute()


def run() -> dict:
    """One scanner run. Returns a summary dict. Never raises on per-row failures."""
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)

    if not cfg["enabled"]:
        _log_activity(sb, "lead_scanner", run_id, started_at, "skipped_disabled",
                      summary="disabled in agent_config")
        _update_config(sb, "lead_scanner", "skipped_disabled", datetime.now(timezone.utc).isoformat())
        return {"status": "skipped_disabled", "rows_processed": 0}

    # 1) Find radar_targets to process:
    #    - status=active
    #    - created in the last N hours (or since last_run_at if it's been longer)
    #    - not already in enriched_leads
    lookback = timedelta(hours=cfg["lookback_hours"])
    since = (started_at - lookback).isoformat()
    rt_res = (sb.table("radar_targets")
                .select("id, address, city, state, phone, email, warehouse_name, asset_value, status, created_at, meta, source")
                .eq("status", "active")
                .order("created_at", desc=False)
                .limit(cfg["max_per_run"] * 2)  # 2x headroom for the dedup filter
                .execute())
    # Filter to the lookback window in Python (so we can fall back to "all-time" if empty)
    candidates = [r for r in (rt_res.data or []) if r.get("created_at", "") >= since]
    in_fallback = False
    if not candidates:
        # First-run / backfill mode: no recent ones. Re-query for the NEWEST
        # active radar_targets (the previous query was order=asc, so we got the
        # oldest first — that meant dedup ate them all because they were
        # already in enriched_leads).
        in_fallback = True
        log.info(f"scanner: no radar_targets in last {cfg['lookback_hours']}h — falling back to all-time, NEWEST first")
        fb_res = (sb.table("radar_targets")
                    .select("id, address, city, state, phone, email, warehouse_name, asset_value, status, created_at, meta, source")
                    .eq("status", "active")
                    .order("created_at", desc=True)   # newest first in fallback
                    .limit(cfg["max_per_run"] * 2)
                    .execute())
        candidates = fb_res.data or []
    log.info(f"scanner: {len(candidates)} candidate radar_targets since {since}")

    # 2) Filter out ones we already have. Chunk the .in_() query so we
    # don't blow up the URL on big backlogs (supabase returns invalid_json
    # when the .in_() list is too long).
    if candidates:
        candidate_ids = [r["id"] for r in candidates]
        CHUNK = 200
        already: set = set()
        for i in range(0, len(candidate_ids), CHUNK):
            chunk = candidate_ids[i:i + CHUNK]
            existing_res = (sb.table("enriched_leads")
                              .select("radar_target_id")
                              .in_("radar_target_id", chunk)
                              .execute())
            already.update(r["radar_target_id"] for r in (existing_res.data or []))
        candidates = [r for r in candidates if r["id"] not in already]
        log.info(f"scanner: {len(candidates)} after dedup against enriched_leads")

    candidates = candidates[:cfg["max_per_run"]]

    # 3) Copy into enriched_leads
    rows_seen = len(candidates)
    rows_processed = 0
    rows_errored = 0
    error_msgs = []

    for rt in candidates:
        try:
            # best-effort city/state extraction from address if missing.
            # Real-world addresses from Google Places are comma-separated:
            #   "<street>, <city>, <ST> <zip>, <country>"
            # Empire-pipeline rows sometimes have just a business name in
            # the address column — those can't be parsed, leave blank.
            city = rt.get("city")
            state = rt.get("state")
            meta = rt.get("meta") or {}
            raw = meta.get("raw") or {}

            # prefer Google Places structured data if available
            if not city and raw.get("city"):
                city = raw.get("city")
            if not state and raw.get("state"):
                state = raw.get("state")

            # fall back to parsing the comma-separated address
            if (not city or not state) and rt.get("address"):
                addr = (rt.get("address") or "").strip()
                # The address is comma-separated. Split on commas.
                parts = [p.strip() for p in addr.split(",") if p.strip()]
                if len(parts) >= 2:
                    # Try: parts[-1] = country, parts[-2] = "ST zip", parts[-3] = city
                    if not state and len(parts) >= 2:
                        # second-to-last usually has "<ST> <zip>" or just "<ST>"
                        st_zip = parts[-2] if not (len(parts) >= 3 and parts[-1] in ("USA", "US", "United States")) else parts[-2]
                        # extract the 2-letter state
                        st_tokens = st_zip.split()
                        if st_tokens and len(st_tokens[0]) == 2 and st_tokens[0].isupper():
                            state = st_tokens[0]
                    if not city and len(parts) >= 3:
                        # If last part is a country, city is parts[-3]; else parts[-2]
                        if parts[-1] in ("USA", "US", "United States"):
                            city = parts[-3] if len(parts) >= 3 else None
                        else:
                            city = parts[-2]

            # phone fallback: top-level first, then meta.raw.phone
            phone = rt.get("phone") or raw.get("phone")
            if phone and isinstance(phone, str):
                digits = "".join(c for c in phone if c.isdigit())
                if len(digits) == 10:
                    phone = "+1" + digits
                elif len(digits) == 11 and digits.startswith("1"):
                    phone = "+" + digits
                elif not phone.startswith("+"):
                    phone = phone  # leave as-is if can't normalize

            # warehouse_name fallback: meta.raw.name or meta.warehouse_name
            wh_name = rt.get("warehouse_name")
            if not wh_name and meta:
                wh_name = (meta.get("warehouse_name")
                           or raw.get("name"))

            insert_row = {
                "radar_target_id": rt["id"],
                "address": rt.get("address"),
                "city": city,
                "state": state,
                "phone": phone,
                "email": rt.get("email") or raw.get("email"),
                "warehouse_name": wh_name,
                "asset_value": rt.get("asset_value"),
                "source": "radar_targets",
                "status": "pending_enrichment",
                "meta": meta,
            }
            sb.table("enriched_leads").insert(insert_row).execute()
            rows_processed += 1
        except Exception as e:
            rows_errored += 1
            error_msgs.append(f"{rt.get('id', '?')[:8]}: {type(e).__name__}: {e}")
            log.warning(f"scanner: insert failed for {rt.get('id')}: {e}")

    finished_at = datetime.now(timezone.utc)
    summary = (f"scanned {rows_seen} candidates, wrote {rows_processed} to enriched_leads, "
               f"{rows_errored} errored")
    status = "ok" if rows_errored == 0 else "ok"  # row errors are not run errors
    err_field = None if rows_errored == 0 else "; ".join(error_msgs[:5])

    _log_activity(sb, "lead_scanner", run_id, started_at, status,
                  rows_seen=rows_seen, rows_processed=rows_processed,
                  rows_errored=rows_errored, error=err_field, summary=summary)
    _update_config(sb, "lead_scanner", status, finished_at.isoformat())

    log.info(summary)
    return {"status": status, "rows_seen": rows_seen, "rows_processed": rows_processed,
            "rows_errored": rows_errored}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="Read radar_targets but don't write to enriched_leads (overrides config)")
    p.add_argument("--status", action="store_true", help="Print last run + stats and exit")
    args = p.parse_args()

    if args.status:
        sb = _sb()
        cfg = _read_config(sb)
        last_act = (sb.table("agent_activity")
                      .select("*")
                      .eq("agent_name", "lead_scanner")
                      .order("started_at", desc=True)
                      .limit(1)
                      .execute())
        print(json.dumps({
            "config": cfg,
            "last_run": last_act.data[0] if last_act.data else None,
        }, indent=2, default=str))
        return

    result = run()
    sys.exit(0 if result["status"] in ("ok", "skipped_disabled") else 1)


if __name__ == "__main__":
    main()
