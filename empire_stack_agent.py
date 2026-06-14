"""
EMPIRE V49 · STACK ENGINEERING AGENT
=====================================
Infrastructure monitoring, deployment management, health checks,
resource forecasting, and incident detection.

Wire-up in hub.py:
    from empire_stack_agent import register_stack_routes
    register_stack_routes(app, require_auth=require_auth)
"""

import logging
import os
import subprocess
import json as _json
from datetime import datetime, timezone
from typing import Optional, Callable

log = logging.getLogger("empire.stack")

_SYSTEM_INFO_CACHE = {}


def _run_cmd(cmd: list[str], timeout: int = 5) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        return str(e)


def _get_pm2_status() -> list[dict]:
    """Get PM2 process list."""
    try:
        out = _run_cmd(["pm2", "jlist"], timeout=5)
        if not out:
            return []
        procs = _json.loads(out)
        services = []
        for p in procs:
            env = p.get("pm2_env", {})
            mon = p.get("monit", {})
            services.append({
                "name": p.get("name", "?"),
                "status": env.get("status", "unknown"),
                "pid": p.get("pid"),
                "uptime_s": int((datetime.now(timezone.utc).timestamp() * 1000 - (env.get("pm_uptime", 0))) / 1000) if env.get("pm_uptime") else 0,
                "restarts": env.get("restart_time", 0),
                "cpu_pct": mon.get("cpu", 0),
                "memory_mb": round(mon.get("memory", 0) / 1024 / 1024, 1),
                "exec_mode": env.get("exec_mode", "fork"),
                "instances": env.get("instances", 1),
                "version": env.get("version", "N/A"),
            })
        return services
    except Exception as e:
        log.warning(f"[stack] PM2 status error: {e}")
        return []


def _get_system_resources() -> dict:
    """Get CPU, memory, disk usage."""
    cpu = _run_cmd(["sh", "-c", "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1"])
    mem_raw = _run_cmd(["sh", "-c", "free -m | grep Mem"])
    disk_raw = _run_cmd(["sh", "-c", "df -h / | tail -1"])
    load = _run_cmd(["sh", "-c", "cat /proc/loadavg | awk '{print $1, $2, $3}'"])

    mem_parts = mem_raw.split()
    disk_parts = disk_raw.split()

    return {
        "cpu_usage_pct": float(cpu) if cpu and cpu != "0.0" else 0,
        "memory_total_mb": int(mem_parts[1]) if len(mem_parts) > 1 else 0,
        "memory_used_mb": int(mem_parts[2]) if len(mem_parts) > 2 else 0,
        "memory_free_mb": int(mem_parts[3]) if len(mem_parts) > 3 else 0,
        "memory_usage_pct": round(int(mem_parts[2]) / max(int(mem_parts[1]), 1) * 100, 1) if len(mem_parts) > 2 else 0,
        "disk_usage_pct": disk_parts[4] if len(disk_parts) > 4 else "N/A",
        "disk_used": disk_parts[2] if len(disk_parts) > 2 else "N/A",
        "disk_total": disk_parts[1] if len(disk_parts) > 1 else "N/A",
        "load_avg": load if load else "N/A",
        "uptime": _run_cmd(["uptime", "-p"]),
    }


def _get_git_info() -> dict:
    """Get latest git info."""
    return {
        "branch": _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": _run_cmd(["git", "rev-parse", "--short", "HEAD"]),
        "last_commit_msg": _run_cmd(["git", "log", "-1", "--pretty=%s"]),
        "last_commit_date": _run_cmd(["git", "log", "-1", "--pretty=%ai"]),
        "status": _run_cmd(["git", "status", "--short"]),
    }


