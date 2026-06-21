#!/usr/bin/env python3
"""
EMPIRE V49 · AUTONOMOUS SUPERVISOR
===================================
The central self-healing loop that makes the entire agent fleet run
autonomously. Monitors PM2 services, runs loop agent evolution cycles,
restarts failed processes, scans agents for security vulnerabilities
via SkillSpector, and reports fleet health.

Runs under PM2 as 'autonomous-supervisor'.
"""

import os
import sys
import json
import time
import subprocess
import logging
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("empire.supervisor")

# ── Configuration ────────────────────────────────────────────────────
_HEALTH_CHECK_INTERVAL = 60  # seconds between health checks
_EVOLUTION_INTERVAL = 300     # seconds between loop agent evolution cycles
_SKILLSPECTOR_INTERVAL = 21600  # seconds between agent security scans (6 hours)
_HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8001")
_HUB_TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")
_PM2_BIN = "pm2"

# Supabase client (lazy-init)
_sb = None
def _get_sb():
    global _sb
    if _sb is None:
        load_dotenv("/root/.env", override=True)
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if url and key:
            _sb = create_client(url, key)
    return _sb


async def _register_self():
    """Register the autonomous supervisor in the agent registry heartbeat."""
    try:
        sb = _get_sb()
        if not sb:
            return
        sb.table("agent_registry").upsert({
            "agent_name": "autonomous_supervisor",
            "role_name": "cron_controller",
            "status": "ACTIVE",
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": [
                "monitor_fleet_health", "auto_restart_services",
                "trigger_evolution", "orchestrate_agents",
                "scan_agent_security",
            ],
            "task_types": [
                "supervisor.health_check", "supervisor.evolution",
                "supervisor.restart", "supervisor.skillspector_scan",
            ],
        }, on_conflict="agent_name").execute()
        log.debug("[supervisor] registered heartbeat in agent_registry")
    except Exception as e:
        log.debug(f"[supervisor] registry heartbeat failed: {e}")


# Services we expect to be running under PM2 (synced to actual fleet 2026-06-21)
_EXPECTED_SERVICES = [
    "empire-hub",
    "agent-runner",
    "vonage-engineer",
    "vault-monitor",
    "daily-revenue",
    "email-pulse-monitor",
    "seo-agent",
    "space-reasoner",
    "stop-loss-bot",
    "trading-bot",
    "trading-stoploss",
    "traffic-specialist",
    "affiliate-recruiter",
]

# Services that are allowed to be offline (non-critical — won't auto-restart)
_OPTIONAL_SERVICES = {"autonomous-supervisor"}


# ── PM2 Helpers ──────────────────────────────────────────────────────

def _run_pm2(args: list[str]) -> dict:
    """Run a PM2 command and return parsed output."""
    try:
        r = subprocess.run(
            [_PM2_BIN] + args,
            capture_output=True, text=True, timeout=30,
        )
        return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "pm2 not found"}


def get_pm2_status() -> list[dict]:
    """Get status of all PM2-managed processes."""
    r = _run_pm2(["jlist", "--no-color"])
    if not r["ok"]:
        log.warning(f"[supervisor] pm2 jlist failed: {r.get('stderr', '')}")
        return []
    try:
        processes = json.loads(r["stdout"]) if r["stdout"] else []
        return processes if isinstance(processes, list) else []
    except json.JSONDecodeError as e:
        log.warning(f"[supervisor] pm2 jlist parse error: {e}")
        return []


def restart_service(name: str) -> bool:
    """Restart a PM2 service."""
    r = _run_pm2(["restart", name])
    if r["ok"]:
        log.info(f"[supervisor] restarted service: {name}")
    else:
        log.error(f"[supervisor] failed to restart {name}: {r.get('stderr', '')}")
    return r["ok"]


# ── Health Checks ────────────────────────────────────────────────────

def check_service_health(service_name: str, processes: list[dict]) -> dict:
    """Check if a specific service is healthy."""
    for proc in processes:
        name = proc.get("name", "")
        if name == service_name:
            pm2_env = proc.get("pm2_env", {})
            status = pm2_env.get("status", "unknown")
            restart_count = pm2_env.get("restart_time", 0)
            uptime_ms = pm2_env.get("pm_uptime", 0)
            uptime_s = (time.time() * 1000 - uptime_ms) // 1000 if uptime_ms else 0
            # monit is at the top level of the process object, not nested in pm2_env
            monit = proc.get("monit", {})
            memory_bytes = monit.get("memory", 0) if isinstance(monit, dict) else 0
            return {
                "name": name,
                "status": status,
                "online": status == "online",
                "restarts": restart_count,
                "uptime_s": uptime_s,
                "memory_mb": round(memory_bytes / (1024 * 1024), 1),
            }
    return {"name": service_name, "status": "not_found", "online": False}


