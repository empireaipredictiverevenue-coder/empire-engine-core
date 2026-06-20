"""
EMPIRE V49 · STORM ALERT AGENT (PHASE 1)
=========================================
Real-time NWS severe weather alert → radar_targets updater.

Cron-friendly one-shot that:
  1. Fetches active NWS alerts via StormTracker (empire_weather_scout.py)
  2. Filters for Texas metro zones + severe events (Tornado, Hail, Thunderstorm, Flood)
  3. Spatial-matches active radar_targets against alert polygons using shapely
  4. Updates radar_targets.damage_severity and urgency_score (upgrades only)
  5. Logs alert summaries to storm_risk_log + run to agent_activity

Cron: every 15 min during storm season; every 30 min off-peak.

Usage:
    python3 -m agents.storm_alert
    python3 -m agents.storm_alert --dry-run
    python3 -m agents.storm_alert --status
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
from typing import List, Dict, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client
from shapely.geometry import shape, Point
from agents.event_emitter import emit_agent_event

log = logging.getLogger("empire.storm_alert")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "storm_alert"

# ── Alert event → (damage_severity, urgency_score) mapping ───────────
# urgency_score: 1-10, higher = more urgent
SEVERITY_MAP: Dict[str, Tuple[str, int]] = {
    "TORNADO":              ("Severe",   10),
    "SEVERE THUNDERSTORM":  ("Severe",    8),
    "HAIL":                 ("Moderate",  7),
    "FLASH FLOOD":          ("Moderate",  6),
    "FLOOD WARNING":        ("Moderate",  6),
    "FLOOD ADVISORY":       ("Moderate",  5),
    "WIND":                 ("Severe",    9),
    "HURRICANE":            ("Severe",    9),
}

# ── Helpers ───────────────────────────────────────────────────────────

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "min_urgency": 5}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled":     row.get("enabled", True),
        "dry_run":     row.get("dry_run", True),
        "min_urgency": cfg.get("min_urgency", 5),
    }


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_blocked=0, rows_errored=0,
                  error=None, summary=None):
    return emit_agent_event(
        sb=sb, agent_name=AGENT_NAME, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_blocked=rows_blocked, rows_errored=rows_errored,
        error=error, summary=summary,
    )


def _parse_wkt_point(location: Optional[str]) -> Optional[Point]:
    """Parse a WKT POINT(lon lat) string into a shapely Point.

    Example: 'POINT(-97.2919 32.8234)' -> Point(-97.2919, 32.8234)
    """
    if not location:
        return None
    try:
        cleaned = location.replace("POINT(", "").replace(")", "").strip()
        parts = cleaned.split()
        if len(parts) != 2:
            return None
        lon, lat = float(parts[0]), float(parts[1])
        return Point(lon, lat)
    except (ValueError, IndexError):
        return None


def _determine_alert_impact(alert: Dict) -> Tuple[str, int]:
    """Map an NWS alert's event type to damage_severity + urgency_score."""
    props = alert.get("properties") or {}
    event = (props.get("event") or "").upper()
    for keyword, (sev, urg) in SEVERITY_MAP.items():
        if keyword in event:
            return sev, urg
    return "Moderate", 5  # default fallback


def _load_targets(sb) -> List[Dict]:
    """Load all active radar_targets that have a WKT location string."""
    try:
        r = sb.table("radar_targets") \
            .select("id, location, city, state, damage_severity, urgency_score") \
            .eq("status", "active") \
            .neq("location", "null") \
            .execute()
        return r.data or []
    except Exception as e:
        log.warning(f"Failed to load radar_targets: {e}")
        return []


# ── Main run logic ────────────────────────────────────────────────────

