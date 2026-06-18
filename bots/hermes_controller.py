"""
EMPIRE V49 · HERMES CONTROLLER (GOD MODE)
==========================================
Autonomous agent mesh controller. Monitors the agent_task_queue for
completed/failed tasks and makes GodMode-level orchestration decisions:

  - Retry failed tasks with corrected parameters (LLM self-correction)
  - Promote completed tasks to the next pipeline stage
  - Auto-scale agent lanes based on queue depth
  - Detect and remediate stalled agents

Pipeline (Hermes Protocol):
  Scout → Outreach → [Studio: Copywriter → Render] → Dispatcher → Quality

GodMode loop: Every decision goes through LLM → Execute → QC → Self-Correct
before being committed. Max 3 correction attempts per decision.

Wire-up: Runs standalone via `python bots/hermes_controller.py` or
          imported by main.py's agent loop. Uses AgentMesh for task
          CRUD and AIRouter for LLM reasoning.
"""

import os
import sys
import json
import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, TYPE_CHECKING

# Space reasoner — multi-provider deep reasoning for GodMode decisions
try:
    from bots.space_providers import SpaceReasoner
    _HAS_SPACE = True
except ImportError:
    _HAS_SPACE = False
    SpaceReasoner = None

# Chatwoot — omnichannel messaging
_HAS_CHATWOOT = False
try:
    from bots.chatwoot_client import get_chatwoot as _get_chatwoot
    _HAS_CHATWOOT = True
except ImportError:
    _get_chatwoot = None

# Langfuse tracing
_HAS_TRACING = False
try:
    from observability.tracing import TraceContext
    _HAS_TRACING = True
except ImportError:
    TraceContext = None

if TYPE_CHECKING:
    # Forward reference for the Supabase client type. We use TYPE_CHECKING
    # so mypy/IDEs see the proper type for the `sb` parameter without
    # paying any runtime import cost.
    from supabase import Client as SupabaseClient  # noqa: F401

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("hermes.controller")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434")
INTERVAL     = int(os.environ.get("HERMES_CTL_INTERVAL_SEC", "60"))
MAX_LOOKBACK = int(os.environ.get("HERMES_CTL_LOOKBACK_MIN", "10"))
AGENT_NAME = "hermes_controller"
AGENT_STATUS = "ACTIVE"

# Space reasoning — enabled by default, opt-out via env
SPACE_REASONING_ENABLED = os.environ.get("HERMES_SPACE_REASONING", "true").lower() == "true"

# Chatwoot — omnichannel messaging enabled via env
CHATWOOT_ENABLED = os.environ.get("CHATWOOT_ENABLED", "false").lower() == "true"

# Langfuse tracing for Hermes decisions
HERMES_TRACING_ENABLED = os.environ.get("HERMES_TRACING_ENABLED", "true").lower() == "true"

# Pipeline stage progression
PIPELINE_NEXT: Dict[str, Optional[str]] = {
    "scout.find_roofs":        "outreach.draft_email",
    "outreach.draft_email":    "studio.write_script",
    "studio.write_script":     "studio.render_reel",
    "studio.render_reel":      "revenue.connect_buyer",
    "revenue.connect_buyer":   "revenue.score_call",
    "revenue.score_call":      None,   # terminal
}

# Agent assignment per stage
STAGE_AGENT: Dict[str, str] = {
    "scout.find_roofs":        "mesh.scout",
    "outreach.draft_email":    "mesh.outreach",
    "studio.write_script":     "mesh.copywriter",
    "studio.render_reel":      "mesh.render",
    "revenue.connect_buyer":   "mesh.dispatcher",
    "revenue.score_call":      "mesh.quality",
}

if os.environ.get("EMPIRE_TESTING") != "1":
    # In production, require Supabase creds at module load.
    # In test mode, defer the connection to first use (or accept an injected
    # client) so the module can be imported without external creds.
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        sys.exit(1)
    _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    _sb = None  # type: ignore[assignment]  # lazy in test mode


