"""
EMPIRE V49 · ERROR WATCHER AGENT
=================================
Monitors all agent errors across the system, aggregates them, and
dispatches structured findings to the predictive-revenue coder.

The predictive-revenue coder (empireaipredictiverevenue@proton.me) is
a profile-aware agent that owns the strike pipeline, predictive revenue
modules, and AGI calibration. This watcher feeds it actionable error
reports so it can fix root causes — not symptoms.

Sources monitored:
  1. agent_activity table  — rows_errored per agent per run
  2. PM2 error logs        — hub/mesh crash traces
  3. agent_registry        — stale heartbeats (silent failures)
  4. IPC events            — infra.critical, skill.circuit_opened, etc.

Output:
  - Watches table: watcher_findings (Supabase) — structured for coder consumption
  - IPC event: watcher.findings_ready — signals new report available
  - Console/log: health summary every cycle

Design principle: NO false alarms. Only report errors the system did NOT
auto-heal within a cooldown window. Everything else is noise.
"""

import os
import re
import sys
import json
import time
import asyncio
import logging
import subprocess
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.error_watcher")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watcher] %(message)s",
)

# ── Constants ──────────────────────────────────────────────────────────

AGENT_NAME = "error_watcher"
INTERVAL_SECONDS = int(os.environ.get("WATCHER_INTERVAL_SEC", "900"))  # 15 min (auto-heal reduces need for fast cycles)
ERROR_THRESHOLD = int(os.environ.get("WATCHER_ERROR_THRESHOLD", "5"))  # min errors to report
STALE_HEARTBEAT_HOURS = int(os.environ.get("WATCHER_STALE_HOURS", "2"))

PM2_LOG_PATHS = {
    "empire-hub": "/root/.pm2/logs/empire-hub-error.log",
    "empire-mesh": "/root/.pm2/logs/empire-mesh-error.log",
}

# Suppress same finding for N minutes to avoid alert storms
SUPPRESS_MINUTES = 30

# Hermes Telegram notification binary
HERMES_BIN = "/usr/local/bin/hermes"

# ── Supabase helpers ───────────────────────────────────────────────────

def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in env")
    return create_client(url, key)


def _ensure_watcher_findings_table(sb) -> bool:
    """Create the watcher_findings table if it doesn't exist.

    Returns True if table exists or was created, False otherwise.
    """
    try:
        # Probe: if table exists, select returns empty (not an error)
        sb.table("watcher_findings").select("id").limit(1).execute()
        return True
    except Exception:
        pass  # Table doesn't exist — try to create

    sql = """
    CREATE TABLE IF NOT EXISTS watcher_findings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        agent_name TEXT NOT NULL,
        finding_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'warning',
        title TEXT NOT NULL,
        detail TEXT,
        error_count INTEGER DEFAULT 0,
        sample_errors JSONB,
        recommended_action TEXT,
        source_table TEXT,
        acknowledged BOOLEAN DEFAULT FALSE,
        fixed_by TEXT,
        fixed_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_watcher_findings_created
        ON watcher_findings (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_watcher_findings_agent
        ON watcher_findings (agent_name);
    CREATE INDEX IF NOT EXISTS idx_watcher_findings_unacked
        ON watcher_findings (acknowledged, created_at DESC)
        WHERE acknowledged = FALSE;
    """

    # Try via raw SQL RPC (only works if exec_sql RPC is defined in Supabase)
    try:
        sb.rpc("exec_sql", {"query": sql}).execute()
        log.info("[watcher] Created watcher_findings table via RPC")
        return True
    except Exception:
        pass

    # Fallback: try to create via direct insert of a dummy row
    # (Supabase REST API auto-creates tables with default columns in some configs)
    try:
        sb.table("watcher_findings").insert({
            "agent_name": "_schema_bootstrap",
            "finding_type": "_schema_bootstrap",
            "severity": "info",
            "title": "Schema bootstrap — will be deleted",
        }).execute()
        # Delete the bootstrap row
        sb.table("watcher_findings").delete().eq("agent_name", "_schema_bootstrap").execute()
        log.info("[watcher] Created watcher_findings table via auto-create")
        return True
    except Exception:
        pass

    log.warning(
        "[watcher] ⚠️  watcher_findings table does not exist and could not be created. "
        "Run the following SQL in Supabase SQL Editor:\n"
        "CREATE TABLE watcher_findings ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "agent_name TEXT NOT NULL, "
        "finding_type TEXT NOT NULL, "
        "severity TEXT NOT NULL DEFAULT 'warning', "
        "title TEXT NOT NULL, "
        "detail TEXT, "
        "error_count INTEGER DEFAULT 0, "
        "sample_errors JSONB, "
        "recommended_action TEXT, "
        "source_table TEXT, "
        "acknowledged BOOLEAN DEFAULT FALSE, "
        "fixed_by TEXT, "
        "fixed_at TIMESTAMPTZ"
        ");"
    )
    return False