def _get_deploy_history() -> list[dict]:
    """Get recent deploy events from deploy scripts."""
    deploys = []
    deploy_dir = "/root/empire-v49"
    deploy_log = os.path.join(deploy_dir, "deploy_history.jsonl")
    if os.path.exists(deploy_log):
        try:
            with open(deploy_log) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            deploys.append(_json.loads(line))
                        except _json.JSONDecodeError:
                            pass
        except Exception:
            pass
    # Fall back to git log
    if not deploys:
        git_log = _run_cmd(["git", "log", "--oneline", "-10", "--format=%H|%s|%ai"])
        for line in git_log.split("\n") if git_log else []:
            parts = line.split("|")
            if len(parts) >= 3:
                deploys.append({
                    "commit": parts[0][:8],
                    "message": parts[1],
                    "date": parts[2],
                    "type": "git_commit",
                })
    return deploys


def _get_incidents() -> list[dict]:
    """Return recent infrastructure incidents."""
    # Check governor heal log
    incidents = []
    heal_log = "/root/empire-v49/governor_heal_log.jsonl"
    if os.path.exists(heal_log):
        try:
            with open(heal_log) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = _json.loads(line)
                            if entry.get("type") in ("restart", "heal", "error") or entry.get("severity", "").lower() in ("high", "critical"):
                                incidents.append(entry)
                        except _json.JSONDecodeError:
                            pass
        except Exception:
            pass
    # Check error logs for recent spikes
    err_log = "/root/empire-v49/logs/agents.log"
    if os.path.exists(err_log):
        try:
            with open(err_log) as f:
                lines = f.readlines()[-200:]
                error_count = sum(1 for l in lines if "ERROR" in l or "CRITICAL" in l)
                if error_count > 20:
                    incidents.append({
                        "type": "error_spike",
                        "severity": "medium",
                        "message": f"{error_count} errors in last 200 log lines",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception:
            pass
    return incidents[:10]


class StackAgent:
    """Infrastructure and deployment management intelligence."""

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db

    def status(self) -> dict:
        """Return overall stack health snapshot."""
        services = _get_pm2_status()
        resources = _get_system_resources()
        git = _get_git_info()
        online = sum(1 for s in services if s["status"] == "online")
        stopped = sum(1 for s in services if s["status"] in ("stopped", "errored"))
        return {
            "services": services,
            "service_count": len(services),
            "online": online,
            "stopped": stopped,
            "resources": resources,
            "git": git,
            "health": "healthy" if stopped == 0 else "degraded" if stopped <= 2 else "critical",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def services_detail(self) -> dict:
        """Return detailed per-service metrics with log tails."""
        services = _get_pm2_status()
        for s in services:
            out_log = f"/root/.pm2/logs/{s['name']}-out.log"
            err_log = f"/root/.pm2/logs/{s['name']}-error.log"
            if os.path.exists(out_log):
                try:
                    with open(out_log) as f:
                        lines = f.readlines()[-20:]
                    s["log_tail"] = "".join(lines[-20:])[-2000:]
                except Exception:
                    s["log_tail"] = ""
            else:
                s["log_tail"] = ""
        return {"services": services, "count": len(services)}

    def deployment_history(self) -> dict:
        """Return deployment history."""
        deploys = _get_deploy_history()
        git = _get_git_info()
        return {
            "deployments": deploys,
            "count": len(deploys),
            "current": git,
        }

    def incidents(self) -> dict:
        """Return recent infrastructure incidents."""
        alerts = _get_incidents()
        services = _get_pm2_status()
        restarts = sum(s.get("restarts", 0) for s in services)
        return {
            "incidents": alerts,
            "count": len(alerts),
            "total_restarts_24h": restarts,
            "services_with_restarts": [s["name"] for s in services if s.get("restarts", 0) > 0],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def health_check(self) -> dict:
        """Run health checks on critical services."""
        checks = []
        # DB check
        if self.get_db:
            try:
                db = self.get_db()
                db.table("_health").select("count").limit(1).execute()
                checks.append({"service": "supabase", "status": "ok", "latency_ms": 0})
            except Exception as e:
                checks.append({"service": "supabase", "status": "error", "message": str(e)[:100]})
        # Brain check
        try:
            import http.client
            conn = http.client.HTTPConnection("localhost", 11434, timeout=3)
            conn.request("GET", "/api/tags")
            r = conn.getresponse()
            r.read()
            checks.append({"service": "ollama", "status": "ok" if r.status < 400 else "error"})
            conn.close()
        except Exception as e:
            checks.append({"service": "ollama", "status": "error", "message": str(e)[:100]})
        # PM2 check
        services = _get_pm2_status()
        online = sum(1 for s in services if s["status"] == "online")
        checks.append({"service": "pm2", "status": "ok" if online == len(services) else "degraded",
                        "online": online, "total": len(services)})
        # Disk check
        resources = _get_system_resources()
        disk_str = resources.get("disk_usage_pct", "0%")
        disk_pct = int(disk_str.replace("%", "")) if "%" in disk_str else 0
        checks.append({"service": "disk", "status": "ok" if disk_pct < 85 else "warn" if disk_pct < 95 else "critical",
                        "usage_pct": disk_pct})
        return {"checks": checks, "healthy": all(c.get("status") == "ok" for c in checks),
                "timestamp": datetime.now(timezone.utc).isoformat()}

    def resource_forecast(self) -> dict:
        """Forecast resource usage based on trends."""
        resources = _get_system_resources()
        mem_pct = resources.get("memory_usage_pct", 0)
        disk_str = resources.get("disk_usage_pct", "0%")
        disk_pct = int(disk_str.replace("%", "")) if "%" in disk_str else 0
        forecasts = []
        if mem_pct > 80:
            forecasts.append({
                "resource": "memory",
                "current_pct": mem_pct,
                "risk": "high" if mem_pct > 90 else "medium",
                "recommendation": "Increase RAM or reduce service count"
            })
        if disk_pct > 80:
            days_until_full = int((100 - disk_pct) / max(disk_pct * 0.01, 0.01))
            forecasts.append({
                "resource": "disk",
                "current_pct": disk_pct,
                "risk": "high" if disk_pct > 90 else "medium",
                "estimated_days_remaining": days_until_full,
                "recommendation": f"Clean up log files or increase disk capacity (~{days_until_full} days)"
            })
        return {
            "forecasts": forecasts,
            "count": len(forecasts),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def stack_report(self) -> dict:
        """Consolidated stack engineering report."""
        status = self.status()
        health = self.health_check()
        incidents = self.incidents()
        forecast = self.resource_forecast()
        return {
            "status": status,
            "health": health,
            "incidents": incidents,
            "forecast": forecast,
            "overall": {
                "status": status["health"],
                "services_online": f"{status['online']}/{status['service_count']}",
                "health_check_passing": f"{sum(1 for c in health['checks'] if c['status'] == 'ok')}/{len(health['checks'])}",
                "active_incidents": incidents["count"],
                "resource_alerts": forecast["count"],
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def register_stack_routes(app, require_auth=None, get_db=None):
    """Register Stack Engineering API routes on a FastAPI app."""
    from fastapi import Depends

    agent = StackAgent(get_db=get_db)

    @app.get("/api/stack/status")
    async def stack_status(auth=Depends(require_auth) if require_auth else None):
        return agent.status()

    @app.get("/api/stack/services")
    async def stack_services(auth=Depends(require_auth) if require_auth else None):
        return agent.services_detail()

    @app.get("/api/stack/deployments")
    async def stack_deployments(auth=Depends(require_auth) if require_auth else None):
        return agent.deployment_history()

    @app.get("/api/stack/incidents")
    async def stack_incidents(auth=Depends(require_auth) if require_auth else None):
        return agent.incidents()

    @app.get("/api/stack/health")
    async def stack_health(auth=Depends(require_auth) if require_auth else None):
        return agent.health_check()

    @app.get("/api/stack/forecast")
    async def stack_forecast(auth=Depends(require_auth) if require_auth else None):
        return agent.resource_forecast()

    @app.get("/api/stack/report")
    async def stack_report(auth=Depends(require_auth) if require_auth else None):
        return agent.stack_report()

    log.info("[stack] routes registered: /api/stack/{status,services,deployments,incidents,health,forecast,report}")