# ── GOD MODE ORCHESTRATION ENGINE ────────────────────────────────────
class GodModeController:
    """
    Autonomous agent mesh controller with GodMode self-correction.
    Each orchestration decision goes through:
      1. LLM analyzes completed tasks → proposes action
      2. Execute the action (retry, promote, escalate, scale)
      3. QC: verify the action's effect
      4. If QC fails, self-correct via LLM and retry (up to 3x)
    """

    def __init__(
        self,
        max_loops: int = 3,
        sb: Optional["SupabaseClient"] = None,
    ):
        """
        Args:
            max_loops: max LLM re-query attempts per cycle.
            sb: optional Supabase client. When provided, the controller
                uses it directly for all DB operations. When None, falls
                back to the module-level `_sb` client (back-compat for
                callers that don't pass the kwarg). In EMPIRE_TESTING=1
                mode, the module-level client is None and the controller
                must be constructed with an injected `sb` or will skip
                DB operations.
        """
        self.max_loops = max_loops
        self.sb = sb
        self.stats = {"runs": 0, "actions_taken": 0, "retries": 0, "escalations": 0, "promotions": 0}

    # ── 1. FETCH RECENTLY COMPLETED TASKS ────────────────────────────
    def fetch_recent_tasks(self) -> Dict[str, List[Dict]]:
        """Pull Done and Failed tasks from the last N minutes."""
        if self.sb is None:
            return {"done": [], "failed": [], "all": []}
        since = (datetime.now(timezone.utc) - timedelta(minutes=MAX_LOOKBACK)).isoformat()
        try:
            r = self.sb.table("agent_task_queue").select("*") \
                .in_("status", ["Done", "Failed"]) \
                .gte("completed_at", since) \
                .order("completed_at", desc=True) \
                .limit(50).execute()
            tasks = r.data or []
            return {
                "done": [t for t in tasks if t.get("status") == "Done"],
                "failed": [t for t in tasks if t.get("status") == "Failed"],
                "all": tasks,
            }
        except Exception as e:
            log.error(f"[controller] fetch error: {e}")
            return {"done": [], "failed": [], "all": []}

    # ── 2. ANALYZE QUEUE STATE ───────────────────────────────────────
    def fetch_queue_state(self) -> Dict[str, Any]:
        """Get aggregate queue stats for the LLM to reason about."""
        if self.sb is None:
            return {"error": "no Supabase client (EMPIRE_TESTING=1 mode)"}
        try:
            r = self.sb.table("agent_task_queue").select("status,task_type,assigned_agent").execute()
            tasks = r.data or []
            by_status: Dict[str, int] = {}
            by_type: Dict[str, int] = {}
            stalled = 0
            for t in tasks:
                s = t.get("status", "unknown")
                by_status[s] = by_status.get(s, 0) + 1
                tt = t.get("task_type", "unknown")
                by_type[tt] = by_type.get(tt, 0) + 1
                if s == "In Progress":
                    stalled += 1
            return {
                "total": len(tasks),
                "by_status": by_status,
                "by_type": by_type,
                "pending": by_status.get("To-Do", 0),
                "stalled": stalled,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── 3. LLM: DECIDE WHAT TO DO ────────────────────────────────────
    async def decide_action(
        self,
        recent: Dict[str, List[Dict]],
        queue: Dict[str, Any],
        *,
        last_failure: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Feed completed tasks + queue state to the LLM.
        Returns a structured action: {action, target_ticket, params, reasoning}.

        Uses Space Reasoner (Gemini → Claude → Ollama) when available and enabled,
        with local Ollama fallback. The self-correction loop still applies.

        If last_failure is provided (from the self-correction loop), the LLM
        is explicitly told what failed so it can adjust its decision.
        """
        # ── Build the self-correction preamble when retrying ────────
        correction_block = ""
        if last_failure:
            failed_action = last_failure.get("action", "unknown")
            failed_target = last_failure.get("target_ticket", "?")[:8]
            failed_error  = last_failure.get("error", "unknown error")
            correction_block = (
                "\n\n*** SELF-CORRECTION: Your previous action FAILED ***\n"
                f"Previous action: '{failed_action}' on ticket {failed_target}\n"
                f"Failure reason: {failed_error}\n"
                "The execution layer rejected your decision. You MUST choose a DIFFERENT "
                "action or a DIFFERENT target ticket to avoid repeating the same failure.\n"
            )

        system = (
            "You are the Hermes Controller — the autonomous GodMode orchestrator for Empire AI's agent mesh. "
            "You monitor completed/failed tasks and make high-leverage control decisions.\n\n"
            "AVAILABLE ACTIONS:\n"
            "  - retry: Re-queue a failed task with corrected parameters\n"
            "  - promote: Move a Done task to the next pipeline stage (scout→outreach→copywriter→render→dispatcher→quality)\n"
            "  - escalate: Flag a stalled task for operator intervention\n"
            "  - scale: If queue is deep, request more agent lanes\n"
            "  - ignore: Nothing to do right now\n\n"
            f"PIPELINE: {json.dumps(PIPELINE_NEXT)}\n\n"
            "RULES:\n"
            "1. Return ONLY a JSON object: {\"action\": \"...\", \"target_ticket\": \"...\", \"params\": {...}, \"reasoning\": \"...\"}\n"
            "2. For 'retry', include corrected params in .params.payload\n"
            "3. For 'promote', include the next task_type in .params.next_type\n"
            "4. Only act on tasks that NEED action — don't promote tasks that have already been promoted\n"
            "5. Be conservative — when in doubt, 'ignore'\n"
        )

        prompt = (
            f"RECENTLY COMPLETED TASKS (Done): {json.dumps([self._task_summary(t) for t in recent.get('done', [])])}\n"
            f"RECENTLY FAILED TASKS (Failed): {json.dumps([self._task_summary(t) for t in recent.get('failed', [])])}\n"
            f"QUEUE STATE: {json.dumps(queue)}"
            f"{correction_block}"
        )

        # Try Space Reasoner first (multi-provider: Gemini → Claude → Ollama)
        if SPACE_REASONING_ENABLED:
            if not _HAS_SPACE:
                log.warning("[controller] space reasoner not available (bots.space_providers missing) — falling back to Ollama")
            else:
                space_result = await self._space_think(system, prompt)
                if space_result.get("ok"):
                    log.info(f"[controller] space decision via {space_result.get('provider', '?')}")
                    return space_result["data"]
                log.info(f"[controller] space reasoner failed ({space_result.get('error')}), falling back to Ollama")

        return await self._ollama_chat_json(system, prompt)

    async def _space_think(self, system: str, prompt: str) -> Dict[str, Any]:
        """Query Space Reasoner for deep reasoning, traced to Langfuse."""
        async def _do() -> Dict[str, Any]:
            try:
                reasoner = SpaceReasoner()
                result = await reasoner.reason_json(
                    prompt=prompt,
                    system=system,
                    max_tokens=2048,
                )
                if result.get("ok"):
                    return {"ok": True, "data": result["data"], "provider": result.get("provider")}
                return {"ok": False, "error": result.get("error", "unknown")}
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}

        if HERMES_TRACING_ENABLED and _HAS_TRACING:
            async with TraceContext(
                name="hermes.space_think",
                model="multi-provider",
                input=prompt[:2000],
                system=system,
                task="controller.space_reasoning",
                tags=["provider:space", "task:godmode"],
            ) as ctx:
                result = await _do()
                ctx.set_output(
                    output=json.dumps(result)[:3000],
                )
                return result
        return await _do()

    async def _ollama_chat_json(self, system: str, prompt: str) -> Dict[str, Any]:
        """Direct Ollama chat for GodMode decision-making, traced to Langfuse.

        Flows through the TokenProxy cache when available — identical
        decisions within TTL are served from cache instead of hitting Ollama.
        """
        import httpx

        # ── Try TokenProxy cache first ────────────────────────────────
        try:
            from empire_token_proxy import get_token_proxy
            _proxy = get_token_proxy()
            compressed = _proxy.compress_prompt(prompt, task="controller.ollama")
            key_data = {"p": compressed, "s": system}
            result = await _proxy.cached_call(
                task="controller.ollama",
                key_data=key_data,
                llm_call=lambda: self._raw_ollama_call(system, compressed, httpx),
            )
            return result
        except ImportError:
            pass
        except Exception as e:
            log.debug(f"[controller] token proxy bypassed ({e}) — calling Ollama directly")

        # ── Direct fallback (no proxy) ───────────────────────────────
        return await self._raw_ollama_call(system, prompt, httpx)

    async def _raw_ollama_call(self, system: str, prompt: str, httpx_mod=None) -> Dict[str, Any]:
        """Raw Ollama call without caching (used by proxy fallback and standalone)."""
        import httpx as _httpx
        _http = httpx_mod or _httpx

        async def _do() -> Dict[str, Any]:
            try:
                async with _http.AsyncClient(timeout=60.0) as client:
                    r = await client.post(
                        f"{OLLAMA_URL}/api/chat",
                        json={
                            "model": "llama3.2:3b",
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": prompt},
                            ],
                            "stream": False,
                            "format": "json",
                        },
                    )
                    r.raise_for_status()
                    data = r.json()
                    return json.loads(data["message"]["content"])
            except Exception as e:
                log.error(f"[controller] LLM call failed: {e}")
                return {"action": "ignore", "reasoning": f"LLM error: {e}"}

        if HERMES_TRACING_ENABLED and _HAS_TRACING:
            async with TraceContext(
                name="hermes.ollama_decision",
                model="llama3.2:3b",
                input=prompt[:2000],
                system=system,
                task="controller.ollama_reasoning",
                tags=["provider:ollama", "task:godmode"],
            ) as ctx:
                result = await _do()
                ctx.set_output(
                    output=json.dumps(result)[:3000],
                )
                return result
        return await _do()

    # ── 4. EXECUTE THE ACTION ────────────────────────────────────────
    async def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the orchestration action in the agent mesh."""
        act = action.get("action", "ignore")
        ticket = action.get("target_ticket", "")
        params = action.get("params", {}) or {}

        if act == "ignore":
            return {"ok": True, "action": "ignore"}

        if act == "retry":
            return await self._execute_retry(ticket, params)

        if act == "promote":
            return await self._execute_promote(ticket, params)

        if act == "escalate":
            return await self._execute_escalate(ticket, params)

        return {"ok": False, "error": f"unknown action: {act}"}

    async def _execute_retry(self, ticket_id: str, params: Dict) -> Dict[str, Any]:
        """Re-queue a failed task as To-Do with corrected payload.
        Marks the original task as 'Retried' to prevent re-picking on subsequent cycles."""
        if self.sb is None:
            return {"ok": False, "error": "no Supabase client (EMPIRE_TESTING=1 mode)"}
        try:
            task = self.sb.table("agent_task_queue").select("*") \
                .eq("ticket_id", ticket_id).limit(1).execute()
            if not task.data:
                return {"ok": False, "error": "ticket not found"}

            t = task.data[0]

            # Guard: don't retry a task that's already been retried
            if t.get("status") == "Retried":
                return {"ok": False, "error": "task already retried"}

            # Insert a fresh To-Do task with corrected payload
            new_payload = params.get("payload", json.loads(t.get("payload", "{}")) if isinstance(t.get("payload"), str) else (t.get("payload") or {}))
            self.sb.table("agent_task_queue").insert({
                "task_type": t.get("task_type"),
                "payload": json.dumps(new_payload) if isinstance(new_payload, dict) else new_payload,
                "status": "To-Do",
                "assigned_agent": t.get("assigned_agent"),
                "priority": max(0, (t.get("priority") or 0) + 1),
            }).execute()

            # Mark the original as Retried so it won't be picked up again
            self.sb.table("agent_task_queue").update({
                "status": "Retried",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()

            log.info(f"[controller] retried {ticket_id[:8]} → new To-Do task (original marked Retried)")
            self.stats["retries"] += 1
            return {"ok": True, "action": "retry", "ticket_id": ticket_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _execute_promote(self, ticket_id: str, params: Dict) -> Dict[str, Any]:
        """Promote a Done task to the next pipeline stage.
        Checks for existing duplicates and marks the original as 'Promoted' to prevent re-promotion."""
        if self.sb is None:
            return {"ok": False, "error": "no Supabase client (EMPIRE_TESTING=1 mode)"}
        try:
            task = self.sb.table("agent_task_queue").select("*") \
                .eq("ticket_id", ticket_id).limit(1).execute()
            if not task.data:
                return {"ok": False, "error": "ticket not found"}

            t = task.data[0]

            # Guard: don't promote a task that's already been promoted
            if t.get("status") == "Promoted":
                return {"ok": False, "error": "task already promoted"}

            current_type = t.get("task_type", "")
            next_type = params.get("next_type") or PIPELINE_NEXT.get(current_type)

            if not next_type:
                return {"ok": True, "action": "terminal", "reason": "no next stage"}

            # Guard: check for duplicate — an existing To-Do task for this
            # pipeline already created from the same lead/source payload.
            # Uses JSONB path filtering on the payload column.
            payload = json.loads(t.get("payload", "{}")) if isinstance(t.get("payload"), str) else (t.get("payload") or {})
            dedup_key = payload.get("lead_id") or payload.get("source_id") or payload.get("campaign_id")
            if dedup_key:
                # Try JSONB path filtering for per-entity dedup
                try:
                    existing = self.sb.table("agent_task_queue").select("ticket_id") \
                        .eq("task_type", next_type) \
                        .in_("status", ["To-Do", "In Progress"]) \
                        .or_(f"payload->>'lead_id'.eq.{dedup_key},payload->>'source_id'.eq.{dedup_key},payload->>'campaign_id'.eq.{dedup_key}") \
                        .limit(1).execute()
                    if existing.data:
                        log.info(f"[controller] skip promote {ticket_id[:8]} — existing {next_type} task for {dedup_key}")
                        # Still mark original as Promoted to stop re-processing
                        self.sb.table("agent_task_queue").update({
                            "status": "Promoted",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                        }).eq("ticket_id", ticket_id).execute()
                        return {"ok": True, "action": "promote", "skipped": True, "reason": "duplicate detected"}
                except Exception:
                    # JSONB path filtering not supported — fall through and create
                    # (the 'Promoted' status guard already prevents re-promotion)
                    pass

            # Carry forward the payload to the next stage
            self.sb.table("agent_task_queue").insert({
                "task_type": next_type,
                "payload": json.dumps(payload),
                "status": "To-Do",
                "assigned_agent": STAGE_AGENT.get(next_type),
            }).execute()

            # Mark the original as Promoted so it won't be picked up again
            self.sb.table("agent_task_queue").update({
                "status": "Promoted",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()

            log.info(f"[controller] promoted {ticket_id[:8]} ({current_type} → {next_type})")
            self.stats["promotions"] += 1
            return {"ok": True, "action": "promote", "next_type": next_type}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _execute_escalate(self, ticket_id: str, params: Dict) -> Dict[str, Any]:
        """Flag a stalled task with an escalation note."""
        if self.sb is None:
            return {"ok": False, "error": "no Supabase client (EMPIRE_TESTING=1 mode)"}
        try:
            reason = params.get("reason", "controller flagged")
            self.sb.table("agent_task_queue").update({
                "error": f"[ESCALATED] {reason}",
            }).eq("ticket_id", ticket_id).execute()
            self.stats["escalations"] += 1
            return {"ok": True, "action": "escalate", "ticket_id": ticket_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 5. QC: VERIFY THE ACTION'S EFFECT ────────────────────────────
    async def verify_action(self, action: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """Simple heuristic QC: did the action succeed without error?"""
        if action.get("action") == "ignore":
            return True
        if result.get("ok") is True:
            return True
        return False

    # ── Chatwoot Webhook (notify conversations) ────────────────────
    _chatwoot_conv_id: Optional[int] = None  # reuse across cycles

    async def _notify_chatwoot(self, result: Dict[str, Any]) -> None:
        """Send significant Hermes decisions to a single Chatwoot conversation.

        Reuses a cached conversation_id across cycles to avoid flooding the
        inbox with a new conversation every 60s.
        """
        if not CHATWOOT_ENABLED or not _HAS_CHATWOOT:
            return
        try:
            cw = _get_chatwoot()
            if not cw:
                return
            action = result.get("action", "?")
            target = result.get("target", "—")
            if action in ("ignore", "nothing_to_do"):
                return

            msg = (
                f"Hermes Controller — {action}\n"
                f"Target: {target}\n"
                f"Attempts: {result.get('attempts', '?')}\n"
                f"Stats: {json.dumps(result.get('stats', {}))}"
            )

            # Reuse cached conversation if we already have one
            if self._chatwoot_conv_id:
                send_res = await cw.send_message(
                    conversation_id=self._chatwoot_conv_id,
                    content=msg,
                )
                if send_res.get("ok"):
                    log.debug(f"[controller] Chatwoot msg sent to conv {self._chatwoot_conv_id}")
                    return
                # Conversation may have been resolved — reset cache
                self._chatwoot_conv_id = None

            # No cached conversation — create one
            inboxes_res = await cw.list_inboxes()
            if not inboxes_res.get("ok"):
                return
            inboxes = inboxes_res.get("inboxes", [])
            if not inboxes:
                log.debug("[controller] no Chatwoot inboxes found")
                return

            conv_res = await cw.notify(
                inbox_id=inboxes[0].get("id"),
                contact_name="Hermes Controller",
                message=msg,
            )
            if conv_res.get("ok"):
                self._chatwoot_conv_id = conv_res.get("conversation_id")
                log.debug(f"[controller] Chatwoot conv {self._chatwoot_conv_id} created")
        except Exception as e:
            log.debug(f"[controller] Chatwoot notify failed: {e}")

    # ── GOD MODE MAIN LOOP ───────────────────────────────────────────
    async def run_god_cycle(self) -> Dict[str, Any]:
        """One GodMode orchestration cycle with self-correction."""
        self.stats["runs"] += 1

        recent = self.fetch_recent_tasks()
        queue = self.fetch_queue_state()

        if not recent["done"] and not recent["failed"]:
            return {"action": "nothing_to_do", "stats": self.stats}

        #   GodMode decision loop with explicit self-correction   ──
        last_failure = None
        for attempt in range(1, self.max_loops + 1):
            action = await self.decide_action(recent, queue, last_failure=last_failure)

            if action.get("action") == "ignore":
                return {"action": "ignore", "attempts": attempt, "stats": self.stats}

            result = await self.execute_action(action)

            if await self.verify_action(action, result):
                self.stats["actions_taken"] += 1
                return {
                    "action": action.get("action"),
                    "target": action.get("target_ticket", "")[:8],
                    "attempts": attempt,
                    "stats": self.stats,
                }

            # Self-correct: build explicit failure context for the next LLM call
            log.warning(f"[controller] action failed (attempt {attempt}/{self.max_loops}), self-correcting...")
            last_failure = {
                "action": action.get("action"),
                "target_ticket": action.get("target_ticket", ""),
                "error": result.get("error", "unknown"),
                "reasoning": action.get("reasoning", ""),
            }

        return {"action": "exhausted", "attempts": self.max_loops, "stats": self.stats}

    @staticmethod
    def _task_summary(t: Dict) -> Dict:
        return {
            "ticket_id": t.get("ticket_id", "")[:8],
            "task_type": t.get("task_type"),
            "status": t.get("status"),
            "assigned_agent": t.get("assigned_agent"),
            "priority": t.get("priority"),
        }


# ── REGISTER AS MESH AGENT ──────────────────────────────────────────
async def heartbeat():
    """Register/ping this controller as a mesh agent."""
    if _sb is None:
        log.debug("[controller] heartbeat skipped: no Supabase client (EMPIRE_TESTING=1 mode)")
        return
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": AGENT_NAME,
            "role_name": "hermes_controller",
            "status": AGENT_STATUS,
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": json.dumps(["controller", "orchestrator", "godmode"]),
            "task_types": [],
        }, on_conflict="agent_name").execute()
        log.info(f"[controller] heartbeat: {AGENT_NAME} → {AGENT_STATUS}")
    except Exception as e:
        log.error(f"[controller] heartbeat failed: {e}")


# ── MAIN LOOP ───────────────────────────────────────────────────────
async def run_loop():
    """Background loop: GodMode cycle every INTERVAL seconds."""
    log.info(f"[controller] Hermes Controller ONLINE (GodMode, interval={INTERVAL}s, loops={3})")

    # Resolve the Supabase client at startup and pass it explicitly via
    # the constructor. This makes the data flow obvious in one place
    # (here) instead of relying on the module-level `_sb` global. In
    # production `_sb` is set at module load; in test mode it's None
    # and the controller skips DB operations gracefully.
    sb_client: Optional["SupabaseClient"] = _sb

    controller = GodModeController(max_loops=3, sb=sb_client)

    await heartbeat()

    while True:
        try:
            result = await controller.run_god_cycle()
            act = result.get("action", "?")
            if act not in ("ignore", "nothing_to_do"):
                log.info(f"[controller] cycle: {act} | target={result.get('target','—')} | attempts={result.get('attempts','?')}")
                # Notify Chatwoot on real actions
                if CHATWOOT_ENABLED and _HAS_CHATWOOT:
                    await controller._notify_chatwoot(result)
        except Exception as e:
            log.error(f"[controller] cycle error: {e}")
        await asyncio.sleep(INTERVAL)


def run():
    """Sync entry point for main.py agent loop compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    run()
