"""Empire AI · Predictive Revenue — Lead Pulse System

Real-time funnel visibility + automated storm-triggered contractor outreach.

Endpoints:
  GET  /api/v1/pulse/summary           — overall funnel snapshot
  GET  /api/v1/pulse/sms-volume        — outbound SMS by hour, last 24h
  GET  /api/v1/pulse/leads-hot         — leads ready for contractor action
  GET  /api/v1/pulse/reply-rate        — reply rate by sequence (last 7d)
  GET  /api/v1/pulse/metro-heat        — SMS activity per metro, last 24h
  GET  /api/v1/pulse/contractor-stats  — top engaged contractors
  GET  /pulse                          — HTML dashboard

  POST /api/v1/webhook/storm-target    — when radar_target is created with
                                          urgency_score >= threshold, fan out
                                          SMS to active contractors in that
                                          metro/niche
  GET  /api/v1/pulse/storm-stream      — recent storm-triggered alerts

Wired into hub.py as:
    from empire_pulse import register_pulse_routes
    register_pulse_routes(app, get_db=get_db)
"""
from __future__ import annotations

import html
import json
import logging
import re
import os
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional

try:
    from dotenv import load_dotenv
    from pathlib import Path
    _r = Path(__file__).resolve().parent.parent
    load_dotenv(_r.parent / ".env")
except Exception:
    pass

from supabase import create_client

log = logging.getLogger("empire_pulse")


# ── STORM TRIGGER THRESHOLDS ─────────────────────────────────────────────
STORM_TRIGGER_URGENCY = 7        # only fire on urgent storm targets
STORM_TRIGGER_MIN_TARGETS = 1     # at least 1 radar_target needed
STORM_TRIGGER_COOLDOWN_MIN = 30   # don't re-fire for same metro/niche within 30 min
STORM_TRIGGER_MAX_CONTRACTORS = 10  # cap to avoid SMS burst


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


# ── PULSE DATA HELPERS ────────────────────────────────────────────────────
def pulse_summary(sb) -> dict:
    """One-shot snapshot of the funnel."""
    now = datetime.now(timezone.utc)
    h24 = (now - timedelta(hours=24)).isoformat()
    h1 = (now - timedelta(hours=1)).isoformat()

    def cnt(table, **f):
        q = sb.table(table).select("id", count="exact")
        for k, v in f.items():
            q = q.eq(k, v)
        r = q.execute()
        return r.count or 0

    return {
        "ts": now.isoformat(),
        "contractors": {
            "total": cnt("contractors"),
            "active": cnt("contractors", active=True),
            "with_phone": cnt("contractors", active=True) - cnt("contractors", active=True, phone=None),
        },
        "leads": {
            "enriched_total": cnt("enriched_leads"),
            "pending_outreach": cnt("enriched_leads", status="pending_outreach"),
            "converted": cnt("enriched_leads", status="converted"),
        },
        "outreach": {
            "sms_out_24h": cnt("sms_log", direction="outbound") if False else
                            sb.table("sms_log").select("id", count="exact")
                              .eq("direction","outbound").gte("created_at", h24).execute().count,
            "sms_in_24h":  sb.table("sms_log").select("id", count="exact")
                              .eq("direction","inbound").gte("created_at", h24).execute().count,
            "sms_out_1h":  sb.table("sms_log").select("id", count="exact")
                              .eq("direction","outbound").gte("created_at", h1).execute().count,
            "outreach_log_24h": sb.table("outreach_log").select("id", count="exact")
                              .gte("created_at", h24).execute().count,
        },
        "fees": {
            "paid_count":  cnt("fee_events", status="paid"),
            "pending_count": cnt("fee_events", status="pending"),
        },
        "sequences": {
            "active_recruits": sb.table("sms_sequences").select("id", count="exact")
                                .eq("sequence_type","contractor_recruit")
                                .eq("status","active").execute().count,
        },
    }


