"""
EMPIRE V49 · AGENT MESH (HERMES PROTOCOL)
=========================================
Kanban task queue + agent orchestration system.
All agents use local Ollama for language generation.

Tables used:
  - agent_task_queue: Task tickets with status (To-Do, In Progress, Blocked, Done, Failed)
  - agent_registry: Agent heartbeat, capabilities, and metrics

Agent teams:
  Scouting  → Prospector → Outreach
  Studio    → Copywriter → Render Pro
  Revenue   → Dispatcher → Quality Analyst

Local sovereignty: All LLM calls go through AIRouter → local Ollama.
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List, Callable, Any
from supabase import create_client, Client

log = logging.getLogger("empire.hermes")

# ── Task type constants ──────────────────────────────────────────────
TASK_SCOUT_FIND_ROOFS       = "scout.find_roofs"
TASK_OUTREACH_DRAFT_EMAIL   = "outreach.draft_email"
TASK_STUDIO_WRITE_SCRIPT    = "studio.write_script"
TASK_STUDIO_RENDER_REEL     = "studio.render_reel"
TASK_REVENUE_CONNECT_BUYER  = "revenue.connect_buyer"
TASK_REVENUE_SCORE_CALL     = "revenue.score_call"
TASK_SWARM_FIRE             = "swarm.fire"
TASK_SWARM_STRIKE_VIDEO     = "swarm.strike_video"

ALL_TASK_TYPES = [
    TASK_SCOUT_FIND_ROOFS,
    TASK_OUTREACH_DRAFT_EMAIL,
    TASK_STUDIO_WRITE_SCRIPT,
    TASK_STUDIO_RENDER_REEL,
    TASK_REVENUE_CONNECT_BUYER,
    TASK_REVENUE_SCORE_CALL,
    TASK_SWARM_FIRE,
    TASK_SWARM_STRIKE_VIDEO,
]

# ── Agent name constants ─────────────────────────────────────────────
AGENT_SCOUT         = "mesh.scout"
AGENT_OUTREACH      = "mesh.outreach"
AGENT_COPYWRITER    = "mesh.copywriter"
AGENT_RENDER        = "mesh.render"
AGENT_DISPATCHER    = "mesh.dispatcher"
AGENT_QUALITY       = "mesh.quality"
AGENT_SWARM_WORKER  = "mesh.swarm_worker"

# ── Agent → task types mapping ───────────────────────────────────────
AGENT_TASK_MAP = {
    AGENT_SCOUT:        [TASK_SCOUT_FIND_ROOFS],
    AGENT_OUTREACH:     [TASK_OUTREACH_DRAFT_EMAIL],
    AGENT_COPYWRITER:   [TASK_STUDIO_WRITE_SCRIPT],
    AGENT_RENDER:       [TASK_STUDIO_RENDER_REEL],
    AGENT_DISPATCHER:   [TASK_REVENUE_CONNECT_BUYER],
    AGENT_QUALITY:      [TASK_REVENUE_SCORE_CALL],
    AGENT_SWARM_WORKER: [TASK_SWARM_FIRE, TASK_SWARM_STRIKE_VIDEO],
}

AGENT_CAPABILITIES = {
    AGENT_SCOUT:        ["scout", "prospector", "satellite"],
    AGENT_OUTREACH:     ["outreach", "email", "drafting"],
    AGENT_COPYWRITER:   ["copywriter", "creative", "scripting"],
    AGENT_RENDER:       ["render", "ffmpeg", "video"],
    AGENT_DISPATCHER:   ["dispatcher", "buyer", "revenue"],
    AGENT_QUALITY:      ["quality", "analyst", "scoring"],
    AGENT_SWARM_WORKER: ["swarm", "tts", "kokoro", "ollama", "ffmpeg", "video_render"],
}

# ── Agent display names ──────────────────────────────────────────────
AGENT_DISPLAY = {
    AGENT_SCOUT:        "Scout (Prospector)",
    AGENT_OUTREACH:     "Outreach Agent",
    AGENT_COPYWRITER:   "Copywriter",
    AGENT_RENDER:       "Render Pro",
    AGENT_DISPATCHER:   "Dispatcher",
    AGENT_QUALITY:      "Quality Analyst",
    AGENT_SWARM_WORKER: "Swarm Worker",
}

# ── Mesh agent → Fleet role mapping ─────────────────────────────────
MESH_AGENT_ROLES = {
    AGENT_SCOUT:        "mesh_scout",
    AGENT_OUTREACH:     "mesh_outreach",
    AGENT_COPYWRITER:   "mesh_studio_copy",
    AGENT_RENDER:       "mesh_studio_render",
    AGENT_DISPATCHER:   "mesh_dispatcher",
    AGENT_QUALITY:      "quality_analyst",
    AGENT_SWARM_WORKER: "swarm_worker",
}


class AgentMesh:
    """Kanban task queue orchestrator. Manages task lifecycle and agent coordination."""

    def __init__(self, get_db: Callable[[], Client], router=None):
        self._get_db = get_db
        self.router = router
        self.running = False
        self._loop_interval = int(os.environ.get("MESH_LOOP_INTERVAL_SEC", "30"))
        self._agents_enabled = set(AGENT_TASK_MAP.keys())  # all agents enabled by default

    # ── DB access ────────────────────────────────────────────────────
    @property
    def db(self) -> Client:
        return self._get_db()

    # ── Task CRUD ────────────────────────────────────────────────────
    async def create_task(
        self,
        task_type: str,
        payload: Dict,
        *,
        assigned_agent: Optional[str] = None,
        priority: int = 0,
    ) -> Optional[str]:
        """Create a new task ticket. Returns ticket_id or None on error."""
        try:
            r = self.db.table("agent_task_queue").insert({
                "task_type": task_type,
                "payload": json.dumps(payload) if isinstance(payload, dict) else payload,
                "status": "To-Do",
                "assigned_agent": assigned_agent,
                "priority": priority,
            }).execute()
            if r.data:
                ticket_id = r.data[0].get("ticket_id")
                log.info(f"[hermes] task created: {ticket_id[:8]} | {task_type} | priority={priority}")
                return ticket_id
        except Exception as e:
            log.error(f"[hermes] create_task error: {e}")
        return None

    async def claim_task(self, agent_name: str, task_types: Optional[List[str]] = None) -> Optional[Dict]:
        """Atomically claim next available task for this agent. Returns task dict or None."""
        try:
            # Use the Supabase RPC for atomic claim
            r = self.db.rpc("claim_next_task", {
                "p_agent_name": agent_name,
                "p_task_types": task_types or AGENT_TASK_MAP.get(agent_name, []),
            }).execute()
            if r.data:
                log.info(f"[hermes] {agent_name} claimed task {r.data.get('ticket_id', '')[:8]}")
                return r.data
        except Exception as e:
            log.error(f"[hermes] claim_task error: {e}")
        return None

    async def update_task_status(
        self,
        ticket_id: str,
        status: str,
        *,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Update a task's status, result, and timestamps."""
        try:
            update = {"status": status}
            utcnow = datetime.now(timezone.utc).isoformat()
            if status in ("Done", "Failed", "Cancelled"):
                update["completed_at"] = utcnow
            if result is not None:
                update["result"] = json.dumps(result) if isinstance(result, dict) else result
            if error is not None:
                update["error"] = str(error)[:2000]
            self.db.table("agent_task_queue").update(update).eq("ticket_id", ticket_id).execute()
            log.info(f"[hermes] task {ticket_id[:8]} → {status}")
        except Exception as e:
            log.error(f"[hermes] update_task_status error: {e}")

    async def complete_task(self, ticket_id: str, result: Optional[Dict] = None):
        """Mark task as Done."""
        await self.update_task_status(ticket_id, "Done", result=result)

    async def fail_task(self, ticket_id: str, error: str, result: Optional[Dict] = None):
        """Mark task as Failed."""
        await self.update_task_status(ticket_id, "Failed", result=result, error=error)

    async def block_task(self, ticket_id: str, reason: str):
        """Mark task as Blocked with reason."""
        await self.update_task_status(ticket_id, "Blocked", error=reason)

    async def cancel_task(self, ticket_id: str, reason: str = ""):
        """Cancel a task."""
        await self.update_task_status(ticket_id, "Cancelled", error=reason)

    async def get_task(self, ticket_id: str) -> Optional[Dict]:
        """Get a single task by ticket_id."""
        try:
            r = self.db.table("agent_task_queue").select("*").eq("ticket_id", ticket_id).limit(1).execute()
            if r.data:
                return r.data[0]
        except Exception as e:
            log.error(f"[hermes] get_task error: {e}")
        return None

    async def list_tasks(
        self,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List tasks with optional filters."""
        try:
            q = self.db.table("agent_task_queue").select("*")
            if status:
                q = q.eq("status", status)
            if task_type:
                q = q.eq("task_type", task_type)
            if assigned_agent:
                q = q.eq("assigned_agent", assigned_agent)
            r = q.order("priority", desc=True).order("created_at", desc=True).limit(limit).execute()
            return r.data or []
        except Exception as e:
            log.error(f"[hermes] list_tasks error: {e}")
        return []

    async def get_queue_stats(self) -> Dict:
        """Return aggregate stats about the task queue."""
        stats = {"total": 0, "by_status": {}, "by_type": {}}
        try:
            tasks = self.db.table("agent_task_queue").select("status,task_type").execute()
            stats["total"] = len(tasks.data or [])
            for t in (tasks.data or []):
                s = t.get("status", "unknown")
                stats["by_status"][s] = stats["by_status"].get(s, 0) + 1
                tt = t.get("task_type", "unknown")
                stats["by_type"][tt] = stats["by_type"].get(tt, 0) + 1
        except Exception as e:
            log.error(f"[hermes] queue_stats error: {e}")
        return stats

    # ── Agent registry ───────────────────────────────────────────────
    async def heartbeat(self, agent_name: str, status: str = "ACTIVE") -> bool:
        """Register/ping an agent in the agent_registry table."""
        try:
            caps = AGENT_CAPABILITIES.get(agent_name, [])
            task_types = AGENT_TASK_MAP.get(agent_name, [])
            role_name = MESH_AGENT_ROLES.get(agent_name)
            payload = {
                "agent_name": agent_name,
                "role_name": role_name,
                "status": status,
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": agent_name in self._agents_enabled,
                "capabilities": caps,
                "task_types": task_types,
            }
            if role_name:
                payload["role_name"] = role_name
            self.db.table("agent_registry").upsert(
                payload, on_conflict="agent_name"
            ).execute()
            return True
        except Exception as e:
            log.error(f"[hermes] heartbeat error ({agent_name}): {e}")
            return False

    async def get_agents(self) -> List[Dict]:
        """List all registered agents with their status."""
        try:
            r = self.db.table("agent_registry").select("*").order("agent_name").execute()
            return r.data or []
        except Exception as e:
            log.error(f"[hermes] get_agents error: {e}")
        return []

    async def snapshot(self) -> Dict:
        """Full mesh status snapshot."""
        agents = await self.get_agents()
        queue_stats = await self.get_queue_stats()
        # Get recent tasks
        recent = await self.list_tasks(limit=20)
        return {
            "agents": agents,
            "queue": queue_stats,
            "recent_tasks": recent,
            "loop_interval_s": self._loop_interval,
            "agents_enabled": len(self._agents_enabled),
            "running": self.running,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ── Mesh loop (background task) ─────────────────────────────────
    async def mesh_loop(self):
        """Main background loop. Runs every N seconds and dispatches agents."""
        log.info(f"[hermes] mesh loop starting (interval={self._loop_interval}s)")
        self.running = True

        # Register all agents on startup
        for agent_name in AGENT_TASK_MAP:
            await self.heartbeat(agent_name, "ACTIVE")

        while self.running:
            try:
                await self._tick()
            except Exception as e:
                log.error(f"[hermes] mesh tick error: {e}")
            await asyncio.sleep(self._loop_interval)

    async def _tick(self):
        """One mesh tick: heartbeat registered agents, check for pending tasks."""
        # Heartbeat all enabled agents
        for agent_name in self._agents_enabled:
            await self.heartbeat(agent_name, "ACTIVE")

        # If no router available, skip agent dispatch (hub handles it)
        if not self.router:
            return

        # Look for tasks that need dispatching (To-Do tasks)
        pending = await self.list_tasks(status="To-Do", limit=20)
        if not pending:
            return

        log.info(f"[hermes] {len(pending)} pending tasks in queue")

        # Try to claim and dispatch each task
        for task in pending:
            tt = task.get("task_type", "")
            assigned = task.get("assigned_agent")
            if assigned and assigned in self._agents_enabled:
                # Agent-specific dispatching will be handled by the individual agent loops
                pass

    def stop(self):
        """Stop the mesh loop."""
        self.running = False
        log.info("[hermes] mesh loop stopping")


# ─────────────────────────────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────────────────────────────
def register_mesh_routes(app, mesh: AgentMesh, require_auth=None):
    """Register Hermes Protocol API routes on a FastAPI app."""

    from fastapi import Depends, Body, HTTPException, Query

    @app.get("/api/hermes/status")
    async def hermes_status(auth=Depends(require_auth) if require_auth else None):
        """Full mesh status: agents + queue stats + recent tasks."""
        return await mesh.snapshot()

    @app.get("/api/hermes/queue")
    async def hermes_queue(
        status: Optional[str] = Query(None),
        task_type: Optional[str] = Query(None),
        limit: int = Query(50),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """List tasks in the queue with optional filters."""
        tasks = await mesh.list_tasks(
            status=status,
            task_type=task_type,
            limit=min(limit, 200),
        )
        return {"tasks": tasks, "count": len(tasks)}

    @app.get("/api/hermes/agents")
    async def hermes_agents(auth=Depends(require_auth) if require_auth else None):
        """List all registered agents."""
        agents = await mesh.get_agents()
        return {"agents": agents}

    @app.post("/api/hermes/tasks")
    async def hermes_create_task(
        payload: dict = Body(...),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Create a new task ticket."""
        task_type = payload.get("task_type")
        if not task_type:
            raise HTTPException(400, "task_type is required")
        ticket_id = await mesh.create_task(
            task_type=task_type,
            payload=payload.get("payload", {}),
            assigned_agent=payload.get("assigned_agent"),
            priority=payload.get("priority", 0),
        )
        if not ticket_id:
            raise HTTPException(500, "Failed to create task")
        return {"ok": True, "ticket_id": ticket_id}

    @app.post("/api/hermes/tasks/{ticket_id}/status")
    async def hermes_update_task(
        ticket_id: str,
        payload: dict = Body(...),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Update a task's status (Done, Failed, Blocked, etc.)."""
        status = payload.get("status")
        if not status:
            raise HTTPException(400, "status is required")
        await mesh.update_task_status(
            ticket_id=ticket_id,
            status=status,
            result=payload.get("result"),
            error=payload.get("error"),
        )
        return {"ok": True}

    @app.get("/api/hermes/tasks/{ticket_id}")
    async def hermes_get_task(
        ticket_id: str,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get a single task by ticket_id."""
        task = await mesh.get_task(ticket_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return task

    log.info("[hermes] routes registered: /api/hermes/{status,queue,agents,tasks}")
