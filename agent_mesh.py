"""
EMPIRE V49 · AGENT MESH (HERMES PROTOCOL)
=========================================
Kanban task queue + agent orchestration system.
All agents use local Ollama for language generation.

Tables used:
  - agent_task_queue: Task tickets with status (To-Do, In Progress, Blocked, Done, Failed)
  - agent_registry: Agent heartbeat, capabilities, and metrics

Agent teams:
  Scouting    → Prospector → Outreach
  Studio      → Copy      → Render
  Revenue     → Dispatcher → Quality
  Browser     → Scraper
  Orchestrator → Autoresearch
  Sovereign   → Strategy-Decide → Self-Aware → Niche-Analyze → Regime-Detect → AGI-Optimize

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
TASK_EMAIL_EXECUTE          = "email.execute"
TASK_DESIGN_EXECUTE         = "design.execute"
TASK_MARKETING_EXECUTE      = "marketing.execute"
TASK_BROWSER_SCRAPE         = "browser.scrape"
TASK_BROWSER_AUTOMATE       = "browser.automate"
TASK_SCRAPE_WEB             = "scrape.web"
TASK_SCRAPE_CRAWL           = "scrape.crawl"
TASK_AGENTIC_PLAN           = "agentic.plan"
TASK_AGENTIC_REVIEW         = "agentic.review"
TASK_AUTORESEARCH_RUN       = "autoresearch.run"
TASK_AUTORESEARCH_ORCHESTRATE = "autoresearch.orchestrate"
TASK_CONSULTING_STRATEGY    = "consulting.strategy"
TASK_MESH_DELEGATE          = "mesh.delegate"
TASK_SOVEREIGN_STRATEGY_DECIDE = "sovereign.strategy_decide"
TASK_SOVEREIGN_SELF_AWARE      = "sovereign.self_aware"
TASK_SOVEREIGN_NICHE_ANALYZE   = "sovereign.niche_analyze"
TASK_SOVEREIGN_REGIME_DETECT   = "sovereign.regime_detect"
TASK_SOVEREIGN_AGI_OPTIMIZE    = "sovereign.agi_optimize"

# ── Sovereign AGI Matrix route mapping ──────────────────────────────
# Used by execute_sovereign_skill() and mesh_sovereign_worker.py
SOVEREIGN_MATRIX_ROUTES = {
    TASK_SOVEREIGN_STRATEGY_DECIDE: "/api/v6/matrix/strategy-decide",
    TASK_SOVEREIGN_SELF_AWARE:      "/api/v6/matrix/self-aware",
    TASK_SOVEREIGN_NICHE_ANALYZE:   "/api/v6/matrix/niche-analyze",
    TASK_SOVEREIGN_REGIME_DETECT:   "/api/v6/matrix/regime-detect",
    TASK_SOVEREIGN_AGI_OPTIMIZE:    "/api/v6/matrix/agi-optimize",
}

ALL_TASK_TYPES = [
    # Core fleet
    TASK_SCOUT_FIND_ROOFS,
    TASK_OUTREACH_DRAFT_EMAIL,
    TASK_STUDIO_WRITE_SCRIPT,
    TASK_STUDIO_RENDER_REEL,
    TASK_REVENUE_CONNECT_BUYER,
    TASK_REVENUE_SCORE_CALL,
    TASK_SWARM_FIRE,
    TASK_SWARM_STRIKE_VIDEO,
    TASK_EMAIL_EXECUTE,
    TASK_DESIGN_EXECUTE,
    TASK_MARKETING_EXECUTE,
    TASK_BROWSER_SCRAPE,
    TASK_BROWSER_AUTOMATE,
    TASK_SCRAPE_WEB,
    TASK_SCRAPE_CRAWL,
    TASK_AGENTIC_PLAN,
    TASK_AGENTIC_REVIEW,
    TASK_AUTORESEARCH_RUN,
    TASK_AUTORESEARCH_ORCHESTRATE,
    # Consulting & Delegation
    TASK_CONSULTING_STRATEGY,
    TASK_MESH_DELEGATE,
    # Sovereign AGI
    TASK_SOVEREIGN_STRATEGY_DECIDE,
    TASK_SOVEREIGN_SELF_AWARE,
    TASK_SOVEREIGN_NICHE_ANALYZE,
    TASK_SOVEREIGN_REGIME_DETECT,
    TASK_SOVEREIGN_AGI_OPTIMIZE,
    # Memory
    "memory.store",
    "memory.retrieve",
    # Prompts
    "prompts.optimize",
    # Scientific
    "scientific.research",
    # Marketing — campaigns & outreach (names match registered skills: skills/marketing_skills.py)
    "marketing.emails",
    "marketing.cold-email",
    "marketing.sms",
    "marketing.ads",
    "marketing.copywriting",
    "marketing.social",
    "marketing.analytics",
    "marketing.video",
    "marketing.cro",
    "marketing.content-strategy",
    "marketing.referrals",
    "marketing.revops",
    "marketing.product",
    "marketing.seo-audit",
    "marketing.lead-magnets",
    "marketing.prospecting",
    "marketing.ad-creative",
    "marketing.ab-testing",
    "marketing.onboarding",
    "marketing.signup",
    "marketing.offers",
    "marketing.launch",
    "marketing.customer-research",
    "marketing.ideas",
    "marketing.pr",
    "marketing.co-marketing",
    "marketing.community",
    "marketing.image",
    "marketing.copy-editing",
    "marketing.programmatic-seo",
    "marketing.schema",
    "marketing.ai-seo",
    "marketing.aso",
    "marketing.free-tools",
    "marketing.directory-submissions",
    "marketing.churn-prevention",
    "marketing.competitor-profiling",
    "marketing.competitors",
    "marketing.marketing-plan",
    "marketing.marketing-psychology",
    "marketing.pricing",
    "marketing.sales-enablement",
    "marketing.site-architecture",
    "marketing.popups",
    "marketing.paywalls",
    # SEO skills
    "marketing.keyword-research",
    "marketing.link-building",
    "marketing.local-seo",
    "marketing.technical-seo",
    # Content / social
    "content.seo",
    "social.scraper",
    "social.facebook-bot",
    # Design — UI
    "design.ui-component",
    "design.ui-layout",
    "design.ui-screen",
    # Design — UX
    "design.ux-flow",
    "design.ux-wireframe",
    "design.ux-prototype",
    "design.ux-research",
    # Design — Visual
    "design.visual-brand",
    "design.visual-color",
    "design.visual-typography",
    "design.visual-iconography",
    "design.visual-data-viz",
    # Design — System
    "design.system-tokens",
    "design.system-component-library",
    "design.system-documentation",
    # Design — Motion
    "design.motion-microinteractions",
    "design.motion-transitions",
    "design.motion-loading",
    # Design — Accessibility
    "design.a11y-color",
    "design.a11y-interaction",
    "design.a11y-audit",
    # Design — Ops
    "design.ops-workflow",
    "design.ops-critique",
    "design.ops-design-sprint",
    # Design — Web builder
    "design.web-builder",
    # Email — Strategy & planning
    "email.strategy",
    "email.calendar",
    "email.sequence",
    "email.drip",
    "email.nurture",
    "email.re-engagement",
    # Email — Deliverability & compliance
    "email.deliverability",
    "email.authentication",
    "email.warmup",
    "email.list-hygiene",
    "email.compliance-can-spam",
    "email.compliance-gdpr",
    "email.compliance-casl",
    # Email — Copy
    "email.copy-subject",
    "email.copy-body",
    "email.copy-cta",
    # Email — Analytics & testing
    "email.analytics",
    "email.ab-testing",
    "email.optimization",
    # Email — Technical
    "email.api",
    "email.template",
    "email.personalization",
    "email.inbound",
    "email.provider-resend",
    "email.provider-listmonk",

]

# ── Agent name constants ─────────────────────────────────────────────
AGENT_SCOUT          = "mesh.scout"
AGENT_OUTREACH       = "mesh.outreach"
AGENT_STUDIO_COPY    = "mesh.studio_copy"
AGENT_STUDIO_RENDER  = "mesh.studio_render"
AGENT_DISPATCHER     = "mesh.dispatcher"
AGENT_QUALITY        = "mesh.quality"
AGENT_SWARM_WORKER   = "mesh.swarm_worker"
AGENT_EMAIL          = "mesh.email"
AGENT_DESIGN         = "mesh.design"
AGENT_MARKETING      = "mesh.marketing"
AGENT_BROWSER        = "mesh.browser"
AGENT_SCRAPER        = "mesh.scraper"
AGENT_ORCHESTRATOR   = "mesh.orchestrator"
AGENT_AUTORESEARCH   = "mesh.autoresearch"
AGENT_SOVEREIGN      = "mesh.sovereign"

# ── Agent → task types mapping ───────────────────────────────────────
AGENT_TASK_MAP = {
    AGENT_SCOUT:         [TASK_SCOUT_FIND_ROOFS],
    AGENT_OUTREACH:      [TASK_OUTREACH_DRAFT_EMAIL],
    AGENT_STUDIO_COPY:   [TASK_STUDIO_WRITE_SCRIPT],
    AGENT_STUDIO_RENDER: [TASK_STUDIO_RENDER_REEL],
    AGENT_DISPATCHER:    [TASK_REVENUE_CONNECT_BUYER],
    AGENT_QUALITY:       [TASK_REVENUE_SCORE_CALL],
    AGENT_SWARM_WORKER:  [TASK_SWARM_FIRE, TASK_SWARM_STRIKE_VIDEO],
    AGENT_EMAIL:         [TASK_EMAIL_EXECUTE],
    AGENT_DESIGN:        [TASK_DESIGN_EXECUTE],
    AGENT_MARKETING:     [TASK_MARKETING_EXECUTE],
    AGENT_BROWSER:       [TASK_BROWSER_SCRAPE, TASK_BROWSER_AUTOMATE],
    AGENT_SCRAPER:       [TASK_SCRAPE_WEB, TASK_SCRAPE_CRAWL],
    AGENT_ORCHESTRATOR:  [TASK_AGENTIC_PLAN, TASK_AGENTIC_REVIEW, TASK_AUTORESEARCH_ORCHESTRATE, TASK_CONSULTING_STRATEGY, TASK_MESH_DELEGATE],
    AGENT_AUTORESEARCH:  [TASK_AUTORESEARCH_RUN],
    AGENT_SOVEREIGN:     [
        TASK_SOVEREIGN_STRATEGY_DECIDE,
        TASK_SOVEREIGN_SELF_AWARE,
        TASK_SOVEREIGN_NICHE_ANALYZE,
        TASK_SOVEREIGN_REGIME_DETECT,
        TASK_SOVEREIGN_AGI_OPTIMIZE,
    ],
}

AGENT_CAPABILITIES = {
    AGENT_SCOUT:         ["scout", "prospector", "satellite"],
    AGENT_OUTREACH:      ["outreach", "email", "drafting"],
    AGENT_STUDIO_COPY:   ["studio", "copy", "creative", "scripting"],
    AGENT_STUDIO_RENDER: ["studio", "render", "ffmpeg", "video"],
    AGENT_DISPATCHER:    ["dispatcher", "buyer", "revenue"],
    AGENT_QUALITY:       ["quality", "analyst", "scoring"],
    AGENT_SWARM_WORKER:  ["swarm", "tts", "kokoro", "ollama", "ffmpeg", "video_render"],
    AGENT_EMAIL:         ["email", "marketing", "automation", "strategy", "deliverability", "compliance"],
    AGENT_DESIGN:        ["design", "ui", "ux", "visual", "motion", "a11y", "brand"],
    AGENT_MARKETING:     ["marketing", "email", "seo", "content", "social", "ads", "cro", "analytics", "brand", "campaigns"],
    AGENT_BROWSER:       ["browser", "scrape", "automate", "playwright"],
    AGENT_SCRAPER:       ["scraper", "web", "extract", "crawl"],
    AGENT_ORCHESTRATOR:  ["orchestrator", "planning", "review", "meta"],
    AGENT_AUTORESEARCH:  ["autoresearch", "experiment", "self-healing"],
    AGENT_SOVEREIGN:     ["sovereign", "agi", "strategy", "self-awareness", "bayesian", "optimization", "regime-detection"],
}

# ── Agent display names ──────────────────────────────────────────────
AGENT_DISPLAY = {
    AGENT_SCOUT:         "Scout (Prospector)",
    AGENT_OUTREACH:      "Outreach Agent",
    AGENT_STUDIO_COPY:   "Studio Copy",
    AGENT_STUDIO_RENDER: "Studio Render",
    AGENT_DISPATCHER:    "Dispatcher",
    AGENT_QUALITY:       "Quality Analyst",
    AGENT_SWARM_WORKER:  "Swarm Worker",
    AGENT_EMAIL:         "Email Marketing Agent",
    AGENT_DESIGN:        "Design Agent",
    AGENT_MARKETING:     "Marketing Agent",
    AGENT_BROWSER:       "Browser Agent",
    AGENT_SCRAPER:       "Scraper Agent",
    AGENT_ORCHESTRATOR:  "Orchestrator",
    AGENT_AUTORESEARCH:  "Autoresearch Agent",
    AGENT_SOVEREIGN:     "Sovereign AGI",
}

# ── Mesh agent → Fleet role mapping ─────────────────────────────────
MESH_AGENT_ROLES = {
    AGENT_SCOUT:         "mesh_scout",
    AGENT_OUTREACH:      "mesh_outreach",
    AGENT_STUDIO_COPY:   "mesh_studio_copy",
    AGENT_STUDIO_RENDER: "mesh_studio_render",
    AGENT_DISPATCHER:    "mesh_dispatcher",
    AGENT_QUALITY:       "quality_analyst",
    AGENT_SWARM_WORKER:  "swarm_worker",
    AGENT_EMAIL:         "mesh_email",
    AGENT_DESIGN:        "mesh_design",
    AGENT_MARKETING:     "mesh_marketing",
    AGENT_BROWSER:       "mesh_browser",
    AGENT_SCRAPER:       "mesh_scraper",
    AGENT_ORCHESTRATOR:  "mesh_orchestrator",
    AGENT_AUTORESEARCH:  "mesh_autoresearch",
    AGENT_SOVEREIGN:     "mesh_sovereign",
}

# ── Task type → registered skill name translation ──────────────────────
# Maps deprecated/legacy task type names to the canonical registered skill
# names so stale tasks still resolve correctly when the mesh.marketing
# worker calls /api/hermes/execute-skill.
TASK_TYPE_TO_SKILL = {
    # Marketing — old dot-separated convention → hyphenated skill names
    "marketing.email.campaign":   "marketing.emails",
    "marketing.cold.outreach":    "marketing.cold-email",
    "marketing.conversion":       "marketing.cro",
    "marketing.sms.campaign":     "marketing.sms",
    "marketing.seo.content":      "marketing.content-strategy",
    "marketing.paid.ads":         "marketing.ads",
    "marketing.copy":             "marketing.copywriting",
    "marketing.social.publish":   "marketing.social",
    "marketing.automation":       "marketing.revops",
    "marketing.brand":            "marketing.product",
    "marketing.content.strategy": "marketing.content-strategy",
    "marketing.lead.nurture":     "marketing.lead-magnets",
    "marketing.referral":         "marketing.referrals",
    "marketing.advertising":      "marketing.ads",
    "marketing.seo-expert":       "marketing.seo-audit",
    "marketing.technical-seo":    "marketing.site-architecture",
    # Design — legacy dot-separated names → hyphenated skill names
    "design.ui.component":        "design.ui-component",
    "design.ui.layout":           "design.ui-layout",
    "design.ui.screen":           "design.ui-screen",
    "design.ux.flow":             "design.ux-flow",
    "design.ux.wireframe":        "design.ux-wireframe",
    "design.ux.prototype":        "design.ux-prototype",
    "design.ux.research":         "design.ux-research",
    "design.visual.brand":        "design.visual-brand",
    "design.visual.color":        "design.visual-color",
    "design.visual.typography":   "design.visual-typography",
    "design.visual.iconography":  "design.visual-iconography",
    "design.visual.data-viz":     "design.visual-data-viz",
    "design.system.tokens":       "design.system-tokens",
    "design.system.documentation":"design.system-documentation",
    "design.system.component-library": "design.system-component-library",
    "design.motion.microinteractions": "design.motion-microinteractions",
    "design.motion.transition":   "design.motion-transitions",
    "design.motion.loading":      "design.motion-loading",
    "design.a11y.color":          "design.a11y-color",
    "design.a11y.interaction":    "design.a11y-interaction",
    "design.a11y.audit":          "design.a11y-audit",
    "design.ops.workflow":        "design.ops-workflow",
    "design.ops.critique":        "design.ops-critique",
    "design.ops.design-sprint":   "design.ops-design-sprint",
}


class AgentMesh:
    """Kanban task queue orchestrator. Manages task lifecycle and agent coordination."""

    def __init__(self, get_db: Callable[[], Client], router=None, harness_mgr=None):
        self._get_db = get_db
        self.router = router
        self.harness_mgr = harness_mgr  # Skills Framework HarnessManager for direct skill execution
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

    # ── Skill execution via HarnessManager ────────────────────────────

    async def execute_skill(self, skill_name: str, params: dict = None) -> dict:
        """Execute a skill from the Skills Framework via the HarnessManager.

        Dispatches to harness_mgr.run(skill_name, params) which handles
        timeout, retries, circuit breaker, and dependency injection.

        AGI/SI/PR context is automatically injected by the HarnessManager's
        SkillHarness._build_context() into the SkillInput.context, so all
        skills have access to live AGI Governor strategy, SI genome traits,
        and Predictive Revenue data without additional wiring.

        Args:
            skill_name: Fully qualified skill name (e.g. "email.strategy",
                        "design.visual-color", "marketing.emails")
            params: Skill execution parameters (audience, goal, constraints, etc.)

        Returns:
            dict with skill result including llm_output, execution_mode,
            agi_context (in result), or error details if execution failed.
        """
        if not self.harness_mgr:
            return {"ok": False, "error": "HarnessManager not wired — skills framework not initialized"}

        params = params or {}

        try:
            output = await self.harness_mgr.run(skill_name, params)
            if output.success and output.data:
                return {"ok": True, "skill": skill_name, "result": output.data}
            return {"ok": False, "skill": skill_name, "error": output.error or "execution failed"}
        except KeyError:
            return {"ok": False, "skill": skill_name, "error": f"Skill '{skill_name}' not registered"}
        except Exception as e:
            log.error(f"[hermes] execute_skill error ({skill_name}): {e}")
            return {"ok": False, "skill": skill_name, "error": str(e)[:500]}

    async def execute_email_skill(self, skill_name: str, params: dict = None) -> dict:
        """Execute an email marketing skill.

        Convenience wrapper that validates the skill is in the email.* namespace.
        """
        if not skill_name.startswith("email."):
            return {"ok": False, "skill": skill_name, "error": f"Not an email skill: {skill_name}"}
        return await self.execute_skill(skill_name, params)

    async def execute_design_skill(self, skill_name: str, params: dict = None) -> dict:
        """Execute a design skill.

        Convenience wrapper that validates the skill is in the design.* namespace.
        Translates legacy task type names (dot-separated) to registered skill names
        (hyphen-separated) via TASK_TYPE_TO_SKILL so stale queue tasks still resolve correctly.
        """
        if not skill_name.startswith("design."):
            return {"ok": False, "skill": skill_name, "error": f"Not a design skill: {skill_name}"}
        resolved = TASK_TYPE_TO_SKILL.get(skill_name, skill_name)
        if resolved != skill_name:
            log.info(f"[hermes] translated design task type '{skill_name}' → skill '{resolved}'")
        return await self.execute_skill(resolved, params)

    async def execute_marketing_skill(self, skill_name: str, params: dict = None) -> dict:
        """Execute a marketing skill.

        Convenience wrapper that validates the skill is in the marketing.* namespace.
        Translates legacy task type names to registered skill names via
        TASK_TYPE_TO_SKILL so stale queue tasks still resolve correctly.
        """
        if not skill_name.startswith("marketing."):
            return {"ok": False, "skill": skill_name, "error": f"Not a marketing skill: {skill_name}"}
        resolved = TASK_TYPE_TO_SKILL.get(skill_name, skill_name)
        if resolved != skill_name:
            log.info(f"[hermes] translated task type '{skill_name}' → skill '{resolved}'")
        return await self.execute_skill(resolved, params)

    async def execute_social_skill(self, skill_name: str, params: dict = None) -> dict:
        """Execute a social media skill.

        Convenience wrapper that validates the skill is in the social.* namespace.
        Supports external GitHub repo skills (e.g. social.deepgram).
        """
        if not skill_name.startswith("social."):
            return {"ok": False, "skill": skill_name, "error": f"Not a social skill: {skill_name}"}
        return await self.execute_skill(skill_name, params)

    async def execute_sovereign_skill(self, skill_name: str, params: dict = None) -> dict:
        """Execute a sovereign AGI skill by proxying to the Sovereign AGI Matrix on port 8010.

        Maps sovereign.* task types to matrix endpoints:
          sovereign.strategy_decide → POST /api/v6/matrix/strategy-decide
          sovereign.self_aware      → POST /api/v6/matrix/self-aware
          sovereign.niche_analyze   → POST /api/v6/matrix/niche-analyze
          sovereign.regime_detect   → POST /api/v6/matrix/regime-detect
          sovereign.agi_optimize    → POST /api/v6/matrix/agi-optimize
        """
        if not skill_name.startswith("sovereign."):
            return {"ok": False, "skill": skill_name, "error": f"Not a sovereign skill: {skill_name}"}

        params = params or {}

        # Map task type → matrix endpoint path (single source: SOVEREIGN_MATRIX_ROUTES)
        endpoint = SOVEREIGN_MATRIX_ROUTES.get(skill_name)
        if not endpoint:
            return {"ok": False, "skill": skill_name, "error": f"No matrix route mapped for '{skill_name}'"}

        try:
            import httpx
            SOVEREIGN_MATRIX_URL = os.environ.get("SOVEREIGN_MATRIX_URL", "http://localhost:8010")
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{SOVEREIGN_MATRIX_URL}{endpoint}",
                    json=params,
                    timeout=120.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"ok": True, "skill": skill_name, "result": data}
                return {
                    "ok": False,
                    "skill": skill_name,
                    "error": f"Matrix returned {resp.status_code}: {resp.text[:300]}",
                }
        except Exception as e:
            log.error(f"[hermes] sovereign skill error ({skill_name}): {e}")
            return {"ok": False, "skill": skill_name, "error": f"Matrix unreachable: {str(e)[:200]}"}

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
    from fastapi.responses import JSONResponse

    # ── Skill execution endpoint (called by mesh.marketing worker) ──
    @app.post("/api/hermes/execute-skill")
    async def hermes_execute_skill(
        payload: dict = Body(...),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Execute a skill via the Skills Framework HarnessManager.

        Used by the mesh.marketing worker to run marketing skills
        without needing to import the full framework.

        Body:
          skill_name: str — the fully qualified skill name
          params: dict — skill execution parameters

        Returns:
          ok: bool
          result: skill output (if ok)
          error: error message (if not ok)
        """
        skill_name = payload.get("skill_name", "")
        params = payload.get("params", {})
        if not skill_name:
            raise HTTPException(400, "skill_name is required")

        # Route to the appropriate convenience wrapper
        if skill_name.startswith("marketing."):
            result = await mesh.execute_marketing_skill(skill_name, params)
        elif skill_name.startswith("email."):
            result = await mesh.execute_email_skill(skill_name, params)
        elif skill_name.startswith("design."):
            result = await mesh.execute_design_skill(skill_name, params)
        elif skill_name.startswith("social."):
            result = await mesh.execute_social_skill(skill_name, params)
        elif skill_name.startswith("sovereign."):
            result = await mesh.execute_sovereign_skill(skill_name, params)
        else:
            result = await mesh.execute_skill(skill_name, params)

        status = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status)

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