def pulse_sms_volume(sb, hours: int = 24) -> list[dict]:
    """Outbound SMS bucketed by hour, last N hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    r = sb.table("sms_log").select("created_at,direction").gte("created_at", cutoff).execute()
    out = Counter()
    inn = Counter()
    for x in (r.data or []):
        ts = (x.get("created_at") or "")[:13]  # YYYY-MM-DDTHH
        if x.get("direction") == "outbound":
            out[ts] += 1
        else:
            inn[ts] += 1
    return [
        {"hour": h + ":00", "outbound": out.get(h, 0), "inbound": inn.get(h, 0)}
        for h in sorted(set(list(out) + list(inn)))
    ]


def pulse_leads_hot(sb, limit: int = 25) -> list[dict]:
    """Leads awaiting contractor action (pending_outreach, top score)."""
    r = (sb.table("enriched_leads")
            .select("id,phone,city,state,score,asset_value,created_at,address")
            .eq("status", "pending_outreach")
            .order("score", desc=True)
            .limit(limit)
            .execute())
    return r.data or []


def pulse_reply_rate(sb, days: int = 7) -> list[dict]:
    """Reply rate by sequence, last N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    r = (sb.table("outreach_log")
            .select("sequence,channel,sent_at,response_received_at")
            .gte("created_at", cutoff)
            .execute())
    by_seq: dict[str, dict[str, int]] = defaultdict(lambda: {"sent": 0, "replied": 0})
    for x in (r.data or []):
        seq = x.get("sequence") or "unknown"
        if x.get("sent_at"):
            by_seq[seq]["sent"] += 1
        if x.get("response_received_at"):
            by_seq[seq]["replied"] += 1
    return [
        {"sequence": k, "sent": v["sent"], "replied": v["replied"],
         "rate": round(v["replied"] / v["sent"] * 100, 1) if v["sent"] else 0}
        for k, v in sorted(by_seq.items(), key=lambda kv: -kv[1]["sent"])
    ]


