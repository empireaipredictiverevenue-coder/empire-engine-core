"""
EMPIRE V49 · AGI LANE ENGINE
=============================
Autonomous lane-level decision engine. Every tick (60s default), feeds
the 32-lane grid state + recent task outcomes to the local LLM (Ollama)
and dispatches lane-specific actions via the Hermes task queue.

Lane actions map to pipeline stages:
  SCOUT  → scout.find_roofs      (prospecting)
  DRAFT  → outreach.draft_email  (email drafting)
  RENDER → studio.render_reel    (synthetic video)
  DISPATCH → revenue.connect_buyer (buyer matching)
  SKIP   → no action this cycle

AGI self-correction: if LLM output doesn't parse or creates duplicate
tasks, the engine self-corrects and re-queries (max 3 attempts per tick).

Wire-up: Added to main.py AGENTS list.
Run standalone: `python bots/agi_lane_engine.py`
"""

import os
import sys
import json
import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    # StrategyEvolution lives in empire_si_strategy. We use a string forward
    # reference (and a TYPE_CHECKING guard) so mypy / IDEs see the proper
    # type for the `si_strategy` parameter without paying any runtime import
    # cost. At runtime the actual instance is resolved lazily via
    # `bots.predictive_revenue.get_si_instance()` (see _resolve_si_strategies).
    from empire_si_strategy import StrategyEvolution  # noqa: F401

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("agi.lane.engine")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434")
INTERVAL     = int(os.environ.get("AGI_LANE_INTERVAL_SEC", "60"))
MAX_LANES    = 36

AGENT_NAME   = "agi.lane.engine"
AGENT_STATUS = "ACTIVE"

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── 32-Lane Grid (imported from mesh_orchestrator) ───────────────────
try:
    from mesh_orchestrator import LANES as _mesh_lanes
    LANES: Dict[int, Dict[str, str]] = {}
    for lid, data in _mesh_lanes.items():
        LANES[lid] = {
            "niche": data.get("niche", "Unknown"),
            "strategy": data.get("strategy", "STANDARD"),
            "source": data.get("source", "General"),
            "trigger": data.get("source", "general"),
        }
    log.info(f"[agi.lane] imported {len(LANES)} lanes from mesh_orchestrator")
