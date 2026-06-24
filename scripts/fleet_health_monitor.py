#!/usr/bin/env python3
"""Fleet Health Monitor — Telegram alert when any PM2 service exceeds restart thresholds.

Usage:
    python3 scripts/fleet_health_monitor.py              # standard check
    python3 scripts/fleet_health_monitor.py --force      # force alert even if healthy
    python3 scripts/fleet_health_monitor.py --dry-run    # print instead of sending

Cron: */15 * * * * cd /root/empire-v49 && python3 scripts/fleet_health_monitor.py

Checks:
  - Any service with >5 total restarts in last 24 hours → WARN
  - Any service currently stopped/errored → CRITICAL
  - Any service with >50 total restarts overall → STALE
  - Current cpu / memory per service
"""

import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [health] %(message)s")
log = logging.getLogger("fleet_health")

ALERT_THRESHOLD_24H = 5     # restarts in 24h → WARN
STALE_THRESHOLD_TOTAL = 50  # total restarts → STALE
HEALTH_FILE = Path("/tmp/fleet_health_state.json")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_HOME_CHANNEL",
                                os.environ.get("TELEGRAM_CHAT", "808657420"))


def get_pm2_services() -> list[dict]:
    """Parse PM2 jlist and return a list of service dicts with restart stats."""
    try:
        r = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            log.warning(f"pm2 jlist failed: {r.stderr[:200]}")
            return []
        data = json.loads(r.stdout)
        if not isinstance(data, list):
            return []
    except Exception as e:
        log.warning(f"pm2 jlist parse error: {e}")
        return []

    services = []
    now_ms = time.time() * 1000

    for p in data:
        env = p.get("pm2_env", {})
        name = p.get("name", "unknown")
        status = env.get("status", "unknown")
        created_ms = env.get("created_at", 0)
        restarts = env.get("unstable_restarts", 0)
        uptime_ms = env.get("pm_uptime", 0)
        monit = p.get("monit", {})
        memory = monit.get("memory", 0)
        cpu = monit.get("cpu", 0)

        # Calculate age and restart rate
        age_hours = (now_ms - created_ms) / 3600000 if created_ms else 0
        age_days = age_hours / 24 if age_hours > 0 else 0
        restarts_per_24h = restarts / max(age_days, 0.05)  # normalized to 24h

        # Determine alert level
        alerts = []
        if status not in ("online", "launching"):
            alerts.append(f"CRITICAL: status={status}")

        if restarts >= STALE_THRESHOLD_TOTAL:
            alerts.append(f"STALE: {restarts} total restarts in {age_days:.0f}d")

        if restarts_per_24h >= ALERT_THRESHOLD_24H and age_hours > 1:
            alerts.append(f"WARN: ~{restarts_per_24h:.0f} restarts/24h ({restarts} total)")

        services.append({
            "name": name,
            "status": status,
            "restarts": restarts,
            "restarts_per_24h": round(restarts_per_24h, 1),
            "age_hours": round(age_hours, 1),
            "uptime_hours": round(uptime_ms / 3600000, 1),
            "memory_mb": round(memory / 1024 / 1024, 1),
            "cpu_pct": cpu,
            "alerts": alerts,
        })

    return services


def format_alert(services: list[dict]) -> str:
    """Build a Telegram message from the service list."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 *Fleet Health — {now}*", ""]

    # Services with alerts first
    alerted = [s for s in services if s["alerts"]]
    healthy = [s for s in services if not s["alerts"]]

    if alerted:
        lines.append(f"⚠️ *{len(alerted)} service(s) need attention:*")
        lines.append("")
        for s in alerted:
            for alert in s["alerts"]:
                emoji = "🔴" if "CRITICAL" in alert else "🟡" if "WARN" in alert else "⚪"
                lines.append(f"{emoji} *{s['name']}*")
                lines.append(f"   {alert}")
                lines.append(f"   memory={s['memory_mb']}MB cpu={s['cpu_pct']}% "
                             f"uptime={s['uptime_hours']}h")
        lines.append("")

    # Summary counts
    total = len(services)
    online = sum(1 for s in services if s["status"] == "online")
    errored = sum(1 for s in services if s["status"] not in ("online", "launching"))
    lines.append(f"*Stats:* {online}/{total} online")
    if errored:
        lines.append(f"*{errored} service(s) not running*")

    # Top memory consumers (if no critical alerts)
    if not alerted:
        by_mem = sorted(healthy, key=lambda s: -s["memory_mb"])[:5]
        lines.append("")
        lines.append("*Top memory:*")
        for s in by_mem:
            if s["memory_mb"] > 50:
                lines.append(f"  {s['name']}: {s['memory_mb']}MB")

    return "\n".join(lines)


def send_telegram(text: str, dry_run: bool = False) -> int:
    """Send a Telegram message. Returns HTTP status code."""
    if dry_run:
        print(text)
        return 200

    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — cannot alert")
        return 0

    import httpx
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        log.info(f"telegram alert: HTTP {r.status_code}")
        return r.status_code
    except Exception as e:
        log.warning(f"telegram send failed: {e}")
        return 0


def run(dry_run: bool = False, force: bool = False) -> dict:
    """Run the health check and alert if needed."""
    services = get_pm2_services()
    if not services:
        msg = "⚠️ Fleet health monitor: could not query PM2"
        status = 200
    else:
        alerted = [s for s in services if s["alerts"]]
        if alerted or force:
            text = format_alert(services)
            status = send_telegram(text, dry_run=dry_run)
        else:
            log.info(f"Fleet healthy: {sum(1 for s in services if s['status']=='online')}/"
                     f"{len(services)} online, 0 alerts")
            status = 0

    # Save state
    state = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_services": len(services),
        "online": sum(1 for s in services if s["status"] == "online"),
        "with_alerts": len([s for s in services if s["alerts"]]),
        "alerted": [s["name"] for s in services if s["alerts"]],
    }
    try:
        HEALTH_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass

    return {"ok": True, "status": status, "services": len(services),
            "online": state["online"], "alerts": state["with_alerts"]}


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    result = run(dry_run=dry_run, force=force)
    log.info(f"Health check: {result['online']}/{result['services']} online, "
             f"{result['alerts']} alerts")


if __name__ == "__main__":
    main()
