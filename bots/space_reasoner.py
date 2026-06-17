"""
EMPIRE V49 · SPACE REASONER AGENT
==================================
Deep reasoning agent for complex decisions. Uses multi-provider LLM
abstraction (Gemini free tier → Claude API → Ollama fallback) to
provide thoughtful analysis for the Hermes controller and other agents.

How it works:
  1. Registers as 'space_reasoner' role in the agent fleet
  2. Monitors agent_task_queue for space.* tasks (space.think, space.decide)
  3. Processes each task using SpaceReasoner (best available provider)
  4. Posts results back to the queue (Done/Failed)

Hermes controller calls consult() directly for inline reasoning
(this avoids queue latency for time-sensitive decisions).

Operators can submit tasks via:
  - agent_task_queue insert with task_type='space.think' or 'space.decide'
  - Payload: {prompt, system?, max_tokens?, prefer_provider?}

Configuration (env vars):
  GEMINI_API_KEY           — Google AI Studio API key (free tier)
  ANTHROPIC_API_KEY        — Anthropic Claude API key (trial credits)
  OLLAMA_URL               — Local Ollama endpoint (fallback)
  SPACE_REASONER_INTERVAL_SEC — Poll interval (default 30s)
"""

import os
import sys
import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client
from bots.space_providers import SpaceReasoner, GEMINI_API_KEY, CLAUDE_API_KEY, get_reasoner

log = logging.getLogger("empire.space_reasoner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [space] %(message)s")

# ── Configuration ──────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
INTERVAL = int(os.environ.get("SPACE_REASONER_INTERVAL_SEC", "30"))
AGENT_NAME = "space_reasoner"
AGENT_STATUS = "ACTIVE"

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("[space] SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    _sb = None
else:
    _sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Heartbeat ──────────────────────────────────────────────────────────


def heartbeat():
    """Register/ping the space reasoner in agent_registry."""
    if not _sb:
        return
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": AGENT_NAME,
            "role_name": "space_reasoner",
            "status": AGENT_STATUS,
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": [
                "deep_reasoning", "multi_provider_llm",
                "gemini_api", "claude_api",
                "structured_thinking", "goal_decomposition",
                "decision_analysis", "strategy_evaluation",
            ],
            "task_types": ["space.think", "space.analyze", "space.decide"],
        }, on_conflict="agent_name").execute()
        log.debug(f"[space] heartbeat: {AGENT_NAME} → {AGENT_STATUS}")
    except Exception as e:
        log.debug(f"[space] heartbeat failed: {e}")


# ── Task Processing ────────────────────────────────────────────────────


async def process_task(task: dict) -> dict:
    """Process a single reasoning task from the queue.

    Returns {"ok": True, "result": str, "provider": str} on success,
    or {"ok": False, "error": str} on failure.
    """
    try:
        raw_payload = task.get("payload", "{}")
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else (raw_payload or {})
        prompt = payload.get("prompt", "").strip()
        system = payload.get("system", "").strip()
        task_type = task.get("task_type", "space.think")
        max_tokens = payload.get("max_tokens", 4096)
        prefer = payload.get("prefer_provider", "")

        if not prompt:
            return {"ok": False, "error": "no prompt in payload"}

        reasoner = SpaceReasoner(prefer=prefer)

        if task_type == "space.decide":
            # Structured decision-making: wrap prompt for deeper reasoning
            structured_prompt = (
                "You are making a structured decision. Follow these steps:\n"
                "1. Analyze the situation and identify key factors\n"
                "2. List 2-3 possible options with pros/cons\n"
                "3. Recommend the best option with clear reasoning\n"
                "4. State your confidence level (high/medium/low)\n\n"
                f"Decision context:\n{prompt}"
            )
            result = await reasoner.reason(
                prompt=structured_prompt,
                system=system or "You are a strategic decision-making assistant.",
                max_tokens=max_tokens,
            )
        else:
            # General thinking task
            result = await reasoner.reason(
                prompt=prompt,
                system=system or "You are a deep reasoning assistant. Think step by step.",
                max_tokens=max_tokens,
            )

        if result.get("ok"):
            return {"ok": True, "result": result["text"], "provider": result["provider"]}
        return {"ok": False, "error": result.get("error", "unknown error")}

    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"payload parse: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