except ImportError:
    # Fallback: define inline (stays synchronized with mesh_orchestrator.py)
    LANES: Dict[int, Dict[str, str]] = {}
    # Full 32-lane grid (mirrors mesh_orchestrator.py)
    _LANE_CFG = [
        (0, "Roofing Restoration", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (1, "Roofing Restoration", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (2, "Roofing Restoration", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (3, "Roofing Restoration", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (4, "Roofing Restoration", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (5, "HVAC", "UGLY_BANNER", "Web Auditor", "audit"),
        (6, "HVAC", "UGLY_BANNER", "Web Auditor", "audit"),
        (7, "SEO", "STANDARD", "SEO Optimizer", "audit"),
        (8, "SEO", "STANDARD", "SEO Optimizer", "audit"),
        (9, "SEO", "STANDARD", "SEO Optimizer", "audit"),
        (10, "Legal", "RECALL_SNIPER", "FDA Live Feed", "recall"),
        (11, "Legal", "RECALL_SNIPER", "FDA Live Feed", "recall"),
        (12, "Legal", "RECALL_SNIPER", "FDA Live Feed", "recall"),
        (13, "Legal", "RECALL_SNIPER", "FDA Live Feed", "recall"),
        (14, "Legal", "RECALL_SNIPER", "FDA Live Feed", "recall"),
        (15, "Insurance", "INSURANCE_STRIKE", "Insurance Lead Gen", "inbound"),
        (16, "Insurance", "INSURANCE_STRIKE", "Insurance Lead Gen", "inbound"),
        (17, "Insurance", "INSURANCE_STRIKE", "Insurance Lead Gen", "inbound"),
        (18, "Financial Services", "FINANCIAL_STRIKE", "Financial Lead Gen", "inbound"),
        (19, "Financial Services", "FINANCIAL_STRIKE", "Financial Lead Gen", "inbound"),
        (20, "Consumer CPA", "FINANCIAL_STRIKE", "Inbound Leads", "inbound"),
        (21, "Consumer CPA", "FINANCIAL_STRIKE", "Inbound Leads", "inbound"),
        (22, "Senior Care", "SENIOR_STRIKE", "Senior Lead Gen", "inbound"),
        (23, "Senior Care", "SENIOR_STRIKE", "Senior Lead Gen", "inbound"),
        (24, "Addiction Treatment", "HEALTH_STRIKE", "Healthcare Lead Gen", "inbound"),
        (25, "Education", "STANDARD", "Edu Lead Gen", "inbound"),
        (26, "Education", "STANDARD", "Edu Lead Gen", "inbound"),
        (27, "Healthcare", "HEALTH_STRIKE", "Healthcare Lead Gen", "inbound"),
        (28, "Healthcare", "HEALTH_STRIKE", "Healthcare Lead Gen", "inbound"),
        (29, "Business Services", "BIZ_STRIKE", "B2B Lead Gen", "inbound"),
        (30, "Business Services", "BIZ_STRIKE", "B2B Lead Gen", "inbound"),
        (31, "Business Services", "BIZ_STRIKE", "B2B Lead Gen", "inbound"),
        (32, "Financial Services", "FINANCIAL_STRIKE", "Financial Lead Gen", "inbound"),
        (33, "Financial Services", "FINANCIAL_STRIKE", "Financial Lead Gen", "inbound"),
        (34, "Home Services", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (35, "Home Services", "UGLY_BANNER", "Web Auditor", "audit"),
        (36, "Commercial Roofing", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (37, "Commercial Solar", "AGGRESSIVE_STRIKE", "Storm Scout", "storm"),
        (38, "Debt Relief", "FINANCIAL_STRIKE", "Financial Lead Gen", "inbound"),
    ]
    for lid, niche, strategy, source, trigger in _LANE_CFG:
        LANES[lid] = {"niche": niche, "strategy": strategy,
                       "source": source, "trigger": trigger}

# ── Pipeline stage mapping: AGI action → Hermes task_type ────────────
ACTION_TASK_MAP: Dict[str, str] = {
    "SCOUT":    "scout.find_roofs",
    "DRAFT":    "outreach.draft_email",
    "RENDER":   "studio.render_reel",
    "DISPATCH": "revenue.connect_buyer",
}

# ── Agent assignment per action ──────────────────────────────────────
ACTION_AGENT_MAP: Dict[str, str] = {
    "SCOUT":    "mesh.scout",
    "DRAFT":    "mesh.outreach",
    "RENDER":   "mesh.render",
    "DISPATCH": "mesh.dispatcher",
}


# ── AGI LANE ENGINE ──────────────────────────────────────────────────
class AGILaneEngine:
    """
    Autonomous lane decision engine.
    Each tick: load lane states → LLM decides actions → dispatch to Hermes queue.
    Self-corrects on parse failures or duplicate detection.
    
    SI Integration: reads evolved strategies from the persistent
    StrategyEvolution instance (fed by RevenueBrain). If a niche has
    an evolved best strategy with better revenue outcomes, the engine
    uses it instead of the hardcoded archetype.
    """

    def __init__(
        self,
        max_correction_loops: int = 3,
        si_strategy: Optional["StrategyEvolution"] = None,
        revenue_score_fn: Optional[Callable[[int], float]] = None,
    ):
        """
        Args:
            max_correction_loops: max LLM re-query attempts per tick.
            si_strategy: optional StrategyEvolution instance. When provided,
                the engine uses it directly for evolved-strategy lookup.
                When None, falls back to the shared singleton
                `bots.predictive_revenue.get_si_instance()` at runtime
                (back-compat for hub.py's late-binding pattern).
            revenue_score_fn: optional callable `int -> float` that returns
                a lane's revenue score. When provided, the engine uses it
                directly for revenue-priority boosts. When None, falls back
                to `bots.predictive_revenue.lane_revenue_score` at runtime
                (back-compat for the late-binding pattern).
        """
        self.max_loops = max_correction_loops
        self.si_strategy = si_strategy
        self.revenue_score_fn = revenue_score_fn
        self.stats: Dict[str, Any] = {"ticks": 0, "actions_dispatched": 0, "lanes_active": 0}

    # ── 0. RESOLVE SI-EVOLVED STRATEGIES ─────────────────────────
    def _resolve_si_strategies(self) -> Dict[str, Dict[str, Any]]:
        """
        Read the persistent SI strategy instance (fed by RevenueBrain).
        Returns {niche: {best_strategy, genome, score, generation}} for each
        niche that has accumulated enough outcomes to evolve.

        Uses `self.si_strategy` directly (injected via constructor). If
        it's None, returns {} and the engine falls back to hardcoded
        archetypes. Production always wires a real instance via run_loop();
        tests inject mocks.
        """
        si_by_niche: Dict[str, Dict[str, Any]] = {}
        si_instance = self.si_strategy
        if si_instance is None:
            return si_by_niche
        try:
            # One snapshot call — avoids 4x overhead inside the loop
            snap = si_instance.snapshot()
            best_per_niche = snap.get("best_per_niche", {})
            by_niche = snap.get("by_niche", {})

            # Derive niche list from LANES (not hardcoded)
            niches = list(set(l["niche"] for l in LANES.values()))

            for niche in niches:
                best_info = best_per_niche.get(niche)
                if not best_info or not best_info.get("name"):
                    continue

                best_name = best_info["name"]
                genome = si_instance.get_genome(best_name, niche)

                # Generation lives on the strategy object, not the genome
                generation = 0
                for entry in by_niche.get(niche, []):
                    if entry.get("name") == best_name:
                        generation = entry.get("generation", 0)
                        break

                si_by_niche[niche] = {
                    "strategy": best_name,
                    "genome": genome,
                    "score": best_info.get("score", 0),
                    "generation": generation,
                }
        except Exception as e:
            log.debug(f"[agi.lane] SI strategy lookup failed (will use archetypes): {e}")
        return si_by_niche

    # ── 1. LOAD LANE STATES ─────────────────────────────────────────
    def load_lane_states(self) -> Dict[int, Dict[str, Any]]:
        """
        Build per-lane state from the Hermes task queue.
        SI-evolved strategies override hardcoded archetypes when available.
        """
        si_strategies = self._resolve_si_strategies()
        
        try:
            r = _sb.table("agent_task_queue").select("task_type,status,payload,created_at,completed_at").limit(500).execute()
            tasks = r.data or []
        except Exception as e:
            log.error(f"[agi.lane] load_lane_states DB error: {e}")
            return {}

        # Initialize all 32 lanes
        states: Dict[int, Dict[str, Any]] = {}
        for lid in LANES:
            niche = LANES[lid]["niche"]
            # Use SI-evolved strategy if available, otherwise hardcoded archetype
            si = si_strategies.get(niche)
            strategy_name = si["strategy"] if si else LANES[lid]["strategy"]
            strategy_gen = si.get("generation", 0) if si else 0
            
            states[lid] = {
                "lane_id": lid,
                "niche": niche,
                "strategy": strategy_name,
                "strategy_gen": strategy_gen,
                "si_score": si.get("score", 0) if si else 0,
                "source": LANES[lid]["source"],
                "pending": 0,
                "in_progress": 0,
                "done_24h": 0,
                "failed_24h": 0,
                "total_tasks": 0,
            }

        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)

        for t in tasks:
            # Determine lane from payload
            payload = {}
            try:
                raw = t.get("payload", "{}")
                payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                pass
            lane_id = payload.get("lane_id")
            if lane_id is None or lane_id not in states:
                continue

            st = states[lane_id]
            status = t.get("status", "unknown")
            st["total_tasks"] += 1

            if status == "To-Do":
                st["pending"] += 1
            elif status == "In Progress":
                st["in_progress"] += 1
            elif status == "Done":
                ts = t.get("completed_at") or t.get("created_at", "")
                if self._is_recent(ts, day_ago):
                    st["done_24h"] += 1
            elif status == "Failed":
                ts = t.get("completed_at") or t.get("created_at", "")
                if self._is_recent(ts, day_ago):
                    st["failed_24h"] += 1

        return states

    # ── 2. LLM: DECIDE LANE ACTIONS ──────────────────────────────────
    async def decide_actions(
        self, states: Dict[int, Dict[str, Any]],
        last_actions: Optional[Dict[int, str]] = None,
    ) -> Dict[int, str]:
        """
        Feed all 32 lane states to the LLM. Returns {lane_id: action} for
        lanes that need action. Self-corrects by including last_actions
        context on retry.
        """
        # Build a compact summary for the LLM
        lane_summaries = []
        for lid in sorted(states.keys()):
            s = states[lid]
            gen_tag = f" gen{s['strategy_gen']}" if s.get('strategy_gen', 0) > 0 else ""
            si_tag = f" SI:{s.get('si_score', 0):.2f}" if s.get('si_score', 0) > 0 else ""
            lane_summaries.append(
                f"L{lid}: {s['niche'][:20]} | {s['strategy']}{gen_tag}{si_tag} | "
                f"pend={s['pending']} prog={s['in_progress']} "
                f"done24={s['done_24h']} fail24={s['failed_24h']}"
            )

        correction_block = ""
        if last_actions:
            correction_block = (
                "\n\n*** SELF-CORRECTION: Previous dispatch had errors ***\n"
                f"Previous actions (that failed): {json.dumps({str(k): v for k, v in last_actions.items()})}\n"
                "Choose DIFFERENT actions or DIFFERENT lanes to avoid repeating errors.\n"
            )

        system = (
            "You are the AGI Lane Engine for Empire AI — an autonomous 32-lane lead-generation "
            "orchestrator. Your job is to review lane states and decide what each lane should do. "
            "Return ONLY a JSON object mapping lane IDs to actions.\n\n"
            "AVAILABLE ACTIONS:\n"
            "  SCOUT    — prospect for new targets (scout.find_roofs)\n"
            "  DRAFT    — draft outreach email (outreach.draft_email)\n"
            "  RENDER   — generate synthetic video ad (studio.render_reel)\n"
            "  DISPATCH — match with buyer/partner (revenue.connect_buyer)\n"
            "  SKIP     — no action this cycle\n\n"
            "RULES:\n"
            "1. Only include lanes that NEED action — skip idle lanes\n"
            "2. Lanes with 0 pending tasks but high done_24h → SCOUT (find fresh targets)\n"
            "3. Lanes with pending tasks but 0 in_progress → DRAFT or DISPATCH to unblock\n"
            "4. Lanes with high fail_24h → SKIP (let them cool down)\n"
            "5. Lanes with done_24h > 5 and no pending → DISPATCH (connect to buyers)\n"
            "6. Lanes with niche 'Roofing' and low pending → RENDER (generate storm video)\n"
            "7. Maximum 8 lanes per tick (don't overload the queue)\n"
            "8. Lanes with SI-evolved strategies (gen>0) and high SI scores → prioritize — they've proven revenue outcomes\n"
            "9. Lanes still using base archetypes (gen=0) → treat as exploration, balance with proven lanes\n"
            "10. Format: {\"0\": \"SCOUT\", \"5\": \"DRAFT\", ...} — only lanes with actions\n"
        )

        prompt = (
            f"LANE STATES (32 lanes):\n"
            + "\n".join(lane_summaries)
            + f"\n\nDecide actions for lanes that need them. Return JSON only.{correction_block}"
        )

        result = await self._ollama_chat_json(system, prompt)

        # Parse LLM output into {int: str} mapping
        actions: Dict[int, str] = {}
        if not result or result.get("action") == "ignore":
            return actions

        for key, val in (result.items() if isinstance(result, dict) else []):
            # Skip metadata keys
            if key in ("_error", "action", "reasoning", "error"):
                continue
            try:
                lid = int(str(key))
                action = str(val).upper().strip()
                if action in ACTION_TASK_MAP and lid in LANES:
                    actions[lid] = action
            except (ValueError, TypeError):
                continue

        # Code-level clamp: max 8 lanes per tick
        if len(actions) > 8:
            # Keep the first 8 (LLM-ordered by priority)
            actions = dict(list(actions.items())[:8])

        return actions

    async def _ollama_chat_json(self, system: str, prompt: str) -> Dict[str, Any]:
        """Direct Ollama chat for AGI lane decision-making."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
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
            log.error(f"[agi.lane] LLM call failed: {e}")
            return {"_error": str(e)}

    # ── 3. DISPATCH ACTIONS TO HERMES QUEUE ──────────────────────────
    async def dispatch_actions(self, actions: Dict[int, str], states: Dict[int, Dict[str, Any]]) -> Dict[str, int]:
        """
        Create Hermes task tickets for each decided action.
        Returns {action: count} summary.
        Deduplicates: skips if a To-Do task of the same type already
        exists for this lane within the last 5 minutes.
        Uses a single batch query to fetch all recent To-Do tasks,
        then filters in Python (avoids N+1 round trips).
        """
        dispatched: Dict[str, int] = {}
        five_min_ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        # ── Batch dedup: fetch ALL recent To-Do tasks once ──────────
        recent_payloads: Dict[str, List[int]] = {}  # task_type → list of lane_ids
        try:
            existing = _sb.table("agent_task_queue").select("task_type,payload") \
                .eq("status", "To-Do") \
                .gte("created_at", five_min_ago) \
                .limit(200).execute()
            for ex in (existing.data or []):
                tt = ex.get("task_type", "")
                raw = ex.get("payload", "{}")
                try:
                    p = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    lid = p.get("lane_id")
                    if lid is not None:
                        recent_payloads.setdefault(tt, []).append(lid)
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[agi.lane] dedup batch query failed: {e}")

        # ── Dispatch each action ────────────────────────────────────
        for lid, action in actions.items():
            task_type = ACTION_TASK_MAP[action]
            agent = ACTION_AGENT_MAP[action]
            state = states.get(lid, {})

            # Dedup: skip if this lane already has a recent To-Do of this type
            if lid in recent_payloads.get(task_type, []):
                log.info(f"[agi.lane] skip L{lid} {action} — existing To-Do task (batch dedup)")
                continue

            # Create the task ticket
            try:
                payload = {
                    "lane_id": lid,
                    "niche": state.get("niche", ""),
                    "strategy": state.get("strategy", ""),
                    "source": state.get("source", ""),
                    "agi_action": action,
                    "agi_tick": self.stats["ticks"],
                }
                _sb.table("agent_task_queue").insert({
                    "task_type": task_type,
                    "payload": json.dumps(payload),
                    "status": "To-Do",
                    "assigned_agent": agent,
                    "priority": self._lane_priority(state),
                }).execute()
                dispatched[action] = dispatched.get(action, 0) + 1
                self.stats["actions_dispatched"] += 1
            except Exception as e:
                log.error(f"[agi.lane] dispatch L{lid} {action} failed: {e}")

        return dispatched

    def _lane_priority(self, state: Dict[str, Any]) -> int:
        """Calculate task priority from lane state + revenue potential. Higher = more urgent."""
        score = 5  # base
        if state.get("pending", 0) == 0 and state.get("done_24h", 0) > 0:
            score += 3  # lane has momentum, keep it going
        if state.get("failed_24h", 0) > 3:
            score -= 2  # cool down failing lanes
        if state.get("in_progress", 0) == 0 and state.get("pending", 0) > 0:
            score += 2  # unblock stalled lanes
        # Revenue potential boost: high-MRR lanes get priority
        # Uses self.revenue_score_fn (injected via constructor) directly.
        # If it's None, no revenue boost is applied — production always
        # wires a real fn via run_loop(); tests inject mocks.
        revenue_fn = self.revenue_score_fn
        if revenue_fn is not None:
            try:
                rev_score = revenue_fn(state.get("lane_id", -1))
                if rev_score >= 7:
                    score += 3  # top revenue lane — push hard
                elif rev_score >= 4:
                    score += 1  # moderate revenue lane — slight boost
                elif rev_score <= 1 and state.get("pending", 0) == 0:
                    score -= 1  # dead-end lane — deprioritize
            except Exception:
                pass  # revenue engine raised — no penalty
        # SI strategy score boost: proven strategies get priority
        si_score = state.get("si_score", 0)
        if si_score > 0.5:
            score += 2  # high-performing evolved strategy
        elif si_score > 0.2:
            score += 1  # moderately evolved strategy
        if state.get("strategy_gen", 0) > 1:
            score += 1  # multi-generation strategy — battle-tested
        return max(1, score)

    @staticmethod
    def _is_recent(ts: str, day_ago: datetime) -> bool:
        """Try multiple ISO formats. Returns True if timestamp is after day_ago."""
        if not ts:
            return False
        for fmt in (ts, ts.replace("Z", "+00:00"), ts.replace(" ", "T")):
            try:
                return datetime.fromisoformat(fmt) > day_ago
            except Exception:
                continue
        return False

    # ── MAIN TICK ────────────────────────────────────────────────────
    async def run_tick(self) -> Dict[str, Any]:
        """One AGI lane engine tick: load states → LLM decide → dispatch."""
        self.stats["ticks"] += 1

        # Load lane states
        states = self.load_lane_states()
        active_lanes = sum(1 for s in states.values() if s["total_tasks"] > 0)
        self.stats["lanes_active"] = active_lanes

        if not states:
            return {"action": "no_data", "stats": self.stats}

        #   AGI decision loop with self-correction   ─────────────────
        # Self-correction only fires when LLM output is unparseable
        # (empty actions dict). Dedup is NOT a failure — it's expected.
        last_actions = None
        for attempt in range(1, self.max_loops + 1):
            actions = await self.decide_actions(states, last_actions=last_actions)

            if not actions:
                if last_actions is not None:
                    # We self-corrected and still got nothing — give up
                    log.warning(f"[agi.lane] tick {self.stats['ticks']} — no parseable actions after correction")
                    return {"action": "none", "lanes_active": active_lanes, "attempts": attempt, "stats": self.stats}
                # First attempt returned empty — self-correct with correction context
                log.warning(f"[agi.lane] tick {self.stats['ticks']} — LLM returned no actions (attempt {attempt}), retrying with correction")
                last_actions = {}  # sentinel: triggers correction prompt on retry
                continue

            dispatched = await self.dispatch_actions(actions, states)

            if dispatched:
                log.info(
                    f"[agi.lane] tick {self.stats['ticks']} — dispatched {sum(dispatched.values())} actions "
                    f"across {len(actions)} lanes (attempt {attempt}): {dict(dispatched)}"
                )
                return {
                    "action": "dispatched",
                    "lanes_acted": len(actions),
                    "dispatched": dispatched,
                    "lanes_active": active_lanes,
                    "attempts": attempt,
                    "stats": self.stats,
                }

            # All actions were deduped — not a failure, just idle
            log.info(f"[agi.lane] tick {self.stats['ticks']} — all {len(actions)} actions deduped, lanes already covered")
            return {"action": "deduped_all", "lanes_checked": len(actions), "attempts": attempt, "stats": self.stats}

        return {"action": "exhausted", "attempts": self.max_loops, "stats": self.stats}


# ── REGISTER AS MESH AGENT ──────────────────────────────────────────
async def heartbeat():
    """Register/ping this engine as a mesh agent."""
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": AGENT_NAME,
            "status": AGENT_STATUS,
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
            "capabilities": json.dumps(["controller", "agi", "lane_engine", "orchestrator"]),
            "task_types": list(ACTION_TASK_MAP.values()),
        }, on_conflict="agent_name").execute()
        log.info(f"[agi.lane] heartbeat: {AGENT_NAME} → {AGENT_STATUS}")
    except Exception as e:
        log.error(f"[agi.lane] heartbeat failed: {e}")


# ── MAIN LOOP ───────────────────────────────────────────────────────
async def run_loop():
    """Background loop: AGI lane decision cycle every INTERVAL seconds."""
    log.info(f"[agi.lane] AGI Lane Engine ONLINE ({MAX_LANES} lanes, interval={INTERVAL}s, loops={3})")

    # Resolve predictive_revenue dependencies at startup and pass them
    # explicitly via the constructor. This makes the data flow obvious in
    # one place (here) instead of relying on the late-binding fallback
    # inside AGILaneEngine._resolve_si_strategies / _lane_priority. The
    # fallback paths in those methods remain for unit-test ergonomics,
    # but production always wires the deps in explicitly via this block.
    si_instance: Optional["StrategyEvolution"] = None
    revenue_score_fn: Optional[Callable[[int], float]] = None
    try:
        from bots.predictive_revenue import get_si_instance, lane_revenue_score
        si_instance = get_si_instance()
        revenue_score_fn = lane_revenue_score
        log.info(
            f"[agi.lane] wired deps: si_instance={'set' if si_instance else 'None'} "
            f"revenue_score_fn={'set' if revenue_score_fn else 'None'}"
        )
    except Exception as e:
        log.warning(f"[agi.lane] could not resolve predictive_revenue deps at startup: {e}")

    engine = AGILaneEngine(
        max_correction_loops=3,
        si_strategy=si_instance,
        revenue_score_fn=revenue_score_fn,
    )

    await heartbeat()

    while True:
        try:
            result = await engine.run_tick()
            act = result.get("action", "?")
            if act == "dispatched":
                disp = result.get("dispatched", {})
                log.info(
                    f"[agi.lane] tick complete: {sum(disp.values())} tasks across {result.get('lanes_acted', 0)} lanes "
                    f"({' · '.join(f'{k}={v}' for k, v in disp.items())})"
                )
            elif act == "none":
                pass  # quiet on idle ticks
            else:
                log.info(f"[agi.lane] tick: {act} | {result.get('lanes_active', '?')} active lanes")
        except Exception as e:
            log.error(f"[agi.lane] tick error: {e}")
        await asyncio.sleep(INTERVAL)


def run():
    """Sync entry point for main.py agent loop compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    run()