def pulse_metro_heat(sb, hours: int = 24) -> list[dict]:
    """SMS activity per metro, last N hours (from contractors.metro)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # Get outbound sms from last 24h with phone
    r = sb.table("sms_log").select("phone").eq("direction","outbound").gte("created_at", cutoff).limit(5000).execute()
    phones = [x.get("phone") for x in (r.data or []) if x.get("phone")]
    if not phones:
        return []
    # Lookup metros for these phones (chunked)
    by_metro = Counter()
    for i in range(0, len(phones), 500):
        chunk = phones[i:i+500]
        conts = sb.table("contractors").select("phone,metro").in_("phone", chunk).execute()
        for c in (conts.data or []):
            m = c.get("metro") or "?"
            by_metro[m] += 1
    return [{"metro": m, "sms_sent": n} for m, n in by_metro.most_common(20)]


def pulse_contractor_stats(sb, limit: int = 20) -> list[dict]:
    """Top engaged contractors (most outreach activity, most replies)."""
    # We don't have direct per-contractor metrics — derive from sms_sequences
    r = (sb.table("sms_sequences")
            .select("phone,status,created_at,last_step_at,total_steps")
            .eq("sequence_type", "contractor_recruit")
            .order("last_step_at", desc=True, nullsfirst=False)
            .limit(limit)
            .execute())
    return r.data or []


# ── STORM-TRIGGER WEBHOOK ─────────────────────────────────────────────────
def _fan_out_storm_sms(sb, target: dict) -> dict:
    """Find matching contractors + dispatch SMS via hub."""
    city = target.get("city") or ""
    state = target.get("state") or ""
    sub_niche = target.get("sub_niche") or target.get("niche") or ""
    urgency = target.get("urgency_score") or 0

    # Find active contractors in this metro
    q = sb.table("contractors").select("id,name,phone,metro,niche").eq("active", True)
    if city:
        q = q.ilike("metro", f"%{city}%")
    elif state:
        q = q.eq("state", state) if "state" in [c["name"] for c in sb.table("contractors").select("state").limit(1).execute().data or [{}]] else q
    conts = q.limit(STORM_TRIGGER_MAX_CONTRACTORS * 3).execute().data or []

    # Score by relevance: same metro > same state > anything
    matched = []
    for c in conts:
        score = 0
        if c.get("metro") and city and city.lower() in (c.get("metro") or "").lower():
            score += 10
        if c.get("niche") and sub_niche and sub_niche.lower() in (c.get("niche") or "").lower():
            score += 5
        if score > 0:
            matched.append((score, c))
    matched.sort(key=lambda x: -x[0])
    matched = [m[1] for m in matched[:STORM_TRIGGER_MAX_CONTRACTORS]]

    if not matched:
        return {"fired": False, "reason": "no matching contractors", "city": city, "state": state}

    # Check cooldown (don't re-fire same metro/niche within 30 min)
    cooldown_cut = (datetime.now(timezone.utc) - timedelta(minutes=STORM_TRIGGER_COOLDOWN_MIN)).isoformat()
    cd = sb.table("storm_trigger_log").select("id").eq("city", city).eq("niche", sub_niche).gte("fired_at", cooldown_cut).execute()
    if cd.data:
        return {"fired": False, "reason": "cooldown", "city": city, "niche": sub_niche}

    # Build SMS body
    body = f"⚡ STORM ALERT [{city or 'your area'}]: {urgency}/10 urgency — leads available now. Reply YES to claim. - Empire AI"

    # Dispatch via hub
    import httpx
    hub = os.getenv("HUB_URL", "http://localhost:8001").rstrip("/")
    sent = 0
    errors = 0
    for c in matched:
        try:
            r = httpx.post(
                f"{hub}/api/v1/sms/enroll",
                json={
                    "phone": c["phone"],
                    "sequence": "storm_alert",
                    "step": 1,
                    "metadata": {"city": city, "urgency": urgency, "niche": sub_niche,
                                 "contractor_id": c["id"], "trigger": "storm_target_webhook"},
                },
                timeout=10,
            )
            if r.status_code in (200, 201, 202):
                sent += 1
            else:
                errors += 1
        except Exception as e:
            log.warning(f"storm-trigger: hub post failed for {c.get('phone')}: {e}")
            errors += 1

    # Log
    sb.table("storm_trigger_log").insert({
        "city": city, "state": state, "niche": sub_niche,
        "urgency_score": urgency, "contractors_targeted": sent,
        "errors": errors, "fired_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    return {"fired": True, "city": city, "niche": sub_niche, "urgency": urgency,
            "contractors_matched": len(matched), "sms_sent": sent, "errors": errors}


def _get_storm_stream(sb, limit: int = 25) -> list[dict]:
    r = sb.table("storm_trigger_log").select("*").order("fired_at", desc=True).limit(limit).execute()
    return r.data or []


# ── HTML DASHBOARD ────────────────────────────────────────────────────────
def _pulse_dashboard_html() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Empire AI · Lead Pulse</title>
<style>
  :root { --bg:#07111E; --card:#0A1726; --border:rgba(255,255,255,.08); --text:#E8EEF6; --muted:#8FA0B5; --teal:#6FCFC0; --red:#FF8B8B; --yellow:#FFD580; --green:#88DDD0; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family: ui-monospace, monospace; }
  .wrap { max-width: 1280px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 28px; font-weight: 300; letter-spacing: -.02em; color: #fff; margin: 0 0 8px; }
  h1 span { color: var(--teal); }
  .sub { color: var(--muted); font-size: 11px; letter-spacing: .22em; text-transform: uppercase; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 4px; padding: 18px; }
  .card .num { font-size: 32px; font-weight: 300; color: var(--teal); letter-spacing: -.02em; }
  .card .num.warn { color: var(--yellow); }
  .card .num.crit { color: var(--red); }
  .card .lbl { font-size: 9px; color: var(--muted); letter-spacing: .22em; text-transform: uppercase; margin-top: 6px; }
  .section { background: var(--card); border: 1px solid var(--border); border-radius: 4px; padding: 20px 24px; margin-bottom: 16px; }
  .section h2 { font-size: 16px; font-weight: 400; color: #fff; margin: 0 0 14px; letter-spacing: -.01em; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { color: var(--muted); text-align: left; padding: 6px 8px; font-weight: 400; font-size: 9px; letter-spacing: .22em; text-transform: uppercase; border-bottom: 1px solid var(--border); }
  td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,.04); }
  .bar { display: inline-block; height: 4px; background: rgba(255,255,255,.06); border-radius: 2px; width: 80px; vertical-align: middle; margin-right: 6px; position: relative; }
  .bar > span { position: absolute; top: 0; left: 0; height: 100%; background: linear-gradient(90deg, var(--teal), var(--green)); border-radius: 2px; }
  .row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
  .hot { background: rgba(111,207,192,.05); }
  pre { background: rgba(0,0,0,.3); padding: 12px; border-radius: 3px; font-size: 11px; overflow-x: auto; }
  .footer { color: var(--muted); font-size: 10px; margin-top: 24px; text-align: center; letter-spacing: .18em; text-transform: uppercase; }
  .live { display: inline-block; width: 6px; height: 6px; background: var(--teal); border-radius: 50%; animation: pulse 1.6s ease-in-out infinite; margin-right: 6px; vertical-align: middle; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .3; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Empire <span>Lead Pulse</span></h1>
  <div class="sub"><span class="live"></span> live · refreshes every 30s · empire-ai.co.uk</div>

  <div class="grid" id="kpis"></div>

  <div class="row">
    <div class="section">
      <h2>SMS Volume (last 24h)</h2>
      <div id="sms-chart"></div>
    </div>
    <div class="section">
      <h2>Metro Heat (SMS last 24h)</h2>
      <div id="metro-heat"></div>
    </div>
  </div>

  <div class="row">
    <div class="section">
      <h2>Reply Rate by Sequence (7d)</h2>
      <div id="reply-rate"></div>
    </div>
    <div class="section">
      <h2>Hot Leads (top score, pending_outreach)</h2>
      <div id="hot-leads"></div>
    </div>
  </div>

  <div class="section">
    <h2>Storm Trigger Stream (latest contractor fan-outs)</h2>
    <div id="storm-stream"></div>
  </div>

  <div class="footer">endpoints: /api/v1/pulse/{summary,sms-volume,leads-hot,reply-rate,metro-heat,contractor-stats,storm-stream}</div>
</div>

<script>
async function fetchJson(path) {
  const r = await fetch(path);
  return r.json();
}
async function refresh() {
  try {
    const sum = await fetchJson('/api/v1/pulse/summary');
    const kpis = [
      ['Active Contractors', sum.contractors.active, sum.contractors.total+' total'],
      ['Pending Outreach', sum.leads.pending_outreach, sum.leads.enriched_total+' enriched'],
      ['SMS Out (24h)', sum.outreach.sms_out_24h, 'in: '+sum.outreach.sms_in_24h],
      ['Fees Pending', sum.fees.pending_count, sum.fees.paid_count+' paid'],
    ];
    document.getElementById('kpis').innerHTML = kpis.map(([lbl, num, sub]) =>
      '<div class="card"><div class="num">'+num+'</div><div class="lbl">'+lbl+'</div><div class="lbl" style="margin-top:4px">'+sub+'</div></div>'
    ).join('');

    const vol = await fetchJson('/api/v1/pulse/sms-volume?hours=24');
    const max = Math.max(1, ...vol.map(v => Math.max(v.outbound, v.inbound)));
    document.getElementById('sms-chart').innerHTML = '<div style="display:flex;align-items:end;gap:2px;height:140px">'
      + vol.map(v => '<div title="'+v.hour+' out:'+v.outbound+' in:'+v.inbound+'" style="flex:1;display:flex;flex-direction:column;align-items:stretch;gap:1px">'
        + '<div style="background:var(--teal);height:'+(v.outbound/max*100)+'%"></div>'
        + '<div style="background:var(--yellow);height:'+(v.inbound/max*100)+'%"></div>'
        + '</div>').join('') + '</div><div style="display:flex;justify-content:space-between;font-size:9px;color:var(--muted);margin-top:6px">'
        + (vol.length>0 ? '<span>'+vol[0].hour+'</span><span>'+vol[Math.floor(vol.length/2)].hour+'</span><span>'+vol[vol.length-1].hour+'</span>' : '') + '</div>';

    const heat = await fetchJson('/api/v1/pulse/metro-heat?hours=24');
    document.getElementById('metro-heat').innerHTML = heat.length === 0 ? '<em style="color:var(--muted)">no data</em>'
      : '<table>' + heat.slice(0, 12).map(m => '<tr><td>'+m.metro+'</td><td style="text-align:right;color:var(--teal)">'+m.sms_sent+'</td></tr>').join('') + '</table>';

    const rr = await fetchJson('/api/v1/pulse/reply-rate?days=7');
    document.getElementById('reply-rate').innerHTML = rr.length === 0 ? '<em style="color:var(--muted)">no data</em>'
      : '<table><tr><th>Sequence</th><th>Sent</th><th>Replied</th><th>Rate</th></tr>'
      + rr.map(r => '<tr><td>'+r.sequence+'</td><td>'+r.sent+'</td><td>'+r.replied+'</td><td><span class="bar"><span style="width:'+Math.min(100, r.rate)+'%"></span></span>'+r.rate+'%</td></tr>').join('') + '</table>';

    const hot = await fetchJson('/api/v1/pulse/leads-hot?limit=10');
    document.getElementById('hot-leads').innerHTML = hot.length === 0 ? '<em style="color:var(--muted)">no pending leads</em>'
      : '<table><tr><th>Phone</th><th>City</th><th>Score</th><th>$</th></tr>'
      + hot.map(l => '<tr class="hot"><td>'+(l.phone||'')+'</td><td>'+l.city+'</td><td>'+(l.score||0).toFixed(2)+'</td><td>$'+(l.asset_value||0).toLocaleString()+'</td></tr>').join('') + '</table>';

    const stream = await fetchJson('/api/v1/pulse/storm-stream?limit=10');
    document.getElementById('storm-stream').innerHTML = stream.length === 0 ? '<em style="color:var(--muted)">no storm triggers fired yet</em>'
      : '<table><tr><th>When</th><th>City</th><th>Niche</th><th>Urg</th><th>Contractors</th><th>Errors</th></tr>'
      + stream.map(s => '<tr><td>'+(s.fired_at||'').slice(0,19)+'</td><td>'+s.city+'</td><td>'+s.niche+'</td><td>'+s.urgency_score+'</td><td style="color:var(--teal)">'+s.contractors_targeted+'</td><td style="color:'+(s.errors>0?'var(--red)':'var(--muted)')+'">'+s.errors+'</td></tr>').join('') + '</table>';

  } catch(e) { console.error(e); }
}
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>'''


# ── ROUTE REGISTRATION ─────────────────────────────────────────────────────


# ── UNIFIED ADMIN HEALTH (one endpoint, all 3 oversight layers) ────────
def _admin_health(sb) -> dict:
    """Returns a single snapshot: supervisor + self_healer + error-watcher
    + pm2 state + recent agent errors. Used by /api/v1/admin/health."""
    out = {"ts": datetime.now(timezone.utc).isoformat()}

    # 1) Supervisor: most recent agent_config rows
    try:
        cfg = sb.table("agent_config").select("agent_name,last_run_at,last_run_status,enabled").order("last_run_at", desc=True, nullsfirst=False).limit(20).execute()
        supervisor = []
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
        for c in (cfg.data or []):
            last = c.get("last_run_at")
            age_h = None
            status = "no_data"
            if last:
                try:
                    # Use the same proven parser as agents/system_supervisor.py
                    last_clean = last
                    for suffix in ("Z", "+00:00", "-00:00"):
                        if last_clean.endswith(suffix):
                            last_clean = last_clean[:-len(suffix)]
                            break
                    last_clean = re.sub(r"[+-]\d{2}:?\d{2}$", "", last_clean)
                    if "." in last_clean:
                        last_clean = last_clean.split(".")[0]
                    last_dt = datetime.fromisoformat(last_clean).replace(tzinfo=timezone.utc)
                    age_h = round((datetime.now(timezone.utc) - last_dt).total_seconds() / 3600, 2)
                    status = "ok" if age_h < 4 else "stale"
                except Exception as e:
                    status = f"parse_error: {type(e).__name__}: {str(e)[:80]}"
            supervisor.append({
                "agent": c.get("agent_name"),
                "last_run_at": last,
                "age_hours": age_h,
                "status": status,
                "enabled": c.get("enabled", True),
                "last_status": c.get("last_run_status"),
            })
        out["supervisor"] = supervisor
    except Exception as e:
        out["supervisor"] = {"error": str(e)[:200]}

    # 2) Self-healer: last 5 fixes
    try:
        r = sb.table("self_healer_log").select("action,target,status,detail,fired_at").order("fired_at", desc=True).limit(5).execute()
        out["self_healer"] = {
            "recent_fixes": r.data or [],
            "total_fixes": sb.table("self_healer_log").select("id", count="exact").execute().count or 0,
        }
    except Exception as e:
        out["self_healer"] = {"error": str(e)[:200]}

    # 3) Error-watcher: most recent watcher_findings (if table exists)
    try:
        r = sb.table("watcher_findings").select("id,source,severity,summary,created_at").order("created_at", desc=True).limit(5).execute()
        out["error_watcher"] = {
            "recent_findings": r.data or [],
            "open_count": sb.table("watcher_findings").select("id", count="exact").eq("status", "open").execute().count or 0,
        }
    except Exception as e:
        # watcher_findings may not exist yet — that's fine
        out["error_watcher"] = {"recent_findings": [], "open_count": 0, "note": "watcher_findings not yet populated"}

    # 4) PM2 process state
    try:
        import subprocess
        rr = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        procs = json.loads(rr.stdout) if rr.returncode == 0 else []
        states = {}
        for p in procs:
            st = p.get("pm2_env", {}).get("status", "?")
            states[st] = states.get(st, 0) + 1
        out["pm2"] = {
            "total": len(procs),
            "by_state": states,
            "online": states.get("online", 0),
        }
    except Exception as e:
        out["pm2"] = {"error": str(e)[:200]}

    # 5) Recent agent errors (last hour, all agents)
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = sb.table("agent_activity").select("agent_name,status,rows_errored,error,started_at").gte("started_at", cutoff).gt("rows_errored", 0).order("started_at", desc=True).limit(10).execute()
        out["agent_errors_1h"] = r.data or []
    except Exception as e:
        out["agent_errors_1h"] = {"error": str(e)[:200]}

    # 6) Vonage volume (from pulse_summary)
    try:
        out["vonage_24h"] = sb.table("sms_log").select("id", count="exact").eq("direction","outbound").gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()).execute().count or 0
    except Exception as e:
        out["vonage_24h"] = 0

    # Overall health verdict
    crit = []
    if isinstance(out.get("self_healer"), dict) and out["self_healer"].get("recent_fixes"):
        for f in out["self_healer"]["recent_fixes"][:5]:
            if f.get("status") in ("failed", "error"):
                crit.append(f"self_healer: {f.get('action')} on {f.get('target')} {f.get('status')}")
    if out.get("pm2", {}).get("by_state", {}).get("errored", 0) > 0:
        crit.append(f"pm2: {out['pm2']['by_state']['errored']} errored process(es)")
    if out.get("vonage_24h", 0) > 1000:
        crit.append(f"vonage: {out['vonage_24h']} SMS in 24h (burn rate)")
    out["health"] = "ok" if not crit else "warn"
    out["concerns"] = crit
    return out






# ── REAL REPLIES (filtered: is_test=false) ──────────────────────────────
def _real_replies(sb, limit: int = 50, hours: int = 168) -> list[dict]:
    """Inbound SMS from real contractors (excludes 555 sandbox numbers).
    Joins to contractors by phone, shows name/metro/niche + which
    sequence they were on."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        r = sb.table("sms_log").select("phone,body,created_at").eq("direction","inbound").eq("is_test", False).gte("created_at", cutoff).order("created_at", desc=True).limit(limit).execute()
        inbound = r.data or []
    except Exception as e:
        return [{"error": str(e)[:200]}]
    if not inbound:
        return []
    # join to contractors
    phones = list({x.get("phone","") for x in inbound if x.get("phone")})
    c_map: dict = {}
    try:
        for i in range(0, len(phones), 500):
            chunk = phones[i:i+500]
            rs = sb.table("contractors").select("id,name,phone,metro,niche,active,trust_score,completed_jobs").in_("phone", chunk).execute()
            for c in (rs.data or []):
                c_map[c["phone"]] = c
            # Also try without +1 prefix
            for phone in chunk:
                if phone.startswith("+1") and len(phone) == 12:
                    short = phone[2:]
                    if short not in c_map:
                        try:
                            r2 = sb.table("contractors").select("id,name,phone,metro,niche,active,trust_score,completed_jobs").eq("phone", short).limit(1).execute()
                            if r2.data:
                                c_map[phone] = r2.data[0]
                        except: pass
    except Exception as e:
        pass
    # also check sms_sequences for step info
    seq_map: dict = {}
    try:
        for phone in phones:
            r = sb.table("sms_sequences").select("phone,status,current_step,last_sent_at,created_at").eq("phone", phone).eq("sequence_type","contractor_recruit").execute()
            for s in (r.data or []):
                seq_map[s["phone"]] = s
    except: pass

    out = []
    for x in inbound:
        p = x.get("phone","")
        c = c_map.get(p, {})
        s = seq_map.get(p, {})
        out.append({
            "phone": p,
            "body": (x.get("body") or "")[:140],
            "created_at": x.get("created_at"),
            "contractor": {
                "id": c.get("id"),
                "name": c.get("name"),
                "metro": c.get("metro"),
                "niche": c.get("niche"),
                "active": c.get("active"),
                "trust_score": c.get("trust_score"),
                "completed_jobs": c.get("completed_jobs"),
            } if c else None,
            "sequence": {
                "status": s.get("status"),
                "current_step": s.get("current_step"),
                "last_sent_at": s.get("last_sent_at"),
            } if s else None,
        })
    return out




