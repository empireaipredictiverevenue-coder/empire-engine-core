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
import re
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
from agents.event_emitter import emit_agent_event

log = logging.getLogger("empire.lead_scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ── ADDRESS PARSING ───────────────────────────────────────────────────

# Regex to extract 2-letter state + ZIP from the end of a string.
_STATE_ZIP_RE = re.compile(
    r"\b(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)\s*$",
    re.ASCII,
)

# Common street suffixes and directionals to filter out of city candidates.
_STREET_WORDS = {
    "st", "ave", "rd", "blvd", "dr", "ln", "ct", "pl", "way",
    "n", "s", "e", "w", "ne", "nw", "se", "sw",
    "north", "south", "east", "west",
    "street", "avenue", "road", "boulevard", "drive", "lane", "court", "place",
    "northeast", "northwest", "southeast", "southwest",
    "pky", "parkway", "hwy", "highway", "trl", "trail",
    "cir", "circle", "sq", "square", "ter", "terrace",
    "bnd", "bend", "byp", "bypass", "xing", "crossing",
}

# Lat/lng coordinate pattern: two comma-separated floats
_LAT_LNG_RE = re.compile(
    r"^-?\d+\.\d+,\s*-?\d+\.\d+$"
)


def _parse_address(addr: str, existing_city: str = None, existing_state: str = None,
                   raw: dict = None) -> tuple:
    """
    Parse city and state from an address string.

    Resolution order:
      1. Already-provided city/state (from structured data)
      2. raw.city / raw.state (Google Places structured fields)
      3. Comma-separated address (ends with "..., ST ZIP, USA")
      4. Regex extraction from the end of a no-comma address ("...Fort Worth TX 76106")
      5. Fallback: None

    Returns (city, state) where either can be None.
    """
    # 1) Already have it
    if existing_city and existing_state:
        return existing_city, existing_state

    # 2) Google Places structured data in meta.raw
    if raw:
        rc = raw.get("city")
        rs = raw.get("state")
        if rc and rs:
            return rc, rs

    if not addr or not isinstance(addr, str):
        return existing_city, existing_state

    addr = addr.strip()
    if not addr:
        return existing_city, existing_state

    # 3) Lat/lng — skip, no city/state in coordinates
    if _LAT_LNG_RE.match(addr.replace(" ", "")):
        return existing_city, existing_state

    # 4) Comma-separated: "<street>, <city>, <ST> <zip>, <country>"
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    if len(parts) >= 2:
        city = existing_city
        state = existing_state

        # Determine which part has "ST ZIP" and which has the city
        # Structure depends on whether the country is present
        if parts[-1] in ("USA", "US", "United States"):
            # parts[-2] = "TX 76106" or "TX 78218, USA"
            st_part = parts[-2]
            city_part_idx = -3
        else:
            # parts[-1] = "TX 76106" or "TX 78218"
            st_part = parts[-1]
            city_part_idx = -2

        if not state and st_part:
            st_tokens = st_part.split()
            if st_tokens and len(st_tokens[0]) == 2 and st_tokens[0].isupper():
                state = st_tokens[0]

        if not city and len(parts) >= abs(city_part_idx):
            city = parts[city_part_idx].strip()

        return city, state

    # 5) No commas: extract state+ZIP from the end, then backtrack for city
    # Patterns like "400 East Industrial Avenue Fort Worth TX 76106"
    m = _STATE_ZIP_RE.search(addr)
    if m:
        state = m.group("state") if not existing_state else existing_state
        # Everything before the state is "<street> <city>" or just "<city>"
        before = addr[:m.start("state")].strip().rstrip(",")
        # Split into tokens and find the city: take the last 1-3 tokens
        # that aren't street suffixes, directions, or numbers.
        tokens = before.split()
        city_tokens = []
        for t in reversed(tokens):
            t_clean = t.strip(",.")
            # Stop at numbers, street words, or single letters
            if t_clean.isdigit():
                break
            if t_clean.lower() in _STREET_WORDS:
                break
            if len(t_clean) == 1 and t_clean.isalpha():
                break
            city_tokens.insert(0, t_clean)
            # Reasonable city name is 1-3 words
            if len(city_tokens) >= 3:
                break

        if city_tokens and not existing_city:
            city = " ".join(city_tokens)

        return city if not existing_city else existing_city, state

    return existing_city, existing_state


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
            "min_urgency_for_engagement": 5,
        }
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled": row.get("enabled", True),
        "dry_run": row.get("dry_run", True),
        "max_per_run": cfg.get("max_per_run", default_max),
        "lookback_hours": cfg.get("lookback_hours", default_lookback),
        "min_urgency_for_engagement": cfg.get("min_urgency_for_engagement", 5),
    }

def _log_activity(sb, agent_name, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_errored=0, error=None, summary=None):
    return emit_agent_event(
        sb=sb, agent_name=agent_name, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_errored=rows_errored, error=error, summary=summary,
    )


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

    # ALSO pick up recently-upgraded targets (storm_log_to_targets bumps
    # urgency_score on existing rows when storms hit their metros). Without
    # this branch the pipeline stays idle when no NEW radar_targets arrive
    # but storm severity rises on the existing 9k dataset.
    min_urg = cfg.get("min_urgency_for_engagement", 5)
    urg_res = (sb.table("radar_targets")
                .select("id, address, city, state, phone, email, warehouse_name, asset_value, status, created_at, updated_at, urgency_score, meta, source")
                .eq("status", "active")
                .gte("urgency_score", min_urg)
                .gte("updated_at", since)
                .order("urgency_score", desc=True)
                .limit(cfg["max_per_run"] * 2)
                .execute())
    urg_ids = {r["id"] for r in (urg_res.data or [])}
    if urg_ids:
        existing_ids = {r["id"] for r in candidates}
        for r in (urg_res.data or []):
            if r["id"] not in existing_ids:
                candidates.append(r)
        log.info(f"scanner: +{len(urg_ids)} urgent-upgraded candidates (urgency >= {min_urg})")
    in_fallback = False
    if not candidates:
        # First-run / backfill mode: no recent ones. Re-query for the NEWEST
        # active radar_targets (the previous query was order=asc, so we got the
        # oldest first — that meant dedup ate them all because they were
        # already in enriched_leads).
        in_fallback = True
        log.info(f"scanner: no radar_targets in last {cfg['lookback_hours']}h — falling back to all-time, OLDEST-first to backfill unscanned targets")
        fb_res = (sb.table("radar_targets")
                    .select("id, address, city, state, phone, email, warehouse_name, asset_value, status, created_at, meta, source")
                    .eq("status", "active")
                    .order("created_at", desc=False)  # oldest first in fallback (backfill unscanned)
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
            # Parse city/state from the address using the new robust parser
            meta = rt.get("meta") or {}
            raw = meta.get("raw") or {}
            city, state = _parse_address(
                rt.get("address"),
                existing_city=rt.get("city"),
                existing_state=rt.get("state"),
                raw=raw,
            )

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
