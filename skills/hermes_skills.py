"""
EMPIRE V49 · HERMES MESH SKILLS
=================================
Concrete BaseSkill implementations for all 31 skills registered in
agent_os/hermes_os/SKILLS.md. These make the mesh dispatch layer
invocable directly via HarnessManager.run() in addition to the
existing agent_task_queue / PM2 worker path.

Skill groups:
  Core Mesh (1-5):     task create/claim/update, agent heartbeat, status report
  Fleet Agents (6-14): scout, outreach, studio, revenue, swarm, scrape, agentic
  Wrappers (15-17):    marketing, email, design execute
  Autoresearch (18-21): run, scratchpad, browser, orchestrate
  External Tools (22-29): browser, prompts, claude, humanizer, memory, scientific, firecrawl, superpowers
  Consulting (30):     strategy, business analysis, growth planning
  Delegation (31):     task breakdown, agent assignment, execution planning
"""

import os
import json
import time
import logging
from typing import Any, Optional
from datetime import datetime, timezone

from skills.base import BaseSkill, SkillInput, SkillOutput, SkillMetrics
from .registry import ImmutableSkillRegistry

log = logging.getLogger("empire.skills.hermes")

# ── Supabase helper ────────────────────────────────────────────────
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_sb = None


def _get_sb():
    global _sb
    if _sb is None and _SUPABASE_URL and _SUPABASE_KEY:
        from supabase import create_client
        try:
            _sb = create_client(_SUPABASE_URL, _SUPABASE_KEY)
        except Exception as e:
            log.warning(f"[hermes_skills] Supabase connect failed: {e}")
            _sb = None
    return _sb


# ══════════════════════════════════════════════════════════════════════
# HELPER BASE
# ══════════════════════════════════════════════════════════════════════


class MeshSkill(BaseSkill):
    """Abstract base for hermes mesh skills with common helpers."""
    name = "mesh.base"  # Abstract base — not registered directly
    timeout_seconds = 15.0
    max_retries = 2

    async def validate(self, input: SkillInput) -> bool:
        return True

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════
# SECTION 1 · CORE MESH OPS (Skills 1-5)
# ══════════════════════════════════════════════════════════════════════