def register_pulse_routes(app, get_db: Optional[Callable] = None):
    """Mount all pulse + storm-trigger routes on the FastAPI app."""
    from fastapi.responses import HTMLResponse, JSONResponse

    if get_db is None:
        def get_db():
            return _sb()

    # ── Pulse JSON endpoints ────────────────────────────────────────────
    async def _summary():
        return JSONResponse(pulse_summary(get_db()))

    async def _sms_volume(hours: int = 24):
        return JSONResponse(pulse_sms_volume(get_db(), hours=hours))

    async def _leads_hot(limit: int = 25):
        return JSONResponse(pulse_leads_hot(get_db(), limit=limit))

    async def _reply_rate(days: int = 7):
        return JSONResponse(pulse_reply_rate(get_db(), days=days))

    async def _metro_heat(hours: int = 24):
        return JSONResponse(pulse_metro_heat(get_db(), hours=hours))

    async def _contractor_stats(limit: int = 20):
        return JSONResponse(pulse_contractor_stats(get_db(), limit=limit))

    async def _storm_stream(limit: int = 25):
        return JSONResponse(_get_storm_stream(get_db(), limit=limit))

    # ── HTML dashboard ─────────────────────────────────────────────────
    async def _dashboard():
        return HTMLResponse(_pulse_dashboard_html())

    # ── Storm trigger webhook ─────────────────────────────────────────
    async def _storm_webhook(payload: dict):
        """POST endpoint. Body: radar_target with urgency_score."""
        urgency = payload.get("urgency_score") or 0
        if urgency < STORM_TRIGGER_URGENCY:
            return JSONResponse({"fired": False, "reason": f"urgency {urgency} < {STORM_TRIGGER_URGENCY}"})
        result = _fan_out_storm_sms(get_db(), payload)
        return JSONResponse(result)

    app.add_api_route("/api/v1/pulse/summary", _summary, methods=["GET"])
    app.add_api_route("/api/v1/pulse/sms-volume", _sms_volume, methods=["GET"])
    app.add_api_route("/api/v1/pulse/leads-hot", _leads_hot, methods=["GET"])
    app.add_api_route("/api/v1/pulse/reply-rate", _reply_rate, methods=["GET"])
    app.add_api_route("/api/v1/pulse/metro-heat", _metro_heat, methods=["GET"])
    app.add_api_route("/api/v1/pulse/contractor-stats", _contractor_stats, methods=["GET"])
    app.add_api_route("/api/v1/pulse/storm-stream", _storm_stream, methods=["GET"])
    app.add_api_route("/pulse", _dashboard, methods=["GET"])
    app.add_api_route("/api/v1/webhook/storm-target", _storm_webhook, methods=["POST"])

    # Unified admin health: one endpoint, all 3 oversight layers + pm2 + vonage
    async def _admin_health_route():
        return JSONResponse(_admin_health(get_db()))
    app.add_api_route("/api/v1/admin/health", _admin_health_route, methods=["GET"])

    # Real replies: SMS from real contractors (excludes 555 sandbox)
    async def _real_replies_route(limit: int = 50, hours: int = 168):
        return JSONResponse(_real_replies(get_db(), limit=limit, hours=hours))
    app.add_api_route("/api/v1/pulse/replies", _real_replies_route, methods=["GET"])

    log.info("pulse routes registered: /pulse + 7 JSON endpoints + storm webhook")


# ── LEGACY SHIMS (used by hub.py:861 and hub.py:3589) ────────────────────
class PulseEngine:
    """Legacy shim. The old pulse engine was a stateful rollup object;
    the new system uses stateless JSON endpoints via register_pulse_routes.
    Kept here so hub.py:861 still constructs without error."""
    def __init__(self, get_db=None, refresh_interval_sec=300):
        self.get_db = get_db
        self.refresh_interval_sec = refresh_interval_sec
        self._cache = {}
    def get(self, key):
        return self._cache.get(key)
    def refresh(self):
        if not self.get_db:
            return
        try:
            self._cache = pulse_summary(self.get_db())
        except Exception as e:
            log.warning(f"PulseEngine.refresh failed: {e}")


def pulse_view_page() -> str:
    """Legacy shim. Old name for the /view/pulse HTML page. Returns
    the same dashboard HTML as /pulse."""
    return _pulse_dashboard_html()