# ── Main Cycle ─────────────────────────────────────────────────────────


async def run_cycle():
    """One cycle: fetch pending space.* tasks and process them."""
    if not _sb:
        return

    try:
        r = (
            _sb.table("agent_task_queue")
            .select("*")
            .in_("task_type", ["space.think", "space.analyze", "space.decide"])
            .eq("status", "To-Do")
            .order("priority", desc=True)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        tasks = r.data or []
    except Exception as e:
        log.warning(f"[space] fetch error: {e}")
        return

    for task in tasks:
        ticket_id = task.get("ticket_id", "")
        log.info(f"[space] processing {task.get('task_type')} / {ticket_id[:8]}")

        result = await process_task(task)

        if result.get("ok"):
            _sb.table("agent_task_queue").update({
                "status": "Done",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": json.dumps({"result": result["result"], "provider": result["provider"]}),
            }).eq("ticket_id", ticket_id).execute()
            log.info(f"[space] ✅ {ticket_id[:8]} — {result.get('provider', '?')}")
        else:
            _sb.table("agent_task_queue").update({
                "status": "Failed",
                "error": result.get("error", "unknown error"),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticket_id", ticket_id).execute()
            log.warning(f"[space] ❌ {ticket_id[:8]} — {result.get('error', '?')}")


async def run_loop(interval_seconds: int = None):
    """Background loop: poll for tasks every N seconds."""
    if interval_seconds is None:
        interval_seconds = INTERVAL

    # Log which providers are configured
    providers_available = []
    if GEMINI_API_KEY:
        providers_available.append("Gemini (free tier)")
    if CLAUDE_API_KEY:
        providers_available.append("Claude (API)")
    providers_available.append("Ollama (local fallback)")

    log.info(f"[space] 🧠 Space Reasoner ONLINE · interval={interval_seconds}s")
    log.info(f"[space] Providers: {' → '.join(providers_available)}")

    if not _sb:
        log.warning("[space] No Supabase client — running in consult-only mode (no task queue)")
    else:
        heartbeat()

    while True:
        try:
            if _sb:
                await run_cycle()
        except Exception as e:
            log.error(f"[space] cycle error: {e}")
        await asyncio.sleep(interval_seconds)


# ── Inline Consult API (used by Hermes controller and other agents) ────

# get_reasoner() is imported from bots.space_providers — singleton lives there


async def consult(prompt: str, system: str = "", prefer: str = "", max_tokens: int = 2048) -> dict:
    """Inline deep reasoning — no task queue involved.

    Used by Hermes controller and other agents for time-sensitive decisions.
    Returns {"text": str, "provider": str, "ok": True} or {"ok": False, "error": str}.
    """
    reasoner = get_reasoner(prefer=prefer)
    return await reasoner.reason(prompt=prompt, system=system, max_tokens=max_tokens)


async def consult_json(prompt: str, system: str = "", prefer: str = "", max_tokens: int = 2048) -> dict:
    """Inline deep reasoning with JSON output.

    Returns {"ok": True, "data": dict, "provider": str} or {"ok": False, "error": str}.
    """
    reasoner = get_reasoner(prefer=prefer)
    return await reasoner.reason_json(prompt=prompt, system=system, max_tokens=max_tokens)


# ── Standalone CLI ─────────────────────────────────────────────────────


def run():
    """Sync entry point for PM2 / main.py compatibility."""
    asyncio.run(run_loop())


async def run_once():
    """Run a single cycle for testing."""
    if _sb:
        heartbeat()
        await run_cycle()
    log.info("[space] run_once complete")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Empire Space Reasoner Agent")
    p.add_argument("--once", action="store_true", help="Run a single cycle")
    p.add_argument("--interval", type=int, default=30, help="Poll interval in seconds")
    p.add_argument("--consult", type=str, default="", help="Inline consult prompt (prints result)")
    args = p.parse_args()

    if args.consult:
        result = asyncio.run(consult(args.consult))
        print(json.dumps(result, indent=2, default=str))
    elif args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_loop(args.interval))