def _save_finding(sb, finding: dict) -> None:
    """Insert a finding into watcher_findings (deduped by type + agent within window)."""
    try:
        # Dedup: if same finding_type for same agent within SUPPRESS_MINUTES, skip
        window = (datetime.now(timezone.utc) - timedelta(minutes=SUPPRESS_MINUTES)).isoformat()
        existing = (
            sb.table("watcher_findings")
            .select("id")
            .eq("agent_name", finding["agent_name"])
            .eq("finding_type", finding["finding_type"])
            .gte("created_at", window)
            .limit(1)
            .execute()
        )
        if existing.data:
            log.debug(f"[watcher] suppressed duplicate: {finding['finding_type']} for {finding['agent_name']}")
            return

        sb.table("watcher_findings").insert(finding).execute()
        log.info(f"[watcher] 🆕 finding: [{finding['severity']}] {finding['title']}")
        # Mirror to self_healer_log so all 3 oversight layers (supervisor,
        # self-healer, error-watcher) share one queryable log. Error-watcher
        # is non-auto-fix by design — it feeds the coder. self_healer is
        # auto-fix. Putting both rows in self_healer_log makes the timeline
        # of every issue (detected + fixed-or-not) trivially queryable.
        try:
            sb.table("self_healer_log").insert({
                "action": "watcher_finding:" + finding.get("finding_type", "?"),
                "target": finding.get("agent_name", "?"),
                "status": finding.get("severity", "info"),  # info|warn|critical
                "detail": (finding.get("title", "") + " | " + (finding.get("summary") or ""))[:500],
                "fired_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug(f"[watcher] self_healer_log mirror failed: {e}")
    except Exception as e:
        # If table doesn't exist, log a one-time message
        if "relation" in str(e).lower() and "watcher_findings" in str(e).lower():
            log.warning("[watcher] ⚠️  watcher_findings table missing — run `python3 scripts/run_migrations.py` or create manually in Supabase SQL Editor")
        else:
            log.warning(f"[watcher] save_finding error: {e}")


def _get_last_n_runs(sb, agent_name: str, limit: int = 50) -> list:
    """Get recent agent_activity rows for a specific agent."""
    try:
        r = (
            sb.table("agent_activity")
            .select("started_at, rows_seen, rows_processed, rows_errored, rows_blocked, summary, error, status")
            .eq("agent_name", agent_name)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return r.data or []
    except Exception as e:
        log.debug(f"[watcher] query error for {agent_name}: {e}")
        return []


# ── PM2 Helpers (auto-heal) ────────────────────────────────────────────────

_PM2_CACHE_TIMESTAMP = 0
_PM2_CACHE_TTL = 60  # seconds between pm2 jlist calls
_PM2_SERVICE_NAMES_CACHE = set()


async def _pm2_service_names() -> set:
    """Return set of service names managed by PM2 (cached for 60s).

    Falls back to stale cache on error to avoid cascading failures.
    Runs subprocess in a thread to avoid stalling the event loop.
    """
    global _PM2_CACHE_TIMESTAMP, _PM2_SERVICE_NAMES_CACHE
    now = time.time()
    if now - _PM2_CACHE_TIMESTAMP < _PM2_CACHE_TTL:
        return _PM2_SERVICE_NAMES_CACHE
    try:
        r = await asyncio.to_thread(
            lambda: subprocess.run(
                ["pm2", "jlist", "--no-color"],
                capture_output=True, text=True, timeout=10,
            )
        )
        if r.returncode != 0 or not r.stdout.strip():
            return _PM2_SERVICE_NAMES_CACHE
        procs = json.loads(r.stdout)
        names = {p.get("name", "") for p in procs if p.get("name")}
        _PM2_SERVICE_NAMES_CACHE = names
        _PM2_CACHE_TIMESTAMP = now
        return names
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        log.debug(f"[watcher] pm2 jlist failed: {e}")
        return _PM2_SERVICE_NAMES_CACHE


async def _pm2_restart(name: str) -> bool:
    """Restart a PM2-managed service. Returns True on success.
    Runs subprocess in a thread to avoid stalling the event loop.
    """
    try:
        r = await asyncio.to_thread(
            lambda: subprocess.run(
                ["pm2", "restart", name],
                capture_output=True, text=True, timeout=30,
            )
        )
        if r.returncode == 0:
            log.info(f"[watcher] \u2695\ufe0f auto-healed {name} via pm2 restart")
            return True
        else:
            log.warning(f"[watcher] pm2 restart {name} failed: {r.stderr[:200]}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning(f"[watcher] pm2 restart {name} failed: {e}")
        return False


# ── Scan Sources ────────────────────────────────────────────────────────

async def scan_agent_errors(sb) -> list[dict]:
    """Scan agent_activity for agents with high error rates in last N minutes.

    Returns list of finding dicts.
    """
    findings = []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    try:
        # Get all activity in last 2 hours
        r = (
            sb.table("agent_activity")
            .select("agent_name, rows_errored, rows_seen, summary, error, started_at")
            .gte("started_at", cutoff)
            .order("started_at", desc=True)
            .limit(500)
            .execute()
        )
        rows = r.data or []
    except Exception as e:
        log.warning(f"[watcher] agent_activity scan failed: {e}")
        return findings

    # Aggregate by agent
    by_agent = defaultdict(lambda: {"total_errors": 0, "total_seen": 0, "runs": 0, "samples": []})
    for row in rows:
        agent = row.get("agent_name", "?")
        err = row.get("rows_errored", 0) or 0
        seen = row.get("rows_seen", 0) or 0
        by_agent[agent]["total_errors"] += err
        by_agent[agent]["total_seen"] += seen
        by_agent[agent]["runs"] += 1
        if err > 0 and len(by_agent[agent]["samples"]) < 3:
            by_agent[agent]["samples"].append({
                "ts": str(row.get("started_at", ""))[:19],
                "err": err,
                "summary": (row.get("summary") or "")[:200],
            })

    # Generate findings for agents above threshold
    for agent, stats in sorted(by_agent.items(), key=lambda x: -x[1]["total_errors"]):
        if stats["total_errors"] < ERROR_THRESHOLD:
            continue

        error_rate = (stats["total_errors"] / max(stats["total_seen"], 1)) * 100
        if error_rate < 1 and stats["total_errors"] < 10:
            continue  # noise filter

        severity = "critical" if error_rate > 50 or stats["total_errors"] > 100 else "warning"

        findings.append({
            "agent_name": agent,
            "finding_type": "high_error_rate",
            "severity": severity,
            "title": f"{agent}: {stats['total_errors']} errors in {stats['runs']} runs ({error_rate:.0f}% error rate)",
            "detail": f"{stats['total_errors']} errors across {stats['runs']} runs, "
                      f"{stats['total_seen']} total rows processed",
            "error_count": stats["total_errors"],
            "sample_errors": stats["samples"],
            "recommended_action": f"Investigate {agent} — error rate {error_rate:.0f}% exceeds threshold",
            "source_table": "agent_activity",
        })

    return findings


async def scan_pm2_logs(sb) -> list[dict]:
    """Tail PM2 error logs for recent crash traces.

    Returns list of finding dicts.
    """
    findings = []

    for service_name, log_path in PM2_LOG_PATHS.items():
        try:
            if not os.path.exists(log_path):
                continue

            # Read last 200 lines
            with open(log_path) as f:
                lines = f.readlines()[-200:]

            # Find error/traceback lines
            error_lines = []
            current_traceback = []
            in_traceback = False

            for line in lines:
                if "Traceback (most recent call last)" in line:
                    in_traceback = True
                    current_traceback = [line]
                elif in_traceback:
                    current_traceback.append(line)
                    if line.strip() and not line.startswith(" "):
                        # End of traceback
                        error_lines.append("".join(current_traceback))
                        in_traceback = False
                        current_traceback = []
                elif "ERROR" in line or "CRITICAL" in line or "Error:" in line:
                    # Skip known non-errors
                    if "HTTP Request" in line or "Unauthorized" in line:
                        continue
                    error_lines.append(line.strip())

            if not error_lines:
                continue

            # Group errors by type (extract exception name)
            error_types = Counter()
            for el in error_lines:
                m = re.search(r"(\w+(?:Error|Exception|Warning))", el)
                if m:
                    error_types[m.group(1)] += 1
                else:
                    error_types["unknown"] += 1

            severity = "critical" if error_types.total() > 5 else "warning"

            findings.append({
                "agent_name": service_name,
                "finding_type": "pm2_log_errors",
                "severity": severity,
                "title": f"{service_name}: {error_types.total()} errors in PM2 log (last 200 lines)",
                "detail": f"Error types: {dict(error_types.most_common(5))}",
                "error_count": error_types.total(),
                "sample_errors": error_lines[:5],
                "recommended_action": f"Check pm2 logs {service_name} --lines 100 for full traceback",
                "source_table": "pm2_log",
            })

        except Exception as e:
            log.debug(f"[watcher] PM2 log scan error for {service_name}: {e}")

    return findings


async def scan_stale_agents(sb) -> list[dict]:
    """Check agent_registry for agents with stale heartbeats (silent failures).

    Returns list of finding dicts.
    """
    findings = []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=STALE_HEARTBEAT_HOURS)).isoformat()

    try:
        r = (
            sb.table("agent_registry")
            .select("agent_name, role_name, status, last_ping, capabilities")
            .lt("last_ping", cutoff)
            .neq("status", "STOPPED")
            .execute()
        )
        stale = r.data or []
    except Exception as e:
        log.debug(f"[watcher] stale agent scan failed: {e}")
        return findings

    pm2_names = await _pm2_service_names()

    # Collect PM2-managed agents for parallel restart
    pm2_stale = [a for a in stale if a.get("agent_name", "?") in pm2_names]
    if pm2_stale:
        names = [a["agent_name"] for a in pm2_stale]
        log.info(f"[watcher] Auto-healing {len(names)} stale PM2 agents in parallel: {names}")
        # Fire all restarts concurrently
        heal_results = await asyncio.gather(
            *[_pm2_restart(name) for name in names],
            return_exceptions=True,
        )
        # Build a lookup: agent_name -> (success bool, details)
        heal_map: dict[str, dict] = {}
        for agent, ok in zip(pm2_stale, heal_results):
            name = agent["agent_name"]
            if isinstance(ok, Exception):
                heal_map[name] = {"healed": False, "detail": f"exception: {ok}"}
            else:
                heal_map[name] = {"healed": ok, "detail": "success" if ok else "failed"}
    else:
        heal_map = {}

    for agent in stale:
        agent_name = agent.get("agent_name", "?")
        is_pm2 = agent_name in pm2_names

        if is_pm2:
            result = heal_map.get(agent_name, {"healed": False, "detail": "unknown"})
            auto_healed = result["healed"]
            heal_status = "success" if auto_healed else f"failed ({result['detail']})"
            action = (
                "Auto-healed — no action needed"
                if auto_healed
                else f"Auto-heal failed — investigate {agent_name}"
            )
        else:
            heal_status = "not applicable (not PM2-managed)"
            action = f"Restart {agent_name} — pm2 restart or check cron"

        findings.append({
            "agent_name": agent_name,
            "finding_type": "stale_heartbeat",
            "severity": "warning",
            "title": f"{agent_name}: no heartbeat for >{STALE_HEARTBEAT_HOURS}h",
            "detail": (
                f"Role: {agent.get('role_name', '?')} | "
                f"Last ping: {str(agent.get('last_ping', ''))[:19]} | "
                f"Auto-heal: {heal_status}"
            ),
            "error_count": 1,
            "sample_errors": None,
            "recommended_action": action,
            "source_table": "agent_registry",
        })

    return findings


# ── Aggregation & Dispatch ────────────────────────────────────────────

def aggregate_findings(all_findings: list[dict]) -> dict:
    """Combine all findings into a structured report for the coder."""
    by_severity = Counter(f["severity"] for f in all_findings)
    by_agent = Counter(f["agent_name"] for f in all_findings)
    by_type = Counter(f["finding_type"] for f in all_findings)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_findings": len(all_findings),
        "critical": by_severity.get("critical", 0),
        "warning": by_severity.get("warning", 0),
        "by_agent": dict(by_agent.most_common(10)),
        "by_type": dict(by_type.most_common(10)),
        "findings": [
            {
                "severity": f["severity"],
                "agent": f["agent_name"],
                "type": f["finding_type"],
                "title": f["title"],
                "detail": f["detail"],
                "error_count": f["error_count"],
                "action": f["recommended_action"],
            }
            for f in sorted(all_findings, key=lambda x: (
                {"critical": 0, "warning": 1}.get(x["severity"], 2),
                -x["error_count"]
            ))
        ],
    }


async def dispatch_to_coder(sb, report: dict) -> None:
    """Dispatch findings to the predictive-revenue coder.

    Writes to watcher_findings table + creates kanban tasks for critical findings
    + logs summary for the IPC event + sends Telegram alert.
    """
    if not report["findings"]:
        log.info("[watcher] ✅ No findings this cycle — system is healthy")
        return

    log.info(f"[watcher] 📋 {report['total_findings']} findings "
             f"({report['critical']} critical, {report['warning']} warnings)")

    # Save individual findings
    for f in report["findings"]:
        _save_finding(sb, {
            "agent_name": f["agent"],
            "finding_type": f["type"],
            "severity": f["severity"],
            "title": f["title"],
            "detail": f["detail"],
            "error_count": f["error_count"],
            "sample_errors": json.dumps(f.get("sample_errors", [])),
            "recommended_action": f.get("action", ""),
            "source_table": f.get("source_table", ""),
        })

    # Create kanban tasks for critical findings (for the predictive-revenue coder)
    try:
        _create_kanban_tasks(sb, report)
    except Exception as e:
        log.warning(f"[watcher] Kanban task creation failed: {e}")

    # Log the summary for the IPC event / Telegram notification
    critical_agents = ", ".join(
        f['agent'] for f in report['findings'] if f['severity'] == 'critical'
    )
    log.info(f"[watcher] Critical agents: {critical_agents or 'none'}")
    log.info(f"[watcher] Top error types: {report['by_type']}")

    # Send Telegram alert for critical findings
    try:
        await _notify_telegram(report)
    except Exception as e:
        log.warning(f"[watcher] Telegram notification failed: {e}")


# ── Kanban Task Creation ─────────────────────────────────────────────

KANBAN_TASK_TYPE = "watcher.finding_critical"
KANBAN_DEDUP_MINUTES = 60  # don't create duplicate kanban tasks within this window


def _create_kanban_tasks(sb, report: dict) -> None:
    """Create kanban tasks in agent_task_queue for critical findings.

    Each critical finding gets a dedicated task assigned to the predictive_revenue
    role. Tasks are deduped by (finding_type, agent_name) within a window to
    avoid flooding the queue.
    """
    critical_items = [f for f in report["findings"] if f["severity"] == "critical"]
    if not critical_items:
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=KANBAN_DEDUP_MINUTES)).isoformat()
    created_count = 0

    for f in critical_items:
        dedup_key = f"{f['type']}:{f['agent']}"

        # Dedup: skip if a To-Do task for this finding already exists
        try:
            existing = (
                sb.table("agent_task_queue")
                .select("ticket_id")
                .eq("task_type", KANBAN_TASK_TYPE)
                .eq("status", "To-Do")
                .gte("created_at", cutoff)
                .filter("payload", "cs", json.dumps({"dedup_key": dedup_key}))
                .limit(1)
                .execute()
            )
            if existing.data:
                log.debug(f"[watcher] kanban dedup: {dedup_key} already has a To-Do task")
                continue
        except Exception:
            pass  # If JSONB filter fails, fall through and create anyway

        # Build the task payload
        payload = {
            "dedup_key": dedup_key,
            "severity": "critical",
            "agent_name": f["agent"],
            "finding_type": f["type"],
            "title": f["title"],
            "detail": f["detail"],
            "error_count": f["error_count"],
            "recommended_action": f.get("action", ""),
            "source": "error_watcher",
        }

        try:
            sb.table("agent_task_queue").insert({
                "task_type": KANBAN_TASK_TYPE,
                "payload": json.dumps(payload),
                "status": "To-Do",
                "assigned_agent": "predictive_revenue",
                "priority": 5,  # high priority for critical findings
            }).execute()
            log.info(f"[watcher] \ud83d\udccb kanban task created: {dedup_key}")
            created_count += 1
        except Exception as e:
            log.warning(f"[watcher] kanban task insert failed for {dedup_key}: {e}")

    if created_count:
        log.info(f"[watcher] Created {created_count} kanban task(s) for critical findings")
    else:
        log.debug("[watcher] No new kanban tasks needed (all deduped)")


# ── Hermes Telegram Notification ──────────────────────────────────────


async def _telegram_send(text: str) -> bool:
    """Send a Telegram message via hermes CLI. Best-effort: if hermes
    isn't available, we just log and return False.

    Runs subprocess in a thread to avoid stalling the event loop."""
    import subprocess
    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(
                [HERMES_BIN, "send", "--to", "telegram", text],
                capture_output=True, text=True, timeout=15,
            )
        )
        if result.returncode == 0:
            log.info(f"[watcher] Telegram notification sent")
            return True
        else:
            log.warning(f"[watcher] Telegram send returned {result.returncode}: {result.stderr[:200]}")
            return False
    except Exception as e:
        log.debug(f"[watcher] Telegram send failed: {e}")
        return False


async def _notify_telegram(report: dict) -> None:
    """Send a concise Telegram alert for critical findings."""
    if not report.get("critical"):
        return  # only notify on critical

    critical_items = [f for f in report["findings"] if f["severity"] == "critical"]
    if not critical_items:
        return

    lines = ["\u26a0\ufe0f Watcher: Critical Findings"]
    for f in critical_items[:5]:  # max 5 to avoid message length limits
        agent = f.get("agent", "?")
        title = (f.get("title") or "?")[:120]
        action = (f.get("action") or "?")[:100]
        lines.append(f"\n\u2022 {agent}: {title}")
        lines.append(f"  \u2192 {action}")

    if len(critical_items) > 5:
        lines.append(f"\n... and {len(critical_items) - 5} more critical findings")

    lines.append(f"\nTotal: {report['total_findings']} findings ({report['critical']} critical, {report['warning']} warnings)")
    lines.append("\nDashboard: empire-ai.co.uk/command#fleet")

    await _telegram_send("\n".join(lines))


# ── Main Cycle ─────────────────────────────────────────────────────────

async def run_cycle(sb) -> dict:
    """One full watcher cycle: scan all sources, aggregate, dispatch.

    Returns the aggregate report.
    """
    log.info("[watcher] 🔍 Starting error scan cycle...")

    # Scan all sources in parallel
    agent_findings, pm2_findings, stale_findings = await asyncio.gather(
        scan_agent_errors(sb),
        scan_pm2_logs(sb),
        scan_stale_agents(sb),
    )

    all_findings = agent_findings + pm2_findings + stale_findings

    # Aggregate and dispatch
    report = aggregate_findings(all_findings)
    await dispatch_to_coder(sb, report)

    log.info(f"[watcher] ✅ Cycle complete — {report['total_findings']} findings, "
             f"{report['critical']} critical, {report['warning']} warnings")

    return report


# ── Background Loop ────────────────────────────────────────────────────

async def run_loop(interval_seconds: int = None):
    """Background loop: run watcher cycle every N seconds."""
    if interval_seconds is None:
        interval_seconds = INTERVAL_SECONDS

    log.info(f"[watcher] 🟢 Error Watcher ONLINE · interval={interval_seconds}s")
    sb = _sb()

    # Ensure the watcher_findings table exists
    table_ok = _ensure_watcher_findings_table(sb)
    if not table_ok:
        log.warning("[watcher] Continuing without watcher_findings table — findings will not persist")
        log.warning("[watcher] Create the table manually or deploy migrations to enable persistence")

    cycles = 0
    while True:
        try:
            report = await run_cycle(sb)

            # Log heartbeat to agent_activity
            try:
                sb.table("agent_activity").insert({
                    "agent_name": AGENT_NAME,
                    "run_id": f"cycle_{cycles}_{int(time.time())}",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "ok",
                    "rows_seen": report["total_findings"],
                    "rows_processed": report["critical"] + report["warning"],
                    "rows_errored": 0,
                    "summary": f"{report['total_findings']} findings ({report['critical']} critical, {report['warning']} warnings)",
                }).execute()
            except Exception:
                pass

            cycles += 1
        except Exception as e:
            log.error(f"[watcher] Cycle error: {e}")

        await asyncio.sleep(interval_seconds)


# ── Standalone CLI ────────────────────────────────────────────────────

def run():
    """Sync entry point for PM2 / main.py compatibility."""
    asyncio.run(run_loop())


async def run_once():
    """Run a single cycle for testing or cron."""
    sb = _sb()
    _ensure_watcher_findings_table(sb)
    report = await run_cycle(sb)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Empire Error Watcher Agent")
    p.add_argument("--once", action="store_true", help="Run a single cycle and print report")
    p.add_argument("--interval", type=int, default=300, help="Polling interval in seconds")
    args = p.parse_args()

    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_loop(args.interval))
