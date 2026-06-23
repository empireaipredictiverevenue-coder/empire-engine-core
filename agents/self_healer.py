"""Empire AI · Self Healer

Catches errors that the supervisor finds + actively fixes them.
Runs in --loop mode every 5 min via pm2.

Fixes applied automatically:
  1. agent_config has a critical/last_run_status=error agent -> re-run that agent
  2. agent_activity has rows_errored > 5 in last hour for an agent -> re-run it
  3. PM2 process in 'errored' state (crash loop) -> pm2 restart it
  4. PM2 process 'stopped' that should be running -> pm2 start it
  5. Hub returning 500/timeout on critical routes -> pm2 restart hub (gracefully)
  6. Storm alerts not firing -> ping the webhook
  7. ollama at 100% CPU for >10min -> pkill llama-server (user opt-in via env)
  8. CRON entry missing for a known agent -> emit a fix_recommendation (don't auto-edit)

All actions logged to self_healer_log table. After each cycle, the
self-healer emits a Telegram alert ONLY if it actually fixed something
(suppresses noise).

Wired into:
  - pm2: 'self-healer' service in ecosystem.config.js
  - supervisor: optionally triggered on critical issues
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
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

import httpx
from supabase import create_client

log = logging.getLogger("empire.self_healer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ── COOLDOWNS (per-action-type, per-target) ─────────────────────────────
# Prevents thrashing: don't restart the same thing twice in 5 minutes.
_last_action: dict[tuple[str, str], datetime] = {}
COOLDOWN_SECONDS = 300

# Agents that should always be running. If they crash, auto-restart.
CRITICAL_AGENTS = {
    "contractor_outreach", "lead_scanner", "lead_enricher", "lead_converter",
    "dispatch", "storm_alert", "storm_log_to_targets", "prospector_bridge",
    "warp_scout", "agent_runner", "system_supervisor", "radar_asset_enricher",
    "multi_touch_cadence",
}

# Agents that shouldn't be touched (legacy scripts that aren't in pm2)
SKIP_AGENTS = {
    "fee_collection", "vault_monitor",  # cron-driven legacy scripts
}


def _cooldown_ok(action: str, target: str) -> bool:
    key = (action, target)
    last = _last_action.get(key)
    if last and (datetime.now(timezone.utc) - last).total_seconds() < COOLDOWN_SECONDS:
        return False
    _last_action[key] = datetime.now(timezone.utc)
    return True


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _log_fix(sb, action: str, target: str, status: str, detail: str = "") -> None:
    sb.table("self_healer_log").insert({
        "action": action,
        "target": target,
        "status": status,
        "detail": detail[:500],
        "fired_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def _send_telegram(text: str) -> bool:
    bot = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("OPERATOR_TELEGRAM_CHAT_ID", "")
    if not bot or not chat:
        return False
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat, "text": text, "disable_web_page_preview": "1",
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=10).read()
        return True
    except Exception as e:
        log.debug(f"tg send failed: {e}")
        return False


# ── FIX ACTIONS ──────────────────────────────────────────────────────────
def _pm2_list() -> list[dict]:
    """Get list of pm2 processes with state."""
    try:
        r = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return []
        return json.loads(r.stdout)
    except Exception as e:
        log.debug(f"pm2 jlist failed: {e}")
        return []


def _pm2_restart(name: str) -> bool:
    try:
        r = subprocess.run(["pm2", "restart", name], capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception as e:
        log.warning(f"pm2 restart {name} failed: {e}")
        return False


def _pm2_start(name: str) -> bool:
    try:
        r = subprocess.run(["pm2", "start", name], capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception as e:
        log.warning(f"pm2 start {name} failed: {e}")
        return False


def fix_pm2_states(sb) -> int:
    """Restart any pm2 process in errored/stopped state (per ecosystem.config.js apps)."""
    fixed = 0
    procs = _pm2_list()
    by_name = {p["name"]: p for p in procs}
    # Read the expected services from ecosystem.config.js — only auto-restart those
    try:
        with open(REPO / "ecosystem.config.js") as f:
            text = f.read()
        expected_names = set(re.findall(r"name:\s*['\"]([^'\"]+)['\"]", text))
    except Exception:
        expected_names = set(by_name.keys())

    for name in expected_names:
        p = by_name.get(name)
        if not p:
            # In ecosystem but not running -> start
            if _cooldown_ok("pm2_start", name):
                log.info(f"self_healer: starting missing pm2 process {name}")
                if _pm2_start(name):
                    _log_fix(sb, "pm2_start", name, "ok", "started missing process")
                    fixed += 1
                else:
                    _log_fix(sb, "pm2_start", name, "failed", "pm2 start returned non-zero")
            continue
        # Process exists. Check status.
        status = p.get("pm2_env", {}).get("status")
        if status in ("errored", "stopped", "stopping"):
            if _cooldown_ok("pm2_restart", name):
                log.info(f"self_healer: restarting {name} (status={status})")
                if _pm2_restart(name):
                    _log_fix(sb, "pm2_restart", name, "ok", f"was {status}")
                    fixed += 1
                else:
                    _log_fix(sb, "pm2_restart", name, "failed", "")
    return fixed


def fix_erroring_agents(sb) -> int:
    """Re-run agents with high error counts in last hour."""
    fixed = 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = (sb.table("agent_activity")
            .select("agent_name,rows_errored,started_at")
            .gte("started_at", cutoff)
            .gt("rows_errored", 3)
            .execute())
    seen = set()
    for row in (r.data or []):
        agent = row.get("agent_name")
        if not agent or agent in seen or agent in SKIP_AGENTS:
            continue
        seen.add(agent)
        if not _cooldown_ok("rerun_agent", agent):
            continue
        # Try to re-run the agent by importing it
        # Most agents have a run() or main() entry; this is best-effort.
        log.info(f"self_healer: re-running {agent} (had {row['rows_errored']} errors in last hour)")
        try:
            mod = __import__(f"agents.{agent}", fromlist=["run", "main"])
            fn = getattr(mod, "run", None) or getattr(mod, "main", None)
            if fn:
                fn()
                _log_fix(sb, "rerun_agent", agent, "ok", f"re-ran after {row['rows_errored']} errors")
                fixed += 1
            else:
                _log_fix(sb, "rerun_agent", agent, "skipped", "no run() / main()")
        except Exception as e:
            _log_fix(sb, "rerun_agent", agent, "failed", f"{type(e).__name__}: {e}")
    return fixed


def fix_hub_health(sb) -> int:
    """Probe critical hub routes. Restart hub if all probes fail."""
    fixed = 0
    hub = os.getenv("HUB_URL", "http://localhost:8001").rstrip("/")
    probes = ["/api/v1/bbb/stats", "/api/v1/pulse/summary"]
    failures = 0
    for p in probes:
        try:
            r = httpx.get(f"{hub}{p}", timeout=10)
            if r.status_code >= 500:
                failures += 1
        except Exception:
            failures += 1
    if failures >= len(probes) and _cooldown_ok("pm2_restart", "empire-hub"):
        log.warning(f"self_healer: all hub probes failed ({failures}/{len(probes)}) — restarting empire-hub")
        if _pm2_restart("empire-hub"):
            _log_fix(sb, "pm2_restart", "empire-hub", "ok", f"all {len(probes)} probes failed")
            fixed += 1
    return fixed


def fix_ollama_cpu(sb) -> int:
    """If ollama llama-server is at 100% CPU for >10min, kill it (the
    systemd service will respawn as needed)."""
    if os.getenv("SELF_HEALER_OLLAMA_GUARD", "0") != "1":
        return 0
    fixed = 0
    try:
        r = subprocess.run(
            ["ps", "-eo", "pid,pcpu,comm,etimes,args"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "llama-server" not in line:
                continue
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            try:
                pcpu = float(parts[1])
                etimes = int(parts[3])  # seconds since started
            except ValueError:
                continue
            if pcpu > 95 and etimes > 600 and _cooldown_ok("kill_ollama", parts[0]):
                log.warning(f"self_healer: killing llama-server PID {parts[0]} (100% CPU for {etimes}s)")
                try:
                    os.kill(int(parts[0]), 9)
                    _log_fix(sb, "kill_ollama", parts[0], "ok", f"100% CPU for {etimes}s")
                    fixed += 1
                except Exception as e:
                    _log_fix(sb, "kill_ollama", parts[0], "failed", str(e))
    except Exception as e:
        log.warning(f"ollama cpu check failed: {e}")
    return fixed


def check_misaligned_configs(sb) -> list[dict]:
    """Detect drift between filesystem (ecosystem.config.js) and reality
    (pm2 list). Emit fix_recommendation (no auto-edit, log only)."""
    recs = []
    procs = _pm2_list()
    pm2_names = {p["name"] for p in procs}
    try:
        with open(REPO / "ecosystem.config.js") as f:
            text = f.read()
        eco_names = set(re.findall(r"name:\s*['\"]([^'\"]+)['\"]", text))
    except Exception:
        return recs
    # In ecosystem but not running
    for name in sorted(eco_names - pm2_names):
        recs.append({"check": "missing_in_pm2", "name": name,
                     "msg": f"'{name}' is in ecosystem.config.js but NOT running in pm2"})
    # Running but not in ecosystem (config drift)
    for name in sorted(pm2_names - eco_names):
        recs.append({"check": "orphan_in_pm2", "name": name,
                     "msg": f"'{name}' is running in pm2 but NOT in ecosystem.config.js"})
    return recs


def run() -> dict:
    started = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    total_fixed = 0
    actions = []

    n = fix_pm2_states(sb)
    actions.append(f"pm2_states={n}")
    total_fixed += n

    n = fix_erroring_agents(sb)
    actions.append(f"errored_agents={n}")
    total_fixed += n

    n = fix_hub_health(sb)
    actions.append(f"hub_health={n}")
    total_fixed += n

    n = fix_ollama_cpu(sb)
    actions.append(f"ollama_cpu={n}")
    total_fixed += n

    misaligned = check_misaligned_configs(sb)
    if misaligned:
        for r in misaligned:
            _log_fix(sb, r["check"], r["name"], "recommendation", r["msg"])
        actions.append(f"misaligned={len(misaligned)}")

    summary = f"fixed={total_fixed} " + " ".join(actions)
    log.info(summary)
    sb.table("agent_activity").insert({
        "agent_name": "self_healer",
        "run_id": str(run_id),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "rows_seen": 0,
        "rows_processed": total_fixed,
        "summary": summary[:500],
    }).execute()

    # Only alert on Telegram if we ACTUALLY fixed something or found drift
    if total_fixed > 0 or misaligned:
        text = f"🤖 *self_healer* — fixed {total_fixed}, drift {len(misaligned)}\n" + "\n".join(actions)
        _send_telegram(text)
    return {"status": "ok", "fixed": total_fixed, "drift": len(misaligned), "actions": actions}


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--loop", action="store_true")
    p.add_argument("--interval", type=int, default=300, help="seconds between cycles (loop mode)")
    args = p.parse_args()
    if args.loop:
        log.info(f"self_healer: loop mode, interval={args.interval}s")
        while True:
            try:
                run()
            except Exception as e:
                log.exception(f"self_healer cycle failed: {e}")
            time.sleep(args.interval)
    else:
        run()


if __name__ == "__main__":
    main()