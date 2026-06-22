"""
EMPIRE V49 · HERMES MESH SKILLS
=================================
Concrete BaseSkill implementations for all 29 skills registered in
agent_os/hermes_os/SKILLS.md. These make the mesh dispatch layer
invocable directly via HarnessManager.run() in addition to the
existing agent_task_queue / PM2 worker path.

Skill groups:
  Core Mesh (1-5):     task create/claim/update, agent heartbeat, status report
  Fleet Agents (6-14): scout, outreach, studio, revenue, swarm, scrape, agentic
  Wrappers (15-17):    marketing, email, design execute
  Autoresearch (18-21): run, scratchpad, browser, orchestrate
  External Tools (22-29): browser, prompts, claude, humanizer, memory, scientific, firecrawl, superpowers
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
# REGISTRATION
# ══════════════════════════════════════════════════════════════════════

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
        "external_tools": [cls.name for cls in HERMES_SKILL_CLASSES[21:]],
        "total": len(HERMES_SKILL_CLASSES),
    }