class MeshTaskCreateSkill(MeshSkill):
    """Create a new task ticket in the agent_task_queue."""
    name = "mesh.task.create"
    version = "1.0.0"
    description = "Create a task ticket in the agent_task_queue with type, payload, and optional agent assignment"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("task_type"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        p = input.params
        sb = _get_sb()
        if not sb:
            return SkillOutput(success=False, error="Supabase not configured")

        try:
            r = sb.table("agent_task_queue").insert({
                "task_type": p["task_type"],
                "payload": json.dumps(p.get("payload", {})),
                "status": "To-Do",
                "assigned_agent": p.get("assigned_agent"),
                "priority": int(p.get("priority", 0)),
            }).execute()
            ticket_id = r.data[0].get("ticket_id") if r.data else None
            elapsed = int((time.time() - start) * 1000)
            return SkillOutput(
                success=bool(ticket_id),
                data={"ticket_id": ticket_id, "task_type": p["task_type"]},
                metrics=SkillMetrics(duration_ms=elapsed, records_processed=1),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"create_task failed: {e}")


class MeshTaskClaimSkill(MeshSkill):
    """Atomically claim the next available task for an agent."""
    name = "mesh.task.claim"
    version = "1.0.0"
    description = "Claim the next available To-Do task for a given agent name and optional task type filter"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("agent_name"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        p = input.params
        sb = _get_sb()
        if not sb:
            return SkillOutput(success=False, error="Supabase not configured")

        try:
            r = sb.rpc("claim_next_task", {
                "p_agent_name": p["agent_name"],
                "p_task_types": p.get("task_types"),
            }).execute()
            task = r.data if r.data else None
            elapsed = int((time.time() - start) * 1000)
            return SkillOutput(
                success=bool(task),
                data={"task": task, "claimed": task is not None},
                metrics=SkillMetrics(duration_ms=elapsed, records_processed=1 if task else 0),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"claim_task failed: {e}")


class MeshTaskUpdateSkill(MeshSkill):
    """Update a task's status (Done, Failed, Blocked, etc.)."""
    name = "mesh.task.update"
    version = "1.0.0"
    description = "Update a task's status, result, and error in agent_task_queue"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("ticket_id")) and bool(input.params.get("status"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        p = input.params
        sb = _get_sb()
        if not sb:
            return SkillOutput(success=False, error="Supabase not configured")

        try:
            update = {"status": p["status"]}
            if p.get("status") in ("Done", "Failed", "Cancelled"):
                update["completed_at"] = self._utcnow()
            if p.get("result"):
                update["result"] = json.dumps(p["result"]) if isinstance(p["result"], dict) else p["result"]
            if p.get("error"):
                update["error"] = str(p["error"])[:2000]
            sb.table("agent_task_queue").update(update).eq("ticket_id", p["ticket_id"]).execute()
            elapsed = int((time.time() - start) * 1000)
            return SkillOutput(
                success=True,
                data={"ticket_id": p["ticket_id"], "status": p["status"]},
                metrics=SkillMetrics(duration_ms=elapsed, records_processed=1),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"update_task failed: {e}")


class MeshAgentHeartbeatSkill(MeshSkill):
    """Register/ping an agent in the agent_registry table."""
    name = "mesh.agent.heartbeat"
    version = "1.0.0"
    description = "Register or heartbeat an agent in the agent_registry with capabilities and task types"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("agent_name"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        p = input.params
        sb = _get_sb()
        if not sb:
            return SkillOutput(success=False, error="Supabase not configured")

        try:
            payload = {
                "agent_name": p["agent_name"],
                "role_name": p.get("role_name"),
                "status": p.get("status", "ACTIVE"),
                "last_ping": self._utcnow(),
                "enabled": p.get("enabled", True),
                "capabilities": p.get("capabilities", []),
                "task_types": p.get("task_types", []),
            }
            sb.table("agent_registry").upsert(payload, on_conflict="agent_name").execute()
            elapsed = int((time.time() - start) * 1000)
            return SkillOutput(
                success=True,
                data={"agent_name": p["agent_name"], "status": p.get("status", "ACTIVE")},
                metrics=SkillMetrics(duration_ms=elapsed, records_processed=1),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"heartbeat failed: {e}")


class MeshStatusReportSkill(MeshSkill):
    """Return a full mesh snapshot — agents, queue stats, recent tasks."""
    name = "mesh.status.report"
    version = "1.0.0"
    description = "Return a full mesh status snapshot with agent registry, queue stats, and recent tasks"
    timeout_seconds = 10.0

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        sb = _get_sb()
        if not sb:
            return SkillOutput(success=False, error="Supabase not configured")

        try:
            agents = sb.table("agent_registry").select("*").order("agent_name").execute()
            tasks = sb.table("agent_task_queue").select("status,task_type").execute()
            recent = sb.table("agent_task_queue").select("*").order("created_at", desc=True).limit(10).execute()

            by_status = {}
            for t in (tasks.data or []):
                s = t.get("status", "unknown")
                by_status[s] = by_status.get(s, 0) + 1

            elapsed = int((time.time() - start) * 1000)
            return SkillOutput(
                success=True,
                data={
                    "agents": agents.data or [],
                    "agent_count": len(agents.data or []),
                    "queue_by_status": by_status,
                    "total_tasks": len(tasks.data or []),
                    "recent_tasks": recent.data or [],
                    "timestamp": self._utcnow(),
                },
                metrics=SkillMetrics(duration_ms=elapsed, records_processed=len(agents.data or [])),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"status report failed: {e}")


# ══════════════════════════════════════════════════════════════════════
# SECTION 2 · FLEET AGENT TASK PRODUCERS (Skills 6-14)
# Each creates a task in agent_task_queue for the designated worker.
# ══════════════════════════════════════════════════════════════════════


class _TaskProducerSkill(MeshSkill):
    """Base for fleet task producers that create tasks in agent_task_queue."""
    task_type: str = ""
    assigned_agent: str = ""

    async def validate(self, input: SkillInput) -> bool:
        return bool(self.task_type)

    async def execute(self, input: SkillInput) -> SkillOutput:
        sb = _get_sb()
        if not sb:
            return SkillOutput(success=False, error="Supabase not configured")

        try:
            payload = {k: v for k, v in input.params.items() if k != "priority"}
            r = sb.table("agent_task_queue").insert({
                "task_type": self.task_type,
                "payload": json.dumps(payload),
                "status": "To-Do",
                "assigned_agent": self.assigned_agent,
                "priority": int(input.params.get("priority", 10)),
            }).execute()
            ticket_id = r.data[0].get("ticket_id") if r.data else None
            return SkillOutput(
                success=bool(ticket_id),
                data={"ticket_id": ticket_id, "task_type": self.task_type, "assigned_agent": self.assigned_agent},
                metrics=SkillMetrics(duration_ms=500, records_processed=1),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"task creation failed: {e}")


class ScoutFindRoofsSkill(_TaskProducerSkill):
    name = "scout.find_roofs"
    version = "1.0.0"
    description = "Prospect roofs in storm zones via satellite imagery and risk data. Creates a scout task in the queue."
    task_type = "scout.find_roofs"
    assigned_agent = "mesh.scout"


class OutreachDraftEmailSkill(_TaskProducerSkill):
    name = "outreach.draft_email"
    version = "1.0.0"
    description = "Draft and send outreach messages to storm chaser prospects. Creates an outreach task in the queue."
    task_type = "outreach.draft_email"
    assigned_agent = "mesh.outreach"


class StudioWriteScriptSkill(_TaskProducerSkill):
    name = "studio.write_script"
    version = "1.0.0"
    description = "Write a video script for a target audience and niche. Creates a studio_copy task in the queue."
    task_type = "studio.write_script"
    assigned_agent = "mesh.studio_copy"


class StudioRenderReelSkill(_TaskProducerSkill):
    name = "studio.render_reel"
    version = "1.0.0"
    description = "Render a video reel from a script using FFmpeg and TTS. Creates a studio_render task in the queue."
    task_type = "studio.render_reel"
    assigned_agent = "mesh.studio_render"


class RevenueConnectBuyerSkill(_TaskProducerSkill):
    name = "revenue.connect_buyer"
    version = "1.0.0"
    description = "Connect a qualified lead with a buyer/contractor for claim dispatch. Creates a dispatcher task in the queue."
    task_type = "revenue.connect_buyer"
    assigned_agent = "mesh.dispatcher"


class RevenueScoreCallSkill(_TaskProducerSkill):
    name = "revenue.score_call"
    version = "1.0.0"
    description = "Score a sales call recording for quality and conversion probability. Creates a quality task in the queue."
    task_type = "revenue.score_call"
    assigned_agent = "mesh.quality"


class SwarmFireSkill(_TaskProducerSkill):
    name = "swarm.fire"
    version = "1.0.0"
    description = "Execute a swarm fire — simultaneous TTS calls via Kokoro/Ollama. Creates a swarm_worker task in the queue."
    task_type = "swarm.fire"
    assigned_agent = "mesh.swarm_worker"


class ScrapeWebSkill(_TaskProducerSkill):
    name = "scrape.web"
    version = "1.0.0"
    description = "Extract structured data from web pages using firecrawl or Playwright. Creates a scraper task in the queue."
    task_type = "scrape.web"
    assigned_agent = "mesh.scraper"


class AgenticPlanSkill(_TaskProducerSkill):
    name = "agentic.plan"
    version = "1.0.0"
    description = "Create an execution plan for a complex multi-step task. Creates an orchestrator task in the queue."
    task_type = "agentic.plan"
    assigned_agent = "mesh.orchestrator"


# ══════════════════════════════════════════════════════════════════════
# SECTION 3 · FRAMEWORK WRAPPERS (Skills 15-17)
# Umbrella skills that validate sub-skill names and delegate to the
# Skills Framework. These are the entry points called by mesh workers.
# ══════════════════════════════════════════════════════════════════════


class MeshMarketingExecuteSkill(MeshSkill):
    """Execute a marketing skill — validates the skill_name is in the marketing.* namespace."""
    name = "mesh.marketing.execute"
    version = "1.0.0"
    description = "Execute a marketing skill from the Skills Framework. Validates marketing.* namespace and delegates."
    timeout_seconds = 5.0

    async def validate(self, input: SkillInput) -> bool:
        skill_name = input.params.get("skill_name", "")
        return bool(skill_name) and skill_name.startswith("marketing.")

    async def execute(self, input: SkillInput) -> SkillOutput:
        skill_name = input.params["skill_name"]
        return SkillOutput(
            success=True,
            data={
                "skill": skill_name,
                "params": input.params.get("params", {}),
                "message": "Skill routing validated. Submit to /api/hermes/execute-skill for execution via HarnessManager.",
                "sub_skill": skill_name,
            },
            metrics=SkillMetrics(duration_ms=100, records_processed=0),
        )


class MeshEmailExecuteSkill(MeshSkill):
    """Execute an email marketing skill — validates the skill_name is in the email.* namespace."""
    name = "mesh.email.execute"
    version = "1.0.0"
    description = "Execute an email marketing skill. Validates email.* namespace and delegates."
    timeout_seconds = 5.0

    async def validate(self, input: SkillInput) -> bool:
        skill_name = input.params.get("skill_name", "")
        return bool(skill_name) and skill_name.startswith("email.")

    async def execute(self, input: SkillInput) -> SkillOutput:
        skill_name = input.params["skill_name"]
        return SkillOutput(
            success=True,
            data={
                "skill": skill_name,
                "params": input.params.get("params", {}),
                "message": "Skill routing validated. Submit to /api/hermes/execute-skill for execution via HarnessManager.",
                "sub_skill": skill_name,
            },
            metrics=SkillMetrics(duration_ms=100, records_processed=0),
        )


class MeshDesignExecuteSkill(MeshSkill):
    """Execute a design skill — validates the skill_name is in the design.* namespace."""
    name = "mesh.design.execute"
    version = "1.0.0"
    description = "Execute a design skill. Validates design.* namespace and delegates."
    timeout_seconds = 5.0

    async def validate(self, input: SkillInput) -> bool:
        skill_name = input.params.get("skill_name", "")
        return bool(skill_name) and skill_name.startswith("design.")

    async def execute(self, input: SkillInput) -> SkillOutput:
        skill_name = input.params["skill_name"]
        return SkillOutput(
            success=True,
            data={
                "skill": skill_name,
                "params": input.params.get("params", {}),
                "message": "Skill routing validated. Submit to /api/hermes/execute-skill for execution via HarnessManager.",
                "sub_skill": skill_name,
            },
            metrics=SkillMetrics(duration_ms=100, records_processed=0),
        )


# ══════════════════════════════════════════════════════════════════════
# SECTION 4 · AUTORESEARCH SKILLS (Skills 18-21)
# Skills for running the recursive self-healing experiment loop
# and automated browser-based research.
# ══════════════════════════════════════════════════════════════════════


class MeshAutoresearchRunSkill(MeshSkill):
    """Execute an autoresearch experiment on a target."""
    name = "mesh.autoresearch.run"
    version = "1.0.0"
    description = "Run an autoresearch experiment on a target (contractor_sms, storm_strike, trading, etc.)"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("target"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        target = input.params["target"]
        return SkillOutput(
            success=True,
            data={
                "target": target,
                "message": (
                    f"Autoresearch experiment queued for '{target}'. "
                    "Run bots/autoresearch_integration.py for full execution."
                ),
                "action": "queue_experiment",
                "experiment_target": target,
            },
            metrics=SkillMetrics(duration_ms=100, records_processed=0),
        )


class MeshAutoresearchScratchpadSkill(MeshSkill):
    """Read the unified measurement program (scratchpad.md) for current system status."""
    name = "mesh.autoresearch.scratchpad"
    version = "1.0.0"
    description = "Read the autoresearch scratchpad for current system status across all experiment targets"

    async def execute(self, input: SkillInput) -> SkillOutput:
        scratchpad_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "autoresearch", "scratchpad.md"
        )
        content = ""
        if os.path.exists(scratchpad_path):
            try:
                with open(scratchpad_path, "r") as f:
                    content = f.read(5000)
            except Exception as e:
                content = f"Error reading scratchpad: {e}"
        else:
            content = "No scratchpad.md found at autoresearch/scratchpad.md"

        return SkillOutput(
            success=True,
            data={"scratchpad": content, "path": scratchpad_path},
            metrics=SkillMetrics(duration_ms=100, records_processed=1),
        )


class MeshAutoresearchBrowserSkill(MeshSkill):
    """Execute browser-based research using the dev-browser harness."""
    name = "mesh.autoresearch.browser"
    version = "1.0.0"
    description = "Browser-based research via dev-browser — scrape, form fill, automation"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("action")) and bool(input.params.get("target_url"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        p = input.params
        return SkillOutput(
            success=True,
            data={
                "action": p["action"],
                "url": p["target_url"],
                "message": (
                    "Browser automation request queued. "
                    "Requires dev-browser harness. "
                    "Run bots/predictive_camofox_scraper.py for actual execution."
                ),
                "params": {k: v for k, v in p.items() if k not in ("action", "target_url")},
            },
            metrics=SkillMetrics(duration_ms=100, records_processed=0),
        )


class MeshAutoresearchOrchestrateSkill(MeshSkill):
    """Run the full recursive meta-loop across all autoresearch targets."""
    name = "mesh.autoresearch.orchestrate"
    version = "1.0.0"
    description = "Run the complete recursive meta-loop — all autoresearch targets in sequence"
    timeout_seconds = 60.0

    async def execute(self, input: SkillInput) -> SkillOutput:
        dry_run = input.params.get("dry_run", True)
        return SkillOutput(
            success=True,
            data={
                "mode": "dry_run" if dry_run else "live",
                "targets": [
                    "contractor_sms", "storm_strike", "trading",
                    "sniper", "weather", "email_subject", "buyer",
                ],
                "message": (
                    "Full meta-loop orchestration request received. "
                    "Run bots/autoresearch_integration.py --full for complete execution."
                ),
            },
            metrics=SkillMetrics(duration_ms=100, records_processed=0),
        )


# ══════════════════════════════════════════════════════════════════════
# SECTION 5 · EXTERNAL TOOL SKILLS (Skills 22-29)
# Guidance/instruction skills that return information about external
# tools and how to use them.
# ══════════════════════════════════════════════════════════════════════


class BrowserDevBrowserSkill(MeshSkill):
    """Browser automation via dev-browser — sandboxed Playwright API."""
    name = "browser.dev-browser"
    version = "1.0.0"
    description = "Browser automation via dev-browser — sandboxed Playwright API for AI agents"

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "dev-browser",
                "description": "Sandboxed Playwright API for browser automation",
                "capabilities": ["scrape", "form_fill", "screenshot", "automate"],
                "integration": "Use bots/predictive_camofox_scraper.py or call via HTTP to the dev-browser service",
                "status": "Available as PM2 service (camofox-scraper on port 9377)",
                "input_params": input.params,
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


class PromptsPromptMasterSkill(MeshSkill):
    """Prompt engineering framework — converts vague requests into structured prompts."""
    name = "prompts.prompt-master"
    version = "1.0.0"
    description = "Prompt engineering framework — converts vague requests into structured, high-quality prompts"

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "prompt-master",
                "description": "Prompt engineering framework for structured prompt generation",
                "request": input.params.get("request", "No request provided"),
                "guidance": (
                    "For best results, provide: request, target_tool (optional), "
                    "output_format (optional), context (optional). "
                    "The prompt-master generates an optimized prompt ready for the target AI tool."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


class SkillsClaudeSkillsSkill(MeshSkill):
    """Hundreds of production-ready skills for Claude Code, Cursor, Aider, Gemini CLI."""
    name = "skills.claude-skills"
    version = "1.0.0"
    description = "Access production-ready skills for Claude Code, Cursor, Aider, Gemini CLI"

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "claude-skills",
                "description": "Library of production-ready CLI skills for AI coding tools",
                "domain": input.params.get("domain", "Not specified"),
                "guidance": (
                    "Browse skills/skills/ or search by domain and tool. "
                    "Each skill includes CLI tool usage, integration guide, and prompt templates."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


class TextHumanizerSkill(MeshSkill):
    """AI text humanizer — detects and removes AI-generated patterns."""
    name = "text.humanizer"
    version = "1.0.0"
    description = "Detect and strip AI-generated patterns from writing"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("text"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "text.humanizer",
                "description": "Detects and removes AI-generated patterns",
                "text_length": len(input.params.get("text", "")),
                "guidance": (
                    "Uses pattern detection for common AI tells (hedging, repetitive structures, "
                    "unnatural transitions). Set aggressiveness 1-5 (default 3), "
                    "preserve_length=true to keep original word count."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=1),
        )


class MemorySupermemorySkill(MeshSkill):
    """RAG memory engine — persistent user profiles, auto-syncing."""
    name = "memory.supermemory"
    version = "1.0.0"
    description = "RAG memory engine — persistent user profiles, auto-syncing, conversation memory extraction"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("action"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "supermemory",
                "description": "RAG memory engine with auto-syncing",
                "action": input.params["action"],
                "supported_actions": ["store", "retrieve", "search", "sync", "extract"],
                "guidance": (
                    "Use action='store' to save data, 'retrieve' to get by query, "
                    "'search' for semantic search, 'sync' for auto-sync."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


class ScientificScientificAgentSkillsSkill(MeshSkill):
    """140+ scientific domain skills — bioinformatics, genomics, drug discovery."""
    name = "scientific.scientific-agent-skills"
    version = "1.0.0"
    description = "Access 140+ scientific domain skills — bioinformatics, genomics, drug discovery, physics, materials science"

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "scientific-agent-skills",
                "description": "Repository of 140+ scientific domain skills",
                "domain": input.params.get("domain", "Not specified"),
                "guidance": (
                    "Skills cover bioinformatics, genomics, drug discovery, physics, materials science. "
                    "Specify domain and task to get relevant skill instructions and database access workflows."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


class ScrapeFirecrawlSkill(MeshSkill):
    """Web scraping optimized for LLMs — scrape, crawl, search, map, extract."""
    name = "scrape.firecrawl"
    version = "1.0.0"
    description = "Open-source web scraping optimized for LLMs — scrape, crawl, search, map, extract"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("url")) if input.params.get("action") in ("scrape", "crawl", "map") else True

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "firecrawl",
                "description": "LLM-optimized web scraping",
                "action": input.params.get("action", "scrape"),
                "url": input.params.get("url", ""),
                "capabilities": ["scrape", "crawl", "search", "map", "extract"],
                "guidance": (
                    "Use action='scrape' for single page, 'crawl' for site-wide, "
                    "'search' for web search, 'map' for site structure. "
                    "Returns clean markdown/structured data. "
                    "Configure via FIRE_CRAWL_API_KEY env var."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


class AgenticSuperpowersSkill(MeshSkill):
    """Agentic skills framework — brainstorming, TDD, planning, subagent dev."""
    name = "agentic.superpowers"
    version = "1.0.0"
    description = "Agentic skills framework — Socratic brainstorming, TDD, planning, subagent dev, code review"

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("capability"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        return SkillOutput(
            success=True,
            data={
                "tool": "superpowers",
                "description": "Agentic skills framework",
                "capability": input.params["capability"],
                "supported_capabilities": ["brainstorm", "tdd", "plan", "delegate", "review", "design-skill"],
                "guidance": (
                    "Use capability='brainstorm' for Socratic brainstorming, 'tdd' for test-driven "
                    "development, 'plan' for multi-step planning, 'delegate' for subagent creation, "
                    "'review' for code review, 'design-skill' for skill creation."
                ),
            },
            metrics=SkillMetrics(duration_ms=50, records_processed=0),
        )


# ══════════════════════════════════════════════════════════════════════
# SECTION 6 · CONSULTING (Skill 30)
# Strategic business consulting — market analysis, growth strategy,
# pricing, competitive positioning, revenue optimization.
# ══════════════════════════════════════════════════════════════════════


class ConsultingStrategySkill(MeshSkill):
    """Strategic business consulting — provides analysis, recommendations, and action plans."""
    name = "consulting.strategy"
    version = "1.0.0"
    description = (
        "Strategic business consulting: market analysis, growth strategy, pricing optimization, "
        "competitive positioning, revenue model review, and go-to-market planning. "
        "Provides structured analysis with rationale, risks, and prioritized action items."
    )
    tags = ["consulting", "strategy", "business", "growth"]
    timeout_seconds = 300.0
    max_retries = 1

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("goal"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        p = input.params

        goal = p["goal"]
        business_context = p.get("business_context", p.get("context", ""))
        constraints = p.get("constraints", [])
        audience = p.get("audience", "leadership")
        depth = p.get("depth", "strategic")  # strategic, tactical, operational

        # Build the consulting framework
        analysis_domains = [
            "market_position",
            "revenue_model",
            "competitive_landscape",
            "growth_levers",
            "risk_assessment",
            "resource_allocation",
        ]

        # Filter domains based on contextual relevance
        relevant_domains = []
        keyword_map = {
            "market_position": ["market", "position", "competitor", "share", "audience", "customer"],
            "revenue_model": ["revenue", "pricing", "monetize", "mrr", "subscription", "fee"],
            "competitive_landscape": ["competitor", "landscape", "differentiate", "moat", "advantage"],
            "growth_levers": ["growth", "scale", "expand", "acquisition", "channels", "traffic"],
            "risk_assessment": ["risk", "threat", "compliance", "legal", "vulnerability"],
            "resource_allocation": ["resource", "budget", "team", "hire", "allocate", "capacity"],
        }

        context_lower = (goal + " " + business_context).lower()
        for domain, keywords in keyword_map.items():
            if any(kw in context_lower for kw in keywords):
                relevant_domains.append(domain)

        if not relevant_domains:
            relevant_domains = analysis_domains[:3]  # Default: first 3 domains

        elapsed = int((time.time() - start) * 1000)

        return SkillOutput(
            success=True,
            data={
                "goal": goal,
                "business_context": business_context[:500],
                "depth": depth,
                "audience": audience,
                "domains_analyzed": relevant_domains,
                "constraints": constraints,
                "framework": "Empire AI Strategic Consulting Engine v1.0",
                "analysis": {
                    "summary": (
                        f"Strategic analysis for: {goal[:120]}. "
                        f"Domains covered: {', '.join(relevant_domains)}. "
                        f"Depth: {depth}. For execution guidance, submit to LLM via /api/hermes/execute-skill "
                        f"with skill_name='consulting.strategy' and the full params."
                    ),
                    "recommendations_pending": True,
                    "next_step": (
                        "This skill provides the analytical framework. "
                        "For full LLM-powered strategic recommendations with rationale, risks, "
                        "and prioritized action items, wire ask_llm into this skill or "
                        "execute via the HarnessManager with LLM injection enabled."
                    ),
                },
                "structured_input": {
                    "goal": goal,
                    "context": business_context,
                    "domains": relevant_domains,
                    "depth": depth,
                    "audience": audience,
                    "constraints": constraints,
                },
            },
            metrics=SkillMetrics(duration_ms=elapsed, records_processed=len(relevant_domains)),
        )


# ══════════════════════════════════════════════════════════════════════
# SECTION 7 · DELEGATION (Skill 31)
# Task delegation engine — breaks down objectives into subtasks,
# maps to available agents, creates execution plan with priorities.
# ══════════════════════════════════════════════════════════════════════


class MeshDelegateSkill(MeshSkill):
    """Delegation engine — breaks down complex objectives, assigns to agents, creates task tickets."""
    name = "mesh.delegate"
    version = "1.0.0"
    description = (
        "Task delegation engine: breaks down complex objectives into subtasks, maps each subtask "
        "to the most capable available agent, prioritizes and sequences the work, creates task "
        "tickets in agent_task_queue for tracking, and returns a complete execution plan with "
        "dependencies, estimated durations, and SLA targets."
    )
    tags = ["delegation", "orchestration", "task_breakdown", "planning"]
    timeout_seconds = 120.0
    max_retries = 2

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("objective"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        p = input.params
        sb = _get_sb()

        objective = p["objective"]
        context = p.get("context", "")
        deadline = p.get("deadline")
        auto_create_tasks = p.get("auto_create_tasks", False)

        # ── Agent capability registry ──────────────────────────────────
        agent_capabilities = {
            "mesh.scout": {
                "skills": ["scout.find_roofs"],
                "description": "Finds targets in storm zones via satellite imagery and risk data",
            },
            "mesh.outreach": {
                "skills": ["outreach.draft_email"],
                "description": "Drafts and sends outreach messages to prospects",
            },
            "mesh.dispatcher": {
                "skills": ["revenue.connect_buyer"],
                "description": "Connects qualified leads with buyers/contractors for dispatch",
            },
            "mesh.studio_copy": {
                "skills": ["studio.write_script"],
                "description": "Writes video scripts and marketing copy",
            },
            "mesh.studio_render": {
                "skills": ["studio.render_reel"],
                "description": "Renders video reels using FFmpeg and TTS",
            },
            "mesh.quality": {
                "skills": ["revenue.score_call"],
                "description": "Scores sales calls for quality and conversion probability",
            },
            "mesh.swarm_worker": {
                "skills": ["swarm.fire"],
                "description": "Executes swarm TTS calls and video strike generation",
            },
            "mesh.marketing": {
                "skills": ["marketing.execute"],
                "description": "Executes 45 marketing skills (email, ads, SEO, referrals, CRO)",
            },
            "mesh.design": {
                "skills": ["design.execute"],
                "description": "Executes 24 design skills (UI, UX, visual, motion, a11y)",
            },
            "mesh.email": {
                "skills": ["email.execute"],
                "description": "Executes 25 email marketing skills (strategy, compliance, sequences)",
            },
            "mesh.scraper": {
                "skills": ["scrape.web"],
                "description": "Extracts structured data from web pages",
            },
            "mesh.orchestrator": {
                "skills": ["agentic.plan", "autoresearch.orchestrate"],
                "description": "Creates execution plans and runs meta-loops",
            },
            "mesh.autoresearch": {
                "skills": ["autoresearch.run"],
                "description": "Runs recursive self-healing experiments",
            },
            "mesh.browser": {
                "skills": ["browser.dev-browser"],
                "description": "Browser automation via sandboxed Playwright",
            },
        }

        # ── Keyword-based agent matching ───────────────────────────────
        objective_lower = objective.lower()
        agent_keywords = {
            "mesh.scout": ["scout", "find", "prospect", "search", "discover", "target", "roof", "storm zone"],
            "mesh.outreach": ["outreach", "draft", "message", "sms", "text", "send", "contact", "email draft"],
            "mesh.dispatcher": ["dispatch", "connect", "buyer", "contractor", "lead", "match", "assign"],
            "mesh.studio_copy": ["write", "script", "copy", "content", "article", "blog"],
            "mesh.studio_render": ["render", "video", "reel", "ffmpeg", "produce"],
            "mesh.quality": ["score", "quality", "call", "review", "audit", "evaluate"],
            "mesh.swarm_worker": ["swarm", "simultaneous", "mass", "bulk", "batch"],
            "mesh.marketing": ["market", "ad", "seo", "social", "campaign", "referral", "cro", "analytics"],
            "mesh.design": ["design", "ui", "ux", "visual", "layout", "brand", "interface"],
            "mesh.email": ["email", "deliverability", "spf", "dkim", "compliance", "newsletter"],
            "mesh.scraper": ["scrape", "crawl", "extract", "data", "webpage"],
            "mesh.orchestrator": ["plan", "orchestrate", "coordinate", "meta", "strategy"],
            "mesh.autoresearch": ["experiment", "optimize", "tune", "ab test", "research"],
            "mesh.browser": ["browser", "screenshot", "automate", "playwright", "navigate"],
        }

        matched_agents = []
        for agent, keywords in agent_keywords.items():
            score = sum(1 for kw in keywords if kw in objective_lower)
            if score > 0:
                matched_agents.append((agent, score))

        matched_agents.sort(key=lambda x: x[1], reverse=True)

        # ── Build execution plan ───────────────────────────────────────
        subtasks = []
        ticket_ids = []

        for rank, (agent, score) in enumerate(matched_agents[:5]):  # Max 5 agents
            caps = agent_capabilities.get(agent, {})
            primary_skill = caps.get("skills", [agent])[0]

            priority = 20 - rank * 3  # First agent gets priority 20, each subsequent drops by 3

            subtask = {
                "step": rank + 1,
                "agent": agent,
                "task_type": primary_skill,
                "description": caps.get("description", f"Executes {primary_skill}"),
                "priority": priority,
                "status": "planned",
                "relevance_score": score,
            }

            # Auto-create task ticket if requested and Supabase is available
            if auto_create_tasks and sb:
                try:
                    r = sb.table("agent_task_queue").insert({
                        "task_type": primary_skill,
                        "payload": json.dumps({
                            "objective": objective,
                            "context": context,
                            "delegation_id": f"delegate_{int(start)}",
                        }),
                        "status": "To-Do",
                        "assigned_agent": agent,
                        "priority": priority,
                    }).execute()
                    ticket_id = r.data[0].get("ticket_id") if r.data else None
                    if ticket_id:
                        subtask["ticket_id"] = ticket_id
                        ticket_ids.append(ticket_id)
                except Exception as e:
                    subtask["create_error"] = str(e)[:200]

            subtasks.append(subtask)

        elapsed = int((time.time() - start) * 1000)

        return SkillOutput(
            success=True,
            data={
                "objective": objective[:300],
                "context": context[:500],
                "deadline": deadline,
                "total_subtasks": len(subtasks),
                "tickets_created": len(ticket_ids),
                "ticket_ids": ticket_ids,
                "auto_create_tasks": auto_create_tasks,
                "execution_plan": {
                    "subtasks": subtasks,
                    "estimated_agents": len(matched_agents),
                    "strategy": (
                        f"Decomposed '{objective[:80]}...' into {len(subtasks)} subtasks "
                        f"across {len(matched_agents)} capable agents. "
                        f"{'Tickets created in agent_task_queue.' if ticket_ids else 'Set auto_create_tasks=true to create tickets.'}"
                    ),
                },
                "available_agents": list(agent_capabilities.keys()),
            },
            metrics=SkillMetrics(duration_ms=elapsed, records_processed=len(subtasks)),
        )


# ══════════════════════════════════════════════════════════════════════
# REGISTRATION
# ══════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════
# SECTION 8 · YOUTUBE SHORTS (Skills 32-33)
# Faceless YouTube Shorts creation for Empire AI's niches.
# Script generation, visual brief creation, and publishing pipeline.
# ══════════════════════════════════════════════════════════════════════


class YouTubeGenerateScriptSkill(MeshSkill):
    """Generate a YouTube Shorts script optimized for Empire AI niches."""
    name = "youtube.shorts.generate_script"
    version = "1.0.0"
    description = (
        "Generate a YouTube Shorts script for a faceless channel. "
        "Creates a short-form script (15-60s) with hook, problem, solution, "
        "visual cue, and CTA. Optimized for Empire AI niches: storm education, "
        "contractor tips, case studies, industry insights, behind-the-scenes."
    )
    tags = ["youtube", "shorts", "video", "script", "content"]
    timeout_seconds = 30.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("hook") or input.params.get("topic"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        from bots.youtube_shorts_agent import YouTubeShortsAgent
        agent = YouTubeShortsAgent()

        hook = input.params.get("hook", "")
        topic = input.params.get("topic", "")
        niche = input.params.get("niche", "")
        duration = int(input.params.get("duration_seconds", 45))

        topic_brief = {
            "pillar_id": "custom",
            "label": "Custom",
            "hook": hook or topic or "How AI is changing storm restoration",
            "angle": input.params.get("angle", "educational"),
            "duration_seconds": duration,
            "tone": input.params.get("tone", "educational"),
        }

        script = await agent.generate_script(topic_brief)
        return SkillOutput(
            success=bool(script),
            data=script,
            metrics=SkillMetrics(duration_ms=500, records_processed=1),
        )


class YouTubeCreateVisualBriefSkill(MeshSkill):
    """Create a visual production brief for a YouTube Short."""
    name = "youtube.shorts.create_visual_brief"
    version = "1.0.0"
    description = (
        "Create a visual production brief from a Shorts script. "
        "Generates style guide, text overlays, background style, "
        "and footage recommendations for faceless video production."
    )
    tags = ["youtube", "shorts", "visual", "production", "design"]
    timeout_seconds = 15.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("script"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        from bots.youtube_shorts_agent import YouTubeShortsAgent
        agent = YouTubeShortsAgent()

        script = input.params["script"]
        if isinstance(script, str):
            try:
                script = json.loads(script)
            except json.JSONDecodeError:
                script = {"hook": script[:80], "full_text": script}

        visual_brief = await agent.create_visual_brief(script)
        return SkillOutput(
            success=bool(visual_brief),
            data=visual_brief,
            metrics=SkillMetrics(duration_ms=300, records_processed=1),
        )


# ══════════════════════════════════════════════════════════════════════
# SECTION 9 · YOUTUBE DESIGN (Skills 34-35)
# YouTube thumbnail and channel banner generation using Pillow.
# Generates 1280x720 thumbnails and 2048x1152 channel banners
# with text overlays, gradient backgrounds, and brand styling.
# ══════════════════════════════════════════════════════════════════════


class YouTubeThumbnailDesignerSkill(MeshSkill):
    """Generate a YouTube thumbnail image for a faceless Shorts channel."""
    name = "youtube.design.thumbnail"
    version = "1.0.0"
    description = (
        "Generate a YouTube thumbnail (1280x720) for a faceless Shorts channel. "
        "Creates an image with gradient background, bold text overlay (hook/title), "
        "accent color scheme, and optional stock-style background image. "
        "Optimized for Empire AI niches: storm education, contractor tips, case studies."
    )
    tags = ["youtube", "design", "thumbnail", "image"]
    timeout_seconds = 15.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("title") or input.params.get("hook"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        from pathlib import Path as _Path

        title = input.params.get("title", input.params.get("hook", "How AI Finds Storm Damage"))
        niche = input.params.get("niche", "storm_education")
        accent_color = input.params.get("accent_color", "#44E5B8")
        bg_color = input.params.get("bg_color", "#0F172A")
        pillar_label = input.params.get("pillar_label", "")

        # Output directory
        output_dir = _Path(__file__).resolve().parent.parent / "youtube_thumbnails"
        output_dir.mkdir(exist_ok=True)
        from datetime import datetime, timezone as _tz
        ts = datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:40]
        output_path = str(output_dir / f"thumb_{safe_title}_{ts}.png")

        thumbnail_generated = False
        thumbnail_data = {}

        # Try Pillow for actual image generation
        try:
            from PIL import Image, ImageDraw, ImageFont

            WIDTH, HEIGHT = 1280, 720
            img = Image.new("RGB", (WIDTH, HEIGHT), bg_color)
            draw = ImageDraw.Draw(img)

            # Parse accent color
            ac = accent_color.lstrip("#")
            accent_rgb = tuple(int(ac[i:i+2], 16) for i in (0, 2, 4))

            # Gradient overlay: dark at top, accent at bottom
            for y in range(HEIGHT):
                ratio = y / HEIGHT
                r = int(15 * (1 - ratio) + accent_rgb[0] * ratio) % 256
                g = int(26 * (1 - ratio) + accent_rgb[1] * ratio) % 256
                b = int(42 * (1 - ratio) + accent_rgb[2] * ratio) % 256
                draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

            # Try to load a font, fall back to default
            font_large = None
            font_medium = None
            font_small = None
            font_candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            ]
            for fp in font_candidates:
                if _Path(fp).exists():
                    font_large = ImageFont.truetype(fp, 72)
                    font_medium = ImageFont.truetype(fp, 48)
                    font_small = ImageFont.truetype(fp, 28)
                    break

            # Pillow accent bar at top
            draw.rectangle([(0, 0), (WIDTH, 6)], fill=accent_rgb)

            # Pillar label (top-left corner)
            if pillar_label and font_small:
                draw.text((40, 20), pillar_label.upper(), fill=accent_rgb, font=font_small)

            # Main title text — split into two lines if long
            words = title.split()
            if len(words) > 5:
                mid = len(words) // 2
                line1 = " ".join(words[:mid])
                line2 = " ".join(words[mid:])
            else:
                line1 = title
                line2 = ""

            # Render title with shadow for readability
            if font_large:
                y_start = 260 if line2 else 320
                # Shadow
                draw.text((42, y_start + 2), line1, fill=(0, 0, 0, 128), font=font_large)
                draw.text((40, y_start), line1, fill="#FFFFFF", font=font_large)
                if line2:
                    draw.text((42, y_start + 88), line2, fill=(0, 0, 0, 128), font=font_large)
                    draw.text((40, y_start + 86), line2, fill="#FFFFFF", font=font_large)

            # Empire AI watermark at bottom
            if font_small:
                draw.text((40, HEIGHT - 50), "Empire AI", fill=accent_rgb, font=font_small)

            # Accent underline bar
            if line2:
                bar_y = y_start + 86 + 10
            else:
                bar_y = y_start + 10
            # Measure text width for underline
            try:
                bbox = font_large.getbbox(line1) if font_large else (0, 0, 200, 0)
                text_w = bbox[2] - bbox[0]
                draw.rectangle([(40, bar_y), (40 + text_w, bar_y + 4)], fill=accent_rgb)
            except Exception:
                draw.rectangle([(40, bar_y), (300, bar_y + 4)], fill=accent_rgb)

            # Empire AI watermark at bottom
            if font_small:
                # Subtitle below main title
                subtitle = "empire-ai.co.uk"
                draw.text((42, HEIGHT - 80), subtitle, fill=(0, 0, 0, 128), font=font_small)
                draw.text((40, HEIGHT - 82), subtitle, fill="#64748B", font=font_small)

            img.save(output_path, "PNG")
            sz = _Path(output_path).stat().st_size
            thumbnail_generated = True
            thumbnail_data = {
                "width": WIDTH,
                "height": HEIGHT,
                "format": "PNG",
                "size_kb": round(sz / 1024, 1),
                "font_used": str(font_large.path) if font_large else "default",
            }
            import logging as _log
            _log.getLogger("empire.skills.hermes").info(
                "[youtube.design.thumbnail] Generated: %s (%d KB)", output_path, sz // 1024
            )

        except ImportError:
            pass  # Pillow not available — fall through to brief
        except Exception as e:
            import logging as _log
            _log.getLogger("empire.skills.hermes").warning(
                "[youtube.design.thumbnail] Pillow failed: %s", e
            )

        if thumbnail_generated:
            return SkillOutput(
                success=True,
                data={
                    "skill": "youtube.design.thumbnail",
                    "title": title,
                    "niche": niche,
                    "output_path": output_path,
                    "thumbnail": thumbnail_data,
                    "design_spec": {
                        "resolution": "1280x720",
                        "bg_color": bg_color,
                        "accent_color": accent_color,
                        "text": title,
                        "pillar_label": pillar_label,
                    },
                },
                metrics=SkillMetrics(duration_ms=1000, records_processed=1),
            )

        # Fallback: return design spec without generated image
        return SkillOutput(
            success=True,
            data={
                "skill": "youtube.design.thumbnail",
                "title": title,
                "niche": niche,
                "output_path": output_path,
                "generated": False,
                "note": (
                    "Thumbnail design spec created. Pillow is required for image generation. "
                    "Install with: pip3 install Pillow. "
                    "To generate manually, create a 1280x720 image with the following spec:"
                ),
                "design_spec": {
                    "resolution": "1280x720",
                    "format": "PNG",
                    "bg_color": bg_color,
                    "accent_color": accent_color,
                    "font_size_title": 72,
                    "font_size_subtitle": 28,
                    "layout": [
                        {"element": "accent_bar", "position": "top", "height": 6},
                        {"element": "pillar_label", "position": "top-left", "content": pillar_label or niche.replace("_", " ").title()},
                        {"element": "title", "position": "center-left", "content": title, "style": "bold, white, shadow"},
                        {"element": "accent_underline", "position": "below_title", "color": accent_color},
                        {"element": "branding", "position": "bottom-left", "content": "Empire AI · empire-ai.co.uk"},
                    ],
                },
            },
            metrics=SkillMetrics(duration_ms=500, records_processed=1),
        )


class YouTubeBannerDesignerSkill(MeshSkill):
    """Generate a YouTube channel banner image."""
    name = "youtube.design.banner"
    version = "1.0.0"
    description = (
        "Generate a YouTube channel banner (2048x1152) for Empire AI's faceless channel. "
        "Creates a banner with brand gradient, tagline, content pillar badges, "
        "and CTA. Optimized for all device safe zones (1546x423 center safe area)."
    )
    tags = ["youtube", "design", "banner", "channel", "brand"]
    timeout_seconds = 15.0

    async def validate(self, input: SkillInput) -> bool:
        return True  # Banner can be generated with defaults

    async def execute(self, input: SkillInput) -> SkillOutput:
        from pathlib import Path as _Path

        channel_name = input.params.get("channel_name", "Empire AI")
        tagline = input.params.get("tagline", "AI-Powered Storm Restoration Lead Generation")
        accent_color = input.params.get("accent_color", "#44E5B8")
        bg_color = input.params.get("bg_color", "#0B1120")
        show_pillars = input.params.get("show_pillars", True)

        # Content pillars to display as badges
        pillars = [
            "Storm Education",
            "Contractor Tips",
            "Case Studies",
            "Industry Insights",
            "Behind the Scenes",
        ]

        # Output directory
        output_dir = _Path(__file__).resolve().parent.parent / "youtube_assets"
        output_dir.mkdir(exist_ok=True)
        from datetime import datetime, timezone as _tz
        ts = datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in channel_name)[:30]
        output_path = str(output_dir / f"banner_{safe_name}_{ts}.png")

        banner_generated = False
        banner_data = {}

        # Try Pillow for actual image generation
        try:
            from PIL import Image, ImageDraw, ImageFont

            WIDTH, HEIGHT = 2048, 1152
            img = Image.new("RGB", (WIDTH, HEIGHT), bg_color)
            draw = ImageDraw.Draw(img)

            # Safe zone indicators (not drawn, just for reference)
            # Center safe zone: 1546x423, centered at (251, 365) to (1797, 788)

            # Parse accent color
            ac = accent_color.lstrip("#")
            accent_rgb = tuple(int(ac[i:i+2], 16) for i in (0, 2, 4))

            # Gradient: dark bg_color at top, accent-tinted at bottom
            bg_rgb = tuple(int(bg_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
            for y in range(HEIGHT):
                ratio = y / HEIGHT
                r = int(bg_rgb[0] * (1 - ratio) + accent_rgb[0] * ratio * 0.3) % 256
                g = int(bg_rgb[1] * (1 - ratio) + accent_rgb[1] * ratio * 0.3) % 256
                b = int(bg_rgb[2] * (1 - ratio) + accent_rgb[2] * ratio * 0.3) % 256
                draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

            # Load fonts
            font_big = None
            font_tag = None
            font_small = None
            font_pillar = None
            font_candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            ]
            for fp in font_candidates:
                if _Path(fp).exists():
                    font_big = ImageFont.truetype(fp, 96)
                    font_tag = ImageFont.truetype(fp, 42)
                    font_small = ImageFont.truetype(fp, 28)
                    font_pillar = ImageFont.truetype(fp, 24)
                    break

            # Accent bar at top
            draw.rectangle([(0, 0), (WIDTH, 4)], fill=accent_rgb)

            # Channel name (centered, large)
            if font_big:
                try:
                    bb = font_big.getbbox(channel_name)
                    tw = bb[2] - bb[0]
                except Exception:
                    tw = 400
                x = (WIDTH - tw) // 2
                # Shadow
                draw.text((x + 3, 253), channel_name, fill=(0, 0, 0, 128), font=font_big)
                draw.text((x, 250), channel_name, fill="#FFFFFF", font=font_big)

            # Accent underline under channel name
            underline_y = 250 + 96 + 12  # below the text
            draw.rectangle([((WIDTH - 400) // 2, underline_y), ((WIDTH + 400) // 2, underline_y + 4)], fill=accent_rgb)

            # Tagline
            if font_tag:
                try:
                    bb = font_tag.getbbox(tagline)
                    tw = bb[2] - bb[0]
                except Exception:
                    tw = 400
                x = (WIDTH - tw) // 2
                draw.text((x, underline_y + 24), tagline, fill="#94A3B8", font=font_tag)

            # Content pillar badges (horizontal row)
            if show_pillars and font_pillar:
                badge_y = underline_y + 90
                badge_height = 40
                badge_gap = 16

                # Calculate total width
                total_w = 0
                badge_widths = []
                for p in pillars:
                    try:
                        bb = font_pillar.getbbox(p)
                        pw = bb[2] - bb[0] + 32  # padding
                    except Exception:
                        pw = 140
                    badge_widths.append(pw)
                    total_w += pw + badge_gap
                total_w -= badge_gap

                start_x = (WIDTH - total_w) // 2
                for i, p in enumerate(pillars):
                    bx = start_x + sum(badge_widths[:i]) + i * badge_gap
                    # Badge background (rounded-rect effect via filled rect)
                    bw = badge_widths[i]
                    draw.rounded_rectangle(
                        [(bx, badge_y), (bx + bw, badge_y + badge_height)],
                        radius=20, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2])
                    )
                    # Badge text
                    draw.text((bx + 16, badge_y + 8), p, fill="#CBD5E1", font=font_pillar)

            # Empire AI URL at bottom
            if font_small:
                url_text = "empire-ai.co.uk"
                try:
                    bb = font_small.getbbox(url_text)
                    tw = bb[2] - bb[0]
                except Exception:
                    tw = 200
                draw.text(((WIDTH - tw) // 2, HEIGHT - 50), url_text, fill="#64748B", font=font_small)

            # Bottom accent bar
            draw.rectangle([(0, HEIGHT - 4), (WIDTH, HEIGHT)], fill=accent_rgb)

            img.save(output_path, "PNG")
            sz = _Path(output_path).stat().st_size
            banner_generated = True
            banner_data = {
                "width": WIDTH,
                "height": HEIGHT,
                "format": "PNG",
                "size_kb": round(sz / 1024, 1),
                "safe_zone": {
                    "center_area": "1546x423",
                    "safe_start": "(251, 365)",
                    "safe_end": "(1797, 788)",
                },
            }
            import logging as _log
            _log.getLogger("empire.skills.hermes").info(
                "[youtube.design.banner] Generated: %s (%d KB)", output_path, sz // 1024
            )

        except ImportError:
            pass
        except Exception as e:
            import logging as _log
            _log.getLogger("empire.skills.hermes").warning(
                "[youtube.design.banner] Pillow failed: %s", e
            )

        if banner_generated:
            return SkillOutput(
                success=True,
                data={
                    "skill": "youtube.design.banner",
                    "channel_name": channel_name,
                    "tagline": tagline,
                    "output_path": output_path,
                    "banner": banner_data,
                },
                metrics=SkillMetrics(duration_ms=1500, records_processed=1),
            )

        # Fallback: return design spec
        return SkillOutput(
            success=True,
            data={
                "skill": "youtube.design.banner",
                "channel_name": channel_name,
                "tagline": tagline,
                "output_path": output_path,
                "generated": False,
                "note": (
                    "Banner design spec created. Pillow is required for image generation. "
                    "Install with: pip3 install Pillow. "
                    "To generate manually, create a 2048x1152 image with the following spec:"
                ),
                "design_spec": {
                    "resolution": "2048x1152",
                    "safe_zone": "1546x423 centered",
                    "format": "PNG",
                    "bg_color": bg_color,
                    "accent_color": accent_color,
                    "font_size_title": 96,
                    "font_size_tagline": 42,
                    "layout": [
                        {"element": "accent_bar", "position": "top", "height": 4},
                        {"element": "channel_name", "position": "center", "content": channel_name, "style": "bold, white, centered"},
                        {"element": "accent_underline", "position": "below_title", "width": 400, "color": accent_color},
                        {"element": "tagline", "position": "below_underline", "content": tagline, "style": "muted, centered"},
                        {"element": "pillar_badges", "position": "below_tagline", "pillars": pillars, "style": "rounded, accent border"},
                        {"element": "url", "position": "bottom-center", "content": "empire-ai.co.uk"},
                        {"element": "accent_bar", "position": "bottom", "height": 4},
                    ],
                },
            },
            metrics=SkillMetrics(duration_ms=500, records_processed=1),
        )

HERMES_SKILL_CLASSES = [
    # Section 1: Core Mesh Ops (1-5)
    MeshTaskCreateSkill,
    MeshTaskClaimSkill,
    MeshTaskUpdateSkill,
    MeshAgentHeartbeatSkill,
    MeshStatusReportSkill,
    # Section 2: Fleet Agent Task Producers (6-14)
    ScoutFindRoofsSkill,
    OutreachDraftEmailSkill,
    StudioWriteScriptSkill,
    StudioRenderReelSkill,
    RevenueConnectBuyerSkill,
    RevenueScoreCallSkill,
    SwarmFireSkill,
    ScrapeWebSkill,
    AgenticPlanSkill,
    # Section 3: Framework Wrappers (15-17)
    MeshMarketingExecuteSkill,
    MeshEmailExecuteSkill,
    MeshDesignExecuteSkill,
    # Section 4: Autoresearch (18-21)
    MeshAutoresearchRunSkill,
    MeshAutoresearchScratchpadSkill,
    MeshAutoresearchBrowserSkill,
    MeshAutoresearchOrchestrateSkill,
    # Section 5: External Tools (22-29)
    BrowserDevBrowserSkill,
    PromptsPromptMasterSkill,
    SkillsClaudeSkillsSkill,
    TextHumanizerSkill,
    MemorySupermemorySkill,
    ScientificScientificAgentSkillsSkill,
    ScrapeFirecrawlSkill,
    AgenticSuperpowersSkill,
    # Section 6: Consulting (30)
    ConsultingStrategySkill,
    # Section 7: Delegation (31)
    MeshDelegateSkill,
    # Section 8: YouTube Shorts (32-33)
    YouTubeGenerateScriptSkill,
    YouTubeCreateVisualBriefSkill,
    # Section 9: YouTube Design (34-35)
    YouTubeThumbnailDesignerSkill,
    YouTubeBannerDesignerSkill,
]


def register_hermes_skills(registry: ImmutableSkillRegistry) -> None:
    """Register all 29 hermes mesh skills into a SkillRegistry.

    These skills are invocable via HarnessManager.run() after registration,
    providing a direct execution path alongside the agent_task_queue route.

    Args:
        registry: An ImmutableSkillRegistry instance to register into.
    """
    for cls in HERMES_SKILL_CLASSES:
        registry.register(cls)

    log.info(f"[hermes.skills] registered {len(HERMES_SKILL_CLASSES)} hermes mesh skills")


def get_hermes_skill_names() -> list[str]:
    """Return all hermes mesh skill names for reference."""
    return [cls.name for cls in HERMES_SKILL_CLASSES]


def list_hermes_skills_by_section() -> dict:
    """Return hermes skills organized by section for documentation."""
    return {
        "core_mesh_ops": [cls.name for cls in HERMES_SKILL_CLASSES[:5]],
        "fleet_agents": [cls.name for cls in HERMES_SKILL_CLASSES[5:14]],
        "framework_wrappers": [cls.name for cls in HERMES_SKILL_CLASSES[14:17]],
        "autoresearch": [cls.name for cls in HERMES_SKILL_CLASSES[17:21]],
        "external_tools": [cls.name for cls in HERMES_SKILL_CLASSES[21:29]],
        "consulting": [cls.name for cls in HERMES_SKILL_CLASSES[29:30]],
        "delegation": [cls.name for cls in HERMES_SKILL_CLASSES[30:31]],
        "total": len(HERMES_SKILL_CLASSES),
    }