async def health_cycle() -> dict:
    """Run one health check cycle across all services."""
    processes = get_pm2_status()
    results = {}

    for svc in _EXPECTED_SERVICES:
        health = check_service_health(svc, processes)
        results[svc] = health
        if not health["online"] and svc not in _OPTIONAL_SERVICES:
            log.warning(f"[supervisor] {svc} is down! restarting...")
            restart_service(svc)

    # Summary
    total = len(_EXPECTED_SERVICES)
    online = sum(1 for r in results.values() if r.get("online"))
    unhealthy = [s for s, r in results.items() if not r.get("online") and s not in _OPTIONAL_SERVICES]

    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "services_checked": total,
        "services_online": online,
        "services_offline": total - online,
        "critical_unhealthy": unhealthy,
        "details": results,
    }

    if unhealthy:
        log.warning(f"[supervisor] {len(unhealthy)} critical service(s) unhealthy: {unhealthy}")
    else:
        log.info(f"[supervisor] health OK ({online}/{total} online)")

    return report


# ── Loop Agent Integration ──────────────────────────────────────────

async def run_evolution_cycle() -> dict:
    """Trigger the loop agent's self-evolution cycle via the hub API."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{_HUB_URL}/api/loop/evolve",
                json={"force": False},
                headers={"Authorization": f"Bearer {_HUB_TOKEN}"},
            )
            if r.status_code == 200:
                data = r.json()
                events = data.get("events", [])
                log.info(f"[supervisor] evolution cycle: {len(events)} events")
                return {"ok": True, "events": events, "count": len(events)}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        log.warning(f"[supervisor] evolution API call failed: {e}")
        return {"ok": False, "error": str(e)[:100]}


async def run_learning_cycle() -> dict:
    """Check loop agent learning status."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{_HUB_URL}/api/loop/learning-status",
                headers={"Authorization": f"Bearer {_HUB_TOKEN}"},
            )
            if r.status_code == 200:
                data = r.json()
                log.info(f"[supervisor] learning: {data.get('total_runs_tracked', 0)} runs tracked")
                return {"ok": True, "status": data}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        log.warning(f"[supervisor] learning cycle API call failed: {e}")
        return {"ok": False, "error": str(e)[:100]}


# ── SkillSpector Security Scan Integration ────────────────────────────

async def _scan_agent_security() -> dict:
    """Run SkillSpector static analysis on all agent Python files.

    Scans bots/ and agents/ directories for 347 vulnerability patterns
    across 10 categories (prompt injection, data exfiltration,
    privilege escalation, etc.).

    Logs findings to agent_activity and fires Telegram alerts on
    CRITICAL or HIGH severity findings.
    """
    from pathlib import Path

    try:
        from bots.skillspector_bridge import (
            scan_all_agents, summarize_findings, _clear_pattern_cache,
        )
    except ImportError as e:
        log.warning(f"[supervisor] skillspector_bridge import failed: {e}")
        return {"ok": False, "error": f"import error: {e}"}

    # Clear cache so pattern updates are picked up
    _clear_pattern_cache()

    repo = Path(__file__).resolve().parent
    agent_dirs = [
        str(repo / "bots"),
        str(repo / "agents"),
    ]

    log.info("[supervisor] running SkillSpector agent security scan...")
    try:
        findings = scan_all_agents(agent_dirs)
    except Exception as e:
        log.error(f"[supervisor] SkillSpector scan_all_agents failed: {e}")
        return {"ok": False, "error": f"scan failed: {e}"}
    summary = summarize_findings(findings)

    log.info(
        f"[supervisor] SkillSpector scan complete: "
        f"{summary['files_scanned']} files, "
        f"{summary['total_findings']} findings "
        f"(C:{summary['by_severity'].get('CRITICAL',0)} "
        f"H:{summary['by_severity'].get('HIGH',0)} "
        f"M:{summary['by_severity'].get('MEDIUM',0)} "
        f"L:{summary['by_severity'].get('LOW',0)})"
    )

    # ── Log to agent_activity ───────────────────────────────────────
    sb = _get_sb()
    if sb:
        try:
            import uuid
            sb.table("agent_activity").insert({
                "agent_name": "skillspector_bridge",
                "run_id": str(uuid.uuid4()),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": "error" if summary["critical_findings"] else (
                    "error" if summary["total_findings"] > 0 else "ok"
                ),
                "rows_seen": summary["files_scanned"],
                "rows_processed": summary["files_scanned"],
                "rows_errored": 0,
                "summary": (
                    f"SkillSpector scan: {summary['files_scanned']} files, "
                    f"{summary['total_findings']} findings "
                    f"(C:{summary['by_severity'].get('CRITICAL',0)} "
                    f"H:{summary['by_severity'].get('HIGH',0)})"
                ),
                "meta": {
                    "scan_type": "skillspector_static_analysis",
                    "files_scanned": summary["files_scanned"],
                    "total_findings": summary["total_findings"],
                    "by_severity": summary["by_severity"],
                    "by_category": summary["by_category"],
                    "critical_findings": summary["critical_findings"][:20],
                    "verdict": summary["verdict"],
                },
            }).execute()
            log.debug("[supervisor] SkillSpector results logged to agent_activity")
        except Exception as e:
            log.warning(f"[supervisor] agent_activity log failed: {e}")

    # ── Telegram alert on CRITICAL findings only (HIGH are 100% false positives) ──
    crit_count = len(summary["critical_findings"])
    if crit_count > 0:
        await _send_skillspector_alert(summary)

    return {"ok": True, "summary": summary}


