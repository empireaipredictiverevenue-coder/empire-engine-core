"""
EMPIRE V49 - OVERSEER AGENT
============================
Monitors the agent mesh + key health signals, writes a consolidated status report.
The visibility layer: catches dead agents, stale data, brain-down - the stuff that
silently broke before (reddit 401s, orphaned orchestrator). Runs as a mesh agent.

Reads: agent_registry (mesh writes ACTIVE/ERROR), storm_forecasts (freshness), call_logs.
Checks: brain (Ollama) reachable. Writes: system_health row + prints a summary each cycle.
"""
import os, sys, time, json, traceback
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "/root/empire-v49")
from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)
from supabase import create_client
import requests

INTERVAL = 600  # report every 10 min
_db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

def _check_brain():
    """Is the local brain (Ollama) up?"""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def _agent_health():
    """Read agent_registry: which agents are ACTIVE vs ERROR, and last ping age."""
    try:
        rows = _db.table("agent_registry").select("agent_name,status,last_ping,enabled").execute().data or []
        out = []
        now = datetime.now(timezone.utc)
        for r in rows:
            age_min = None
            lp = r.get("last_ping")
            if lp:
                try:
                    t = datetime.fromisoformat(lp.replace("Z", "+00:00"))
                    age_min = round((now - t).total_seconds() / 60, 1)
                except Exception:
                    pass
            out.append({"agent": r.get("agent_name"), "status": r.get("status"), "ping_age_min": age_min})
        return out
    except Exception as e:
        return [{"error": str(e)[:80]}]

def _storm_fresh():
    """Is storm forecast data fresh (predictor running)?"""
    try:
        rows = _db.table("storm_forecasts").select("id", count="exact").execute()
        return rows.count or 0
    except Exception as e:
        return f"err: {str(e)[:50]}"

def _call_stats():
    """Real funnel: calls + qualified today."""
    try:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = _db.table("call_logs").select("qualified", count="exact").gte("created_at", today).execute()
        total = rows.count or 0
        qual = sum(1 for r in (rows.data or []) if r.get("qualified"))
        return {"calls_today": total, "qualified_today": qual}
    except Exception as e:
        return {"error": str(e)[:50]}

def build_report():
    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "brain_up": _check_brain(),
        "agents": _agent_health(),
        "storm_forecasts_count": _storm_fresh(),
        "funnel": _call_stats(),
    }
    return report

def run():
    print("[OVERSEER] starting (mesh + health monitor)")
    while True:
        try:
            report = build_report()
            # console summary
            agents = report["agents"]
            active = [a["agent"] for a in agents if a.get("status") == "ACTIVE"]
            errored = [a["agent"] for a in agents if a.get("status") == "ERROR"]
            print(f"[OVERSEER] brain={'UP' if report['brain_up'] else 'DOWN'} | active={active} | errored={errored} | funnel={report['funnel']}")
            # persist (best-effort; table optional)
            try:
                _db.table("system_health").insert({"report": json.dumps(report), "created_at": report["ts"]}).execute()
            except Exception:
                pass  # table may not exist; console report still works
        except Exception:
            print(f"[OVERSEER] error: {traceback.format_exc()}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    import json as _j
    print(_j.dumps(build_report(), indent=2))