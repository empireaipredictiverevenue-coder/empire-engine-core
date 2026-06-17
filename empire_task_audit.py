"""
EMPIRE V49 · TASK AUDIT REPORTER
=================================
Audit reporting layer for agent task completions.

Queries the agent_task_queue table and produces:
  - Recent task completions (Done/Failed) with results
  - Aggregate stats (daily completions, per-agent performance, success rates)
  - Per-agent performance reports
  - Operator-facing HTML audit report page

Wire-up in hub.py:
    from empire_task_audit import TaskAuditReporter, register_task_audit_routes
    task_audit = TaskAuditReporter(get_db=get_db)
    register_task_audit_routes(app, reporter=task_audit, require_auth=require_auth)

Endpoints:
  GET  /api/v1/task-audit/recent        — recent completions (last 24h default)
  GET  /api/v1/task-audit/stats         — aggregate stats (daily, per-agent)
  GET  /api/v1/task-audit/agent/{name}  — per-agent report
  GET  /api/v1/task-audit/report        — rendered HTML report page
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

log = logging.getLogger("empire.task_audit")


class TaskAuditReporter:
    """Queries completed agent tasks and generates audit reports."""

    def __init__(self, get_db: Callable):
        self._get_db = get_db

    # ── Recent Completions ──────────────────────────────────────────

    def recent_completions(
        self,
        *,
        hours: int = 24,
        limit: int = 50,
        status: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> list[dict]:
        """Return recently completed/failed tasks with their results."""
        try:
            db = self._get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

            statuses = ["Done", "Failed"]
            if status and status in ("Done", "Failed"):
                statuses = [status]

            q = db.table("agent_task_queue") \
                .select("*") \
                .in_("status", statuses) \
                .gte("completed_at", cutoff) \
                .order("completed_at", desc=True) \
                .limit(limit)

            if agent:
                q = q.eq("assigned_agent", agent)

            r = q.execute()
            rows = r.data or []

            # Parse payload/result from JSON strings if needed
            out = []
            for row in rows:
                out.append({
                    "ticket_id": row.get("ticket_id", ""),
                    "task_type": row.get("task_type", ""),
                    "status": row.get("status", ""),
                    "assigned_agent": row.get("assigned_agent", ""),
                    "priority": row.get("priority", 0),
                    "created_at": str(row.get("created_at", "")),
                    "started_at": str(row.get("started_at", "")) if row.get("started_at") else None,
                    "completed_at": str(row.get("completed_at", "")),
                    "result": row.get("result", {}) if isinstance(row.get("result"), dict) else {},
                    "error": row.get("error", "") if row.get("error") else None,
                    "payload": row.get("payload", {}) if isinstance(row.get("payload"), dict) else {},
                    "duration_seconds": self._compute_duration(
                        row.get("started_at"), row.get("completed_at")
                    ),
                })
            return out
        except Exception as e:
            log.warning(f"[task-audit] recent_completions error: {e}")
            return []

    # ── Aggregate Stats ──────────────────────────────────────────────

    def aggregate_stats(self, days: int = 7) -> dict:
        """Return aggregate task completion stats for the given period."""
        try:
            db = self._get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            # Fetch all completed/failed tasks in the window
            r = db.table("agent_task_queue") \
                .select("status,assigned_agent,task_type,completed_at,started_at") \
                .in_("status", ["Done", "Failed"]) \
                .gte("completed_at", cutoff) \
                .limit(5000) \
                .execute()
            rows = r.data or []

            if not rows:
                return self._empty_stats()

            # ── Daily breakdown ──────────────────────────────────
            daily: dict[str, dict] = {}
            for row in rows:
                day = str(row.get("completed_at", ""))[:10]
                if day not in daily:
                    daily[day] = {"date": day, "done": 0, "failed": 0, "total": 0}
                status = row.get("status", "")
                if status == "Done":
                    daily[day]["done"] += 1
                elif status == "Failed":
                    daily[day]["failed"] += 1
                daily[day]["total"] += 1

            daily_list = sorted(daily.values(), key=lambda d: d["date"])

            # ── Per-agent breakdown ──────────────────────────────
            agents: dict[str, dict] = {}
            for row in rows:
                agent = row.get("assigned_agent") or "unassigned"
                if agent not in agents:
                    agents[agent] = {
                        "agent": agent,
                        "done": 0,
                        "failed": 0,
                        "total": 0,
                        "total_duration_seconds": 0,
                        "durations_count": 0,
                        "task_types": set(),
                    }
                status = row.get("status", "")
                if status == "Done":
                    agents[agent]["done"] += 1
                elif status == "Failed":
                    agents[agent]["failed"] += 1
                agents[agent]["total"] += 1
                agents[agent]["task_types"].add(row.get("task_type", ""))

                dur = self._compute_duration(row.get("started_at"), row.get("completed_at"))
                if dur is not None:
                    agents[agent]["total_duration_seconds"] += dur
                    agents[agent]["durations_count"] += 1

            agent_list = []
            for agent, data in sorted(agents.items(), key=lambda x: -x[1]["total"]):
                dur_count = max(data["durations_count"], 1)
                agent_list.append({
                    "agent": data["agent"],
                    "done": data["done"],
                    "failed": data["failed"],
                    "total": data["total"],
                    "success_rate": round(data["done"] / max(data["total"], 1), 3),
                    "avg_duration_seconds": round(data["total_duration_seconds"] / dur_count, 1),
                    "task_types": sorted(data["task_types"]),
                })

            # ── Per task_type breakdown ──────────────────────────
            task_types: dict[str, dict] = {}
            for row in rows:
                tt = row.get("task_type", "unknown")
                if tt not in task_types:
                    task_types[tt] = {"task_type": tt, "done": 0, "failed": 0, "total": 0}
                status = row.get("status", "")
                if status == "Done":
                    task_types[tt]["done"] += 1
                elif status == "Failed":
                    task_types[tt]["failed"] += 1
                task_types[tt]["total"] += 1

            tt_list = []
            for tt, data in sorted(task_types.items(), key=lambda x: -x[1]["total"]):
                tt_list.append({
                    "task_type": data["task_type"],
                    "done": data["done"],
                    "failed": data["failed"],
                    "total": data["total"],
                    "success_rate": round(data["done"] / max(data["total"], 1), 3),
                })

            total_done = sum(d["done"] for d in daily.values())
            total_failed = sum(d["failed"] for d in daily.values())
            total_all = total_done + total_failed

            return {
                "window_days": days,
                "total_completed": total_all,
                "total_done": total_done,
                "total_failed": total_failed,
                "overall_success_rate": round(total_done / max(total_all, 1), 3),
                "daily_breakdown": daily_list,
                "agent_breakdown": agent_list,
                "task_type_breakdown": tt_list,
                "distinct_agents": len(agent_list),
                "distinct_task_types": len(tt_list),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            log.warning(f"[task-audit] aggregate_stats error: {e}")
            return self._empty_stats(str(e)[:200])

    def _empty_stats(self, error: str = "") -> dict:
        return {
            "window_days": 0,
            "total_completed": 0,
            "total_done": 0,
            "total_failed": 0,
            "overall_success_rate": 0,
            "daily_breakdown": [],
            "agent_breakdown": [],
            "task_type_breakdown": [],
            "distinct_agents": 0,
            "distinct_task_types": 0,
            "error": error,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Per-Agent Report ─────────────────────────────────────────────

    def agent_report(self, agent_name: str, days: int = 30) -> dict:
        """Return detailed performance report for a single agent."""
        try:
            db = self._get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            r = db.table("agent_task_queue") \
                .select("*") \
                .eq("assigned_agent", agent_name) \
                .in_("status", ["Done", "Failed"]) \
                .gte("completed_at", cutoff) \
                .order("completed_at", desc=True) \
                .limit(200) \
                .execute()
            rows = r.data or []

            done = sum(1 for r in rows if r.get("status") == "Done")
            failed = sum(1 for r in rows if r.get("status") == "Failed")
            total = done + failed

            durations = []
            for row in rows:
                dur = self._compute_duration(row.get("started_at"), row.get("completed_at"))
                if dur is not None:
                    durations.append(dur)

            # Latest tasks
            latest = []
            for row in rows[:20]:
                latest.append({
                    "ticket_id": str(row.get("ticket_id", ""))[:16] + "...",
                    "task_type": row.get("task_type", ""),
                    "status": row.get("status", ""),
                    "completed_at": str(row.get("completed_at", "")),
                    "error": row.get("error") if row.get("error") else None,
                    "duration_seconds": self._compute_duration(
                        row.get("started_at"), row.get("completed_at")
                    ),
                })

            return {
                "agent": agent_name,
                "window_days": days,
                "total_completed": total,
                "done": done,
                "failed": failed,
                "success_rate": round(done / max(total, 1), 3),
                "avg_duration_seconds": round(sum(durations) / max(len(durations), 1), 1) if durations else None,
                "latest_tasks": latest,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            log.warning(f"[task-audit] agent_report({agent_name}) error: {e}")
            return {"agent": agent_name, "error": str(e)[:200]}

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _compute_duration(started_at, completed_at) -> Optional[float]:
        """Compute task duration in seconds."""
        if not started_at or not completed_at:
            return None
        try:
            s = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            e = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
            return round((e - s).total_seconds(), 1)
        except (ValueError, TypeError):
            return None


# ── HTML REPORT PAGE ──────────────────────────────────────────────────

def _audit_report_html(stats: dict, recent: list) -> str:
    """Render an operator-facing HTML audit report page."""
    from empire_tokens import empire_head

    css = """
    .ar-wrap { max-width: 960px; margin: 0 auto; padding: 48px 32px; }
    .ar-title { font-size: 26px; font-weight: 200; color: #f8fafc; letter-spacing: -0.02em; margin-bottom: 4px; }
    .ar-title em { color: #44E5B8; font-style: italic; font-weight: 500; }
    .ar-sub { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #64748b; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 32px; }
    .ar-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 32px; }
    @media (max-width: 800px) { .ar-cards { grid-template-columns: repeat(2, 1fr); } }
    .ar-card { background: #14141e; border: 1px solid #1e293b; padding: 16px; }
    .ar-card-label { font-family: 'SF Mono','Fira Code',monospace; font-size: 9px; color: #64748b; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 6px; }
    .ar-card-value { font-family: 'SF Mono','Fira Code',monospace; font-size: 22px; color: #f8fafc; font-weight: 600; }
    .ar-card-value.teal { color: #44E5B8; }
    .ar-card-value.red { color: #ff6b6b; }
    .ar-card-value.amber { color: #FFB800; }
    .ar-section { margin-bottom: 32px; }
    .ar-section-title { font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #94a3b8; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #1e293b; }
    .ar-table { width: 100%; border-collapse: collapse; font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; }
    .ar-table th { text-align: left; padding: 8px 10px; font-size: 8px; color: #64748b; letter-spacing: 0.12em; text-transform: uppercase; border-bottom: 1px solid #1e293b; font-weight: 400; }
    .ar-table td { padding: 8px 10px; color: #cbd5e1; border-bottom: 1px solid #1e293b; }
    .ar-table tr:hover td { background: rgba(255,255,255,0.02); }
    .ar-badge { display: inline-block; padding: 2px 6px; font-size: 8px; border-radius: 2px; letter-spacing: 0.08em; }
    .ar-badge.done { background: rgba(68,229,184,0.1); color: #44E5B8; }
    .ar-badge.failed { background: rgba(255,107,107,0.1); color: #ff6b6b; }
    .ar-empty { padding: 32px; text-align: center; font-family: 'SF Mono','Fira Code',monospace; font-size: 10px; color: #64748b; }
    .ar-duration { color: #64748b; font-size: 9px; }
    .ar-refresh { display: inline-block; padding: 6px 12px; background: transparent; border: 1px solid #1e293b; color: #94a3b8; font-family: 'SF Mono','Fira Code',monospace; font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; cursor: pointer; text-decoration: none; margin-left: 12px; transition: all 0.15s; }
    .ar-refresh:hover { border-color: #44E5B8; color: #44E5B8; }
    """

    overall_success = stats.get("overall_success_rate", 0)
    success_color = "teal" if overall_success >= 0.9 else ("amber" if overall_success >= 0.7 else "red")

    head = empire_head(title="Empire AI · Agent Task Audit", extra=css)

    # ── Stats cards ──────────────────────────────────────────────
    total_done = stats.get("total_done", 0)
    total_failed = stats.get("total_failed", 0)
    total_all = stats.get("total_completed", 0)

    # ── Agent table rows ─────────────────────────────────────────
    agent_rows = ""
    for a in stats.get("agent_breakdown", [])[:15]:
        sr = a.get("success_rate", 0)
        sr_display = f"{(sr * 100):.0f}%"
        dur = f"{a.get('avg_duration_seconds', 0):.0f}s" if a.get("avg_duration_seconds") else "—"
        agent_rows += f"""<tr>
            <td style="color:#f8fafc">{a['agent']}</td>
            <td>{a['done']} done · {a['failed']} failed</td>
            <td style="color:{'#44E5B8' if sr >= 0.9 else ('#FFB800' if sr >= 0.7 else '#ff6b6b')}">{sr_display}</td>
            <td class="ar-duration">{dur}</td>
            <td style="color:#94a3b8;font-size:9px">{', '.join(a.get('task_types', []))}</td>
        </tr>"""

    # ── Recent task rows ─────────────────────────────────────────
    recent_rows = ""
    for t in recent[:30]:
        status_cls = "done" if t.get("status") == "Done" else "failed"
        dur = f"{t.get('duration_seconds', 0):.0f}s" if t.get("duration_seconds") else "—"
        err = t.get("error", "")
        err_display = f'<br><span style="color:#ff6b6b;font-size:8px">{err[:80]}</span>' if err else ""
        recent_rows += f"""<tr>
            <td style="color:#64748b">{str(t.get('completed_at', ''))[:19]}</td>
            <td style="color:#f8fafc">{t.get('assigned_agent', '?')}</td>
            <td><span class="ar-badge {status_cls}">{t.get('status', '?')}</span></td>
            <td>{t.get('task_type', '?')}{err_display}</td>
            <td class="ar-duration">{dur}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
<div class="ar-wrap">
  <div style="display:flex;align-items:baseline;justify-content:space-between">
    <div>
      <div class="ar-title">Agent <em>Task Audit</em></div>
      <div class="ar-sub">Task completion reports · {stats.get('window_days', 7)}-day window</div>
    </div>
    <a href="/api/v1/task-audit/report" class="ar-refresh">Refresh</a>
  </div>

  <div class="ar-cards">
    <div class="ar-card">
      <div class="ar-card-label">Total Completed</div>
      <div class="ar-card-value">{total_all}</div>
    </div>
    <div class="ar-card">
      <div class="ar-card-label">Successful</div>
      <div class="ar-card-value teal">{total_done}</div>
    </div>
    <div class="ar-card">
      <div class="ar-card-label">Failed</div>
      <div class="ar-card-value red">{total_failed}</div>
    </div>
    <div class="ar-card">
      <div class="ar-card-label">Success Rate</div>
      <div class="ar-card-value {success_color}">{(overall_success * 100):.0f}%</div>
    </div>
  </div>

  <div class="ar-section">
    <div class="ar-section-title">Agent Performance · {stats.get('distinct_agents', 0)} agents</div>
    <table class="ar-table">
      <thead><tr><th>Agent</th><th>Completions</th><th>Success Rate</th><th>Avg Duration</th><th>Task Types</th></tr></thead>
      <tbody>{agent_rows or '<tr><td colspan="5" class="ar-empty">No agent completions in window</td></tr>'}</tbody>
    </table>
  </div>

  <div class="ar-section">
    <div class="ar-section-title">Recent Task Completions · last 24h</div>
    <table class="ar-table">
      <thead><tr><th>Completed</th><th>Agent</th><th>Status</th><th>Task / Error</th><th>Duration</th></tr></thead>
      <tbody>{recent_rows or '<tr><td colspan="5" class="ar-empty">No recent completions</td></tr>'}</tbody>
    </table>
  </div>

  <div style="font-family:'SF Mono','Fira Code',monospace;font-size:9px;color:#475569;text-align:right;margin-top:24px">
    Empire AI V49 · Task Audit Report · Generated {stats.get('generated_at', '')[:19]}
  </div>
</div>
</body>
</html>"""


# ── ROUTE REGISTRATION ───────────────────────────────────────────────

def register_task_audit_routes(
    app: FastAPI,
    *,
    reporter: TaskAuditReporter,
    require_auth=None,
):
    """Register task audit API routes on a FastAPI app.

    GET /api/v1/task-audit/recent      — recent task completions
    GET /api/v1/task-audit/stats       — aggregate stats
    GET /api/v1/task-audit/agent/{name} — per-agent report
    GET /api/v1/task-audit/report      — rendered HTML report page
    """

    @app.get("/api/v1/task-audit/recent")
    async def task_audit_recent(
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(50, ge=1, le=200),
        status: Optional[str] = Query(None, pattern="^(Done|Failed)$"),
        agent: Optional[str] = Query(None),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Recent agent task completions (Done/Failed) with results."""
        tasks = reporter.recent_completions(
            hours=hours,
            limit=limit,
            status=status,
            agent=agent,
        )
        return {
            "tasks": tasks,
            "count": len(tasks),
            "window_hours": hours,
        }

    @app.get("/api/v1/task-audit/stats")
    async def task_audit_stats(
        days: int = Query(7, ge=1, le=90),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Aggregate task completion stats: daily, per-agent, per-task-type."""
        return reporter.aggregate_stats(days=days)

    @app.get("/api/v1/task-audit/agent/{agent_name}")
    async def task_audit_agent(
        agent_name: str,
        days: int = Query(30, ge=1, le=90),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Detailed performance report for a single agent."""
        report = reporter.agent_report(agent_name, days=days)
        if "error" in report:
            raise HTTPException(500, report["error"])
        return report

    @app.get("/api/v1/task-audit/report", response_class=HTMLResponse)
    async def task_audit_report_page(
        days: int = Query(7, ge=1, le=90),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Rendered HTML audit report page for operator review."""
        stats = reporter.aggregate_stats(days=days)
        recent = reporter.recent_completions(hours=24, limit=50)
        return _audit_report_html(stats, recent)

    log.info("[task-audit] Routes registered · /api/v1/task-audit/*")