async def _send_skillspector_alert(summary: dict) -> None:
    """Send a Telegram alert about SkillSpector findings."""
    try:
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
        if not tg_token:
            return

        critical = summary["critical_findings"]
        high_count = summary["by_severity"].get("HIGH", 0)

        lines = [
            "\ud83d\udd10 *SkillSpector Security Scan*",
            f"  Files scanned: {summary['files_scanned']}",
            f"  Total findings: {summary['total_findings']}",
            f"  Critical: {len(critical)}  High: {high_count}",
            "",
        ]

        if critical:
            lines.append("*Critical findings:*")
            for cf in critical[:5]:
                fname = cf["file"].rsplit("/", 1)[-1] if "/" in cf["file"] else cf["file"]
                lines.append(f"  \u2022 {fname}:{cf['line']} \u2014 {cf['message'][:100]}")
            if len(critical) > 5:
                lines.append(f"  \u2026 and {len(critical) - 5} more")

        alert = "\n".join(lines)

        import urllib.request as _ur
        payload_json = json.dumps({
            "chat_id": tg_chat,
            "text": alert,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode()
        req = _ur.Request(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            data=payload_json,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=10)
        log.info("[supervisor] SkillSpector alert sent to Telegram")
    except Exception as e:
        log.warning(f"[supervisor] SkillSpector Telegram alert failed: {e}")


# ── Main Autonomous Loop ────────────────────────────────────────────

async def autonomous_loop():
    """Main autonomous supervisor loop."""
    log.info("[supervisor] === AUTONOMOUS SUPERVISOR STARTING ===")
    log.info(f"[supervisor] health interval: {_HEALTH_CHECK_INTERVAL}s")
    log.info(f"[supervisor] evolution interval: {_EVOLUTION_INTERVAL}s")

    # Register self in agent registry
    await _register_self()

    # Track time since last evolution and last SkillSpector scan
    last_evolution = 0
    last_skillspector = time.time()  # delay first scan (won't fire immediately)
    cycle_count = 0
    heartbeat_every = 5  # beats every 5 cycles (5 min)

    while True:
        cycle_count += 1
        now = time.time()

        try:
            # Always run health check
            health_report = await health_cycle()

            # Heartbeat every N cycles
            if cycle_count % heartbeat_every == 0:
                await _register_self()

            # Run evolution cycle periodically
            if (now - last_evolution) >= _EVOLUTION_INTERVAL:
                await run_evolution_cycle()
                await run_learning_cycle()
                last_evolution = now

            # Run SkillSpector security scan periodically
            if (now - last_skillspector) >= _SKILLSPECTOR_INTERVAL:
                await _scan_agent_security()
                last_skillspector = now

            # Log cycle summary
            if cycle_count % 10 == 0:
                log.info(f"[supervisor] {cycle_count} cycles completed - fleet stable")

        except Exception as e:
            log.error(f"[supervisor] cycle error: {e}")

        await asyncio.sleep(_HEALTH_CHECK_INTERVAL)


async def main():
    """Entry point."""
    try:
        await autonomous_loop()
    except asyncio.CancelledError:
        log.info("[supervisor] shutdown requested")
    except KeyboardInterrupt:
        log.info("[supervisor] keyboard interrupt")


if __name__ == "__main__":
    asyncio.run(main())