def run_once(dry_run_override: Optional[bool] = None) -> dict:
    """Run one storm-alert cycle.

    1. Fetch & filter NWS active alerts
    2. Load active radar_targets with location data
    3. Spatial-match targets against alert polygons
    4. Upgrade damage_severity / urgency_score for matched targets
    5. Log to storm_risk_log + agent_activity
    """
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

    # ── 1. Fetch NWS alerts ──────────────────────────────────────────
    try:
        from empire_weather_scout import StormTracker
        tracker = StormTracker()
        raw_alerts = asyncio.run(tracker.get_active_alerts())
        relevant = tracker.filter_relevant(raw_alerts)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log.exception("NWS fetch failed")
        finished_at = _log_activity(
            sb, run_id, started_at, "error", error=err,
            summary=f"NWS fetch failed: {err[:120]}",
        )
        _update_config(sb, "error", finished_at)
        return {"status": "error", "error": err}

    if not relevant:
        summary = f"NWS polled {len(raw_alerts)} alerts, none relevant for Texas metros"
        log.info(summary)
        finished_at = _log_activity(
            sb, run_id, started_at, "ok",
            rows_seen=len(raw_alerts), summary=summary,
        )
        _update_config(sb, "ok", finished_at)
        return {"status": "ok", "alerts_fetched": len(raw_alerts), "alerts_relevant": 0}

    # ── 2. Load targets ───────────────────────────────────────────────
    targets = _load_targets(sb)
    if not targets:
        summary = "No radar_targets with location data to match"
        log.info(summary)
        finished_at = _log_activity(
            sb, run_id, started_at, "ok", rows_seen=len(relevant), summary=summary,
        )
        _update_config(sb, "ok", finished_at)
        return {"status": "ok", "note": "no targets to match", "alerts_relevant": len(relevant)}

    # Parse target locations upfront into (id, point, old_severity, old_urgency)
    target_points: List[Tuple[str, Point, Optional[str], Optional[int]]] = []
    for t in targets:
        pt = _parse_wkt_point(t.get("location"))
        if pt:
            target_points.append((
                t["id"], pt,
                t.get("damage_severity"),
                t.get("urgency_score"),
            ))

    if not target_points:
        summary = f"Loaded {len(targets)} targets, but none had parseable locations"
        log.warning(summary)
        finished_at = _log_activity(
            sb, run_id, started_at, "ok", rows_seen=len(relevant),
            summary=summary,
        )
        _update_config(sb, "ok", finished_at)
        return {"status": "ok", "note": summary}

    # ── 3. Spatial-match ─────────────────────────────────────────────
    # Build alert polygons once
    alert_polys = []  # list of (polygon, sev, urg, event, headline, area_desc, nws_id)
    for alert in relevant:
        geom = alert.get("geometry") or {}
        if geom.get("type") not in ("Polygon",):
            continue
        try:
            poly = shape(geom)
        except Exception:
            continue
        sev, urg = _determine_alert_impact(alert)
        props = alert.get("properties") or {}
        area_desc = (props.get("areaDesc") or "")[:80] or "Unknown"
        alert_polys.append((
            poly, sev, urg,
            props.get("event", "Unknown"),
            props.get("headline", "")[:120],
            area_desc,
            props.get("id", alert.get("id", "unknown")),
        ))

    if not alert_polys:
        summary = f"{len(relevant)} relevant alerts but none had parseable polygon geometry"
        log.info(summary)
        finished_at = _log_activity(
            sb, run_id, started_at, "ok",
            rows_seen=len(relevant), rows_blocked=len(relevant),
            summary=summary,
        )
        _update_config(sb, "ok", finished_at)
        return {"status": "ok", "note": summary, "alerts_relevant": len(relevant)}

    # Match & update
    # NOTE: must check against the *best urgency already assigned in this run*,
    # not the old DB value — otherwise a less-severe polygon processed later
    # can overwrite a more-severe assignment from an earlier polygon.
    updates: Dict[str, Tuple[str, int]] = {}  # target_id -> (severity, urgency)
    for poly, sev, urg, event, headline, area_desc, nws_id in alert_polys:
        for target_id, pt, old_sev, old_urg in target_points:
            if not poly.contains(pt):
                continue
            # Best urgency so far: check run-assigned value first, then DB value
            best = updates.get(target_id)
            best_urg = best[1] if best else (old_urg if isinstance(old_urg, (int, float)) else 0)
            if urg > best_urg:
                updates[target_id] = (sev, urg)

    # ── 4. Apply updates ────────────────────────────────────────────
    updated = 0
    if not dry_run and updates:
        now_iso = datetime.now(timezone.utc).isoformat()
        for target_id, (sev, urg) in updates.items():
            try:
                sb.table("radar_targets").update({
                    "damage_severity": sev,
                    "urgency_score": urg,
                    "updated_at": now_iso,
                }).eq("id", target_id).execute()
                updated += 1
            except Exception as e:
                log.warning(f"Failed to update target {target_id[:12]}: {e}")

    # ── 5. Log alert summaries to storm_risk_log ──────────────────────
    log_rows = [
        {
            "source":     AGENT_NAME,
            "run_id":     str(run_id),
            "metro":      a[5],  # area_desc from NWS
            "day":        0,
            "risk_level": a[1],  # severity
            "risk_rank":  a[2],  # urgency score
            "lat":        None,
            "lon":        None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for a in alert_polys
    ]
    log_rows_written = 0
    if log_rows and not dry_run:
        try:
            sb.table("storm_risk_log").insert(log_rows).execute()
            log_rows_written = len(log_rows)
        except Exception as e:
            log.warning(f"storm_risk_log insert failed: {e}")

    summary = (
        f"[{'DRY-RUN' if dry_run else 'LIVE'}] "
        f"alerts_fetched={len(raw_alerts)} "
        f"alerts_relevant={len(relevant)} "
        f"alerts_with_polygons={len(alert_polys)} "
        f"targets_matched={len(updates)} "
        f"targets_updated={updated} "
        f"log_rows={log_rows_written}"
    )
    log.info(summary)
    finished_at = _log_activity(
        sb, run_id, started_at, "ok",
        rows_seen=len(relevant), rows_processed=updated,
        rows_blocked=len(relevant) - len(alert_polys),
        summary=summary[:500],
    )
    _update_config(sb, "ok", finished_at)
    return {
        "status":              "ok",
        "alerts_fetched":      len(raw_alerts),
        "alerts_relevant":     len(relevant),
        "alerts_with_polygons": len(alert_polys),
        "targets_matched":     len(updates),
        "targets_updated":     updated,
        "log_rows_written":    log_rows_written,
        "dry_run":             dry_run,
    }


# ── CLI ────────────────────────────────────────────────────────────────

def show_status():
    """Print agent status and recent run history."""
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        cfg = row.get("config_json") or {}
        print(f"agent:        {AGENT_NAME}")
        print(f"enabled:      {row.get('enabled')}")
        print(f"dry_run:      {row.get('dry_run')}")
        print(f"min_urgency:  {cfg.get('min_urgency', 5)}")
        print(f"last_run_at:  {row.get('last_run_at')}")
        print(f"last_status:  {row.get('last_run_status')}")
    else:
        print(f"agent:        {AGENT_NAME}  (not initialized)")
    print()
    r2 = sb.table("agent_activity").select(
        "started_at,status,rows_seen,rows_processed,summary"
    ).eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(8).execute()
    print("recent runs:")
    for row in r2.data:
        sa = (row.get("started_at") or "")[:19]
        st = row.get("status", "")
        rs = row.get("rows_seen", 0)
        rp = row.get("rows_processed", 0)
        sm = (row.get("summary") or "")[:80]
        print(f"  {sa}  {st:10}  alerts={rs}  updated={rp}  {sm}")
    print()
    # Show recent storm_risk_log entries from this agent
    r3 = sb.table("storm_risk_log").select("created_at,metro,risk_level,risk_rank").eq("source", AGENT_NAME).order("created_at", desc=True).limit(8).execute()
    if r3.data:
        print("recent storm_risk_log entries:")
        for row in r3.data:
            ca = (row.get("created_at") or "")[:19]
            m  = (row.get("metro") or "")[:50]
            rl = row.get("risk_level", "")
            rr = row.get("risk_rank", 0)
            print(f"  {ca}  {m:50s}  {rl:10}  urg={rr}")


def main():
    p = argparse.ArgumentParser(description="Empire AI Storm Alert Agent (Phase 1)")
    p.add_argument("--dry-run", action="store_true", help="report only, no DB writes")
    p.add_argument("--status", action="store_true", help="print last run + stats")
    args = p.parse_args()
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
