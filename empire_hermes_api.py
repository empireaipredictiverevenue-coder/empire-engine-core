"""
Empire AI - Hermes dashboard endpoint.

GET /api/v1/command/hermes  -- single-shot payload with all
  the system-health data the operator SPA needs for the Hermes tab.

Returns:
{
  "ok": true,
  "now":            "iso timestamp",
  "gateway": {
    "status":         "online" | "offline",
    "uptime_s":       12345,
    "pid":            1234,
    "restarts":       0,
  },
  "daemons": [
    {
      "name":           "sms-qc",
      "status":         "online" | "offline",
      "uptime_s":       12345,
      "pid":            1234,
      "restarts":       0,
      "memory_mb":      78,
      "last_tick_age_s": 23,
    },
    ...
  ],
  "agent_activity_feed": [
    {
      "agent_name":     "lead_converter",
      "started_at":     "...",
      "finished_at":    "...",
      "status":         "ok",
      "rows_seen":      100,
      "rows_processed": 50,
      "summary":        "...",
    },
    ...
  ],
  "funnel_snapshot": {
    "radar_targets":            N,
    "enriched_leads":           N,
    "sms_sequences_active":     N,
    "dispatches_total":         N,
    "contractors_total":        N,
    "contractors_active":       N,
  },
  "qc_summary": {
    "tier_1_remediations_24h":  N,
    "tier_2_pings_24h":         N,
    "tier_3_summaries_24h":     N,
    "unresolved_tier_2":        N,
  },
  "inbound_24h": {
    "total":      N,
    "stop":       N,
    "yes":        N,
    "notnow":     N,
    "other":      N,
  }
}

Auth: requires require_auth (operator only).
"""
import os
import time
import logging
import subprocess
import json
from datetime import datetime, timezone, timedelta
from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("empire.hermes_api")


def _pm2_list() -> list:
    """Return list of pm2 process dicts."""
    try:
        out = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True, text=True, timeout=10,
        )
        return json.loads(out.stdout or "[]")
    except Exception as e:
        log.debug(f"[hermes_api] pm2 jlist failed: {e}")
        return []


def _db():
    from hub import get_db
    return get_db()


async def hermes_dashboard(request: Request) -> JSONResponse:
    """GET /api/v1/command/hermes"""
    # Auth: mirror the inline check used by qc_api
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    token = auth_header[7:].strip()
    expected = os.environ.get("HUB_TOKEN", "").strip()
    if not expected or token != expected:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # ---- pm2 fleet status ----
    procs = _pm2_list()
    daemons = []
    for p in procs:
        try:
            name = p.get("name", "?")
            pid = p.get("pid") or 0
            pm2_env = p.get("pm2_env") or {}
            status = p.get("pm2_env", {}).get("status", "?")
            # uptime
            try:
                started_ms = pm2_env.get("pm_uptime", 0)
                uptime_s = int((now.timestamp() * 1000 - started_ms) / 1000) if started_ms else 0
            except Exception:
                uptime_s = 0
            # memory
            try:
                mem_mb = int((p.get("monit", {}) or {}).get("memory", 0) / 1024 / 1024)
            except Exception:
                mem_mb = 0
            # restarts
            restarts = pm2_env.get("restart_time", 0)
            daemons.append({
                "name":         name,
                "status":       status,
                "pid":          pid,
                "uptime_s":     uptime_s,
                "memory_mb":    mem_mb,
                "restarts":     restarts,
            })
        except Exception:
            continue

    # ---- gateway status (look for the hermes gateway daemon) ----
    # pm2 may not list it; it might be a system process. Use a heuristic:
    # if the gateway CLI is on PATH and responds, it's online.
    gateway_status = "offline"
    gateway_pid = 0
    try:
        out = subprocess.run(
            ["pgrep", "-f", "hermes.*gateway"],
            capture_output=True, text=True, timeout=5,
        )
        if out.stdout.strip():
            gateway_pid = int(out.stdout.strip().splitlines()[0])
            gateway_status = "online"
    except Exception:
        pass

    # ---- agent_activity feed ----
    activity = []
    try:
        db = _db()
        r = (db.table("agent_activity")
                .select("agent_name,started_at,finished_at,status,rows_seen,rows_processed,rows_blocked,rows_errored,summary")
                .order("started_at", desc=True)
                .limit(20).execute())
        activity = r.data or []
    except Exception as e:
        log.debug(f"[hermes_api] agent_activity query failed: {e}")

    # ---- funnel snapshot ----
    funnel = {}
    for table, key in [
        ("radar_targets",     "radar_targets"),
        ("enriched_leads",    "enriched_leads"),
        ("sms_sequences",     "sms_sequences_total"),
        ("dispatches",        "dispatches_total"),
        ("contractors",       "contractors_total"),
    ]:
        try:
            r = db.table(table).select("id", count="exact").execute()
            funnel[key] = r.count or 0
        except Exception:
            funnel[key] = None
    # active sequences + active contractors
    try:
        r = db.table("sms_sequences").select("id", count="exact").eq("status", "active").execute()
        funnel["sms_sequences_active"] = r.count or 0
    except Exception:
        funnel["sms_sequences_active"] = None
    try:
        r = db.table("contractors").select("id", count="exact").eq("active", True).execute()
        funnel["contractors_active"] = r.count or 0
    except Exception:
        funnel["contractors_active"] = None

    # ---- qc summary ----
    qc = {}
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    for sev, key in [
        ("tier_1", "tier_1_remediations_24h"),
        ("tier_2", "tier_2_pings_24h"),
        ("tier_3", "tier_3_summaries_24h"),
    ]:
        try:
            r = db.table("qc_events").select("id", count="exact").eq("severity", sev).gte("created_at", cutoff_24h).execute()
            qc[key] = r.count or 0
        except Exception:
            qc[key] = None
    try:
        r = db.table("qc_events").select("id", count="exact").eq("severity","tier_2").eq("resolved", False).execute()
        qc["unresolved_tier_2"] = r.count or 0
    except Exception:
        qc["unresolved_tier_2"] = None

    # ---- inbound 24h ----
    inbound = {"total": 0, "stop": 0, "yes": 0, "notnow": 0, "other": 0}
    try:
        r = db.table("sms_log").select("body").eq("direction","inbound").gte("created_at", cutoff_24h).limit(500).execute()
        rows = r.data or []
        inbound["total"] = len(rows)
        for row in rows:
            body = (row.get("body") or "").upper()
            if "STOP" in body:    inbound["stop"]   += 1
            elif "YES" in body:   inbound["yes"]    += 1
            elif "NOTNOW" in body: inbound["notnow"] += 1
            else:                 inbound["other"]  += 1
    except Exception as e:
        log.debug(f"[hermes_api] inbound query failed: {e}")

    return JSONResponse({
        "ok":                  True,
        "now":                 now_iso,
        "gateway": {
            "status":   gateway_status,
            "pid":      gateway_pid,
            "uptime_s": None,
        },
        "daemons":             daemons,
        "agent_activity_feed": activity,
        "funnel_snapshot":     funnel,
        "qc_summary":          qc,
        "inbound_24h":         inbound,
    }, status_code=200)


def register_hermes_routes(app):
    app.add_api_route(
        "/api/v1/command/hermes",
        hermes_dashboard,
        methods=["GET"],
    )
    log.info("[hermes_api] route registered: GET /api/v1/command/hermes")
