"""
EMPIRE V49 · PANEL COURT — 10-AGENT ENSEMBLE VOTING SYSTEM
============================================================
Architecture:
  1. AGENT POOL       — 10 CompetitorAgents, each with unique temperature/prompt style
  2. ENSEMBLE RUN     — All 10 score the SAME lead in parallel via asyncio.gather
  3. 5-ROLE PANEL     — CFO, Growth Coach, Strategy Expert, Brand Purist, and AGI Judge
                         review ALL 10 outputs and assign consensus scores
  4. VOTE & DISPATCH  — The output with the highest consensus score wins and is dispatched
  5. LEARNING LOOP    — The 9 losing agents adapt toward the winner's approach
                         (temperature, framing weights) — building "work ethic"

The 5-role panel does NOT debate each other. They are the VOTING JURY that evaluates
which of the 10 competing agent outputs is the strongest.

Supabase tables:
  - panel_court_decisions: ensemble results with per-agent scores and panel votes
  - agent_pool_state: persisted agent win/loss records and learning state
"""

import os
import sys
import json
import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Awaitable, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    # Forward references for the injected dependency types. We use
    # TYPE_CHECKING so mypy/IDEs see the proper types for the
    # `live_broadcaster`, `get_latest_wisdom`, and `sb` parameters
    # without paying any runtime import cost.
    from supabase import Client as SupabaseClient  # noqa: F401

sys.path.insert(0, "/root/empire-v49")
try:
    from empire_dream import get_latest_wisdom as _module_get_latest_wisdom
except ImportError:
    _module_get_latest_wisdom = None

try:
    from empire_live import live_broadcaster as _module_live_broadcaster
except ImportError:
    _module_live_broadcaster = None

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("panel_court")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── 10 COMPETITOR AGENT FRAMING STYLES ──────────────────────────────
# Each agent has a unique "personality" that influences HOW they analyze.
# Key: each framing emphasizes different scoring dimensions so outputs vary meaningfully.

AGENT_FRAMINGS = [
    "You are a meticulous quant. Score on: margin/cost ratio (40%), risk flags (30%), intent signal (30%). Be precise.",
    "You are a gut-instinct closer. Score on: raw urgency feel (50%), phone presence (30%), address quality (20%). Act fast.",
    "You are a conservative auditor. Score on: compliance risk (40%), margin floor (35%), source trust (25%). Reject liberally.",
    "You are an aggressive growth hunter. Score on: conversion velocity (45%), buyer demand fit (35%), phone availability (20%). Push everything viable.",
    "You are a geo-strategist. Score on: metro demand (40%), seasonal timing (30%), cross-niche potential (30%). Think market-level.",
    "You are a brand purist. Score on: premium feel (50%), source authenticity (30%), buyer reputation fit (20%). Reject anything spammy.",
    "You are a profit-maximizing CFO. Score on: projected net margin (50%), CPA estimate (30%), retainer potential (20%). Numbers only.",
    "You are a customer-success advocate. Score on: lead→buyer match quality (45%), complaint risk (30%), long-term retention (25%).",
    "You are a pipeline velocity operator. Score on: time-to-close (40%), actionable phone (35%), urgency signals (25%). Speed wins.",
    "You are a perfectionist forensic analyst. Score on: data completeness (30%), edge-case risks (40%), meta quality (30%). Be skeptical.",
]


# ── COMPETITOR AGENT ─────────────────────────────────────────────────
class CompetitorAgent:
    """Individual agent in the 10-agent pool that scores leads."""

    def __init__(self, agent_id: int, temperature: float, framing: str):
        self.id = agent_id
        self.temperature = temperature
        self.framing = framing  # unique prompt style with scoring dimensions
        self.wins = 0
        self.losses = 0
        self.total_runs = 0
        self.avg_score = 0.0
        self._score_sum = 0.0
        # Accuracy tracking from real-world outcomes
        self.accuracy_weight = 1.0   # multiplier based on actual conversion rate
        self._real_dispatches = 0
        self._real_conversions = 0

    @property
    def win_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return round(self.wins / self.total_runs, 3)

    @property
    def real_conversion_rate(self) -> float:
        if self._real_dispatches == 0:
            return 0.0
        return round(self._real_conversions / self._real_dispatches, 3)

    def record_result(self, won: bool, score: float):
        self.total_runs += 1
        self._score_sum += score
        self.avg_score = round(self._score_sum / self.total_runs, 3)
        if won:
            self.wins += 1
        else:
            self.losses += 1

    def record_real_outcome(self, converted: bool):
        """Called when a lead this agent won is later confirmed converted or not."""
        self._real_dispatches += 1
        if converted:
            self._real_conversions += 1
        # Adjust accuracy weight toward real performance (slow-moving average)
        target = max(0.5, self.real_conversion_rate * 2) if self._real_dispatches >= 3 else 1.0
        self.accuracy_weight = round(
            self.accuracy_weight + (target - self.accuracy_weight) * 0.1, 3
        )

    def learn_from_winner(self, winner_temp: float):
        """Nudge toward the winner's approach — small adjustments each loss."""
        rate = 0.05
        self.temperature = max(0.05, min(0.8,
            self.temperature + (winner_temp - self.temperature) * rate))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "temperature": round(self.temperature, 2),
            "framing": self.framing[:80],
            "wins": self.wins,
            "losses": self.losses,
            "total_runs": self.total_runs,
            "win_rate": self.win_rate,
            "avg_score": self.avg_score,
            "accuracy_weight": self.accuracy_weight,
            "real_conversion_rate": self.real_conversion_rate,
            "real_dispatches": self._real_dispatches,
        }


# ── AGENT POOL ───────────────────────────────────────────────────────
class AgentPool:
    """Manages the 10 competing agents, ensemble runs, and learning."""

    POOL_SIZE = 10

    def __init__(self):
        self.agents: List[CompetitorAgent] = []
        # Shared HTTP client with connection pool — avoids creating 15+ separate clients
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._init_pool()

    async def close(self):
        """Clean up shared HTTP client."""
        await self._client.aclose()

    def _init_pool(self):
        """Create 10 agents with varied temperatures and unique framings."""
        temps = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14]
        for i in range(self.POOL_SIZE):
            framing = AGENT_FRAMINGS[i] if i < len(AGENT_FRAMINGS) else AGENT_FRAMINGS[i % len(AGENT_FRAMINGS)]
            self.agents.append(CompetitorAgent(
                agent_id=i + 1,
                temperature=temps[i] if i < len(temps) else 0.4,
                framing=framing,
            ))

    async def ensemble_score(self, lead: Dict, market_context: Optional[Dict] = None) -> List[Dict]:
        """Run all 10 agents in parallel on the same lead. Returns 10 scored outputs."""
        tasks = []
        for agent in self.agents:
            tasks.append(self._agent_score(agent, lead, market_context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs = []
        for i, result in enumerate(results):
            agent = self.agents[i]
            if isinstance(result, Exception):
                outputs.append({
                    "agent_id": agent.id,
                    "quality_score": 50,
                    "reasoning": f"Error: {str(result)}",
                    "recommended_action": "skip",
                    "temperature": agent.temperature,
                    "_error": str(result),
                })
            else:
                result["agent_id"] = agent.id
                result["temperature"] = agent.temperature
                outputs.append(result)

        return outputs

    async def ensemble_critique(self, outputs: List[Dict], lead: Dict) -> List[Dict]:
        """Phase 1.5: Round-robin critique — Agent i critiques Agent (i+1)%10."""
        out_map = {o.get("agent_id"): o for o in outputs}
        tasks = []
        for i in range(self.POOL_SIZE):
            critic = self.agents[i]
            target_id = self.agents[(i + 1) % self.POOL_SIZE].id
            target_out = out_map.get(target_id, {})
            tasks.append(self._agent_critique(critic, target_out, lead, target_id))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        critiques = []
        for i, res in enumerate(results):
            critic_id = self.agents[i].id
            target_id = self.agents[(i + 1) % self.POOL_SIZE].id
            if isinstance(res, Exception):
                critiques.append({"critic_id": critic_id, "target_id": target_id,
                                   "critique_text": str(res), "severity": 0,
                                   "suggested_adjustment": 0.0, "agrees": True})
            else:
                res["critic_id"] = critic_id
                res["target_id"] = target_id
                critiques.append(res)
        return critiques

    async def _agent_critique(self, critic: CompetitorAgent, target_out: Dict,
                               lead: Dict, target_id: int) -> Dict:
        """One agent critiques another's score via Ollama. Compact, fast."""
        system = f"""{critic.framing}
Critique the target agent's score from YOUR perspective. Return ONLY compact JSON:
{{"critique_text":"brief","severity":1-10,"suggested_adjustment":float,"agrees":bool}}"""
        prompt = (
            f"L:{lead.get('address', lead.get('name', '?'))[:60]}|"
            f"C:{lead.get('city', 'N/A')}|U:{lead.get('urgency_score', 'N/A')}|"
            f"TargetAgent:{target_id} Score:{target_out.get('quality_score', '?')} "
            f"Action:{target_out.get('recommended_action', '?')} "
            f"Reason:{target_out.get('reasoning', '?')[:120]}|Critique. JSON only."
        )
        try:
            r = await self._client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": critic.temperature, "num_predict": 150},
                },
            )
            r.raise_for_status()
            return _parse_json(r.json().get("message", {}).get("content", "{}"))
        except Exception as e:
            return {"critique_text": str(e), "severity": 0,
                    "suggested_adjustment": 0.0, "agrees": True}

    async def _agent_score(self, agent: CompetitorAgent, lead: Dict, context: Optional[Dict] = None) -> Dict:
        """One agent scores the lead via Ollama. Uses shared client for speed."""
        system = f"""{agent.framing}
Return ONLY a compact JSON object (no markdown, no extra text):
{{"qs":0-100,"r":"brief reason","a":"dispatch"|"skip"|"hold","m":float,"rf":[],"is":0-100}}
qs=quality_score, r=reasoning, a=recommended_action, m=margin_estimate, rf=risk_flags, is=intent_score"""

        prompt_parts = [
            f"L:{lead.get('address', lead.get('name', 'unknown'))[:60]}",
            f"P:{lead.get('phone', 'N/A')}",
            f"C:{lead.get('city', lead.get('metro', 'N/A'))}",
            f"D:{lead.get('damage_severity', 'N/A')}",
            f"U:{lead.get('urgency_score', 'N/A')}",
            f"S:{lead.get('status', 'N/A')}",
            f"SRC:{lead.get('source', 'N/A')}",
        ]
        meta = lead.get("meta", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if meta:
            prompt_parts.append(f"M:{json.dumps(meta)[:200]}")
        if context:
            prompt_parts.append(f"CTX:{json.dumps(context)[:200]}")

        prompt = "|".join(prompt_parts) + "\nScore. JSON only."

        try:
            r = await self._client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/chat",
                json={
                    "model": "llama3.2:3b",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": agent.temperature, "num_predict": 200},
                },
            )
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "{}")
            parsed = _parse_json(raw)
            # Normalize short keys to full keys for downstream compatibility
            if "qs" in parsed and "quality_score" not in parsed:
                parsed["quality_score"] = parsed.pop("qs")
            if "r" in parsed and "reasoning" not in parsed:
                parsed["reasoning"] = parsed.pop("r")
            if "a" in parsed and "recommended_action" not in parsed:
                parsed["recommended_action"] = parsed.pop("a")
            if "m" in parsed and "margin_estimate" not in parsed:
                parsed["margin_estimate"] = parsed.pop("m")
            if "rf" in parsed and "risk_flags" not in parsed:
                parsed["risk_flags"] = parsed.pop("rf")
            if "is" in parsed and "intent_score" not in parsed:
                parsed["intent_score"] = parsed.pop("is")
            return parsed
        except Exception as e:
            return {"_error": str(e), "quality_score": 50, "recommended_action": "skip"}


# ── 5-ROLE VOTING PANEL ──────────────────────────────────────────────
# These are the JURY that reviews all 10 agent outputs and picks the winner.

PANEL_SYSTEMS = {
    "cfo": """You are the CFO. Review 10 agent outputs for the same lead. Score each output 0-100 based on:
- Margin realism: does the margin estimate make sense?
- Risk management: are risk flags properly identified?
- Financial soundness: would this dispatch protect the company's bottom line?
Return ONLY: {"scores": {"agent_1": 75, "agent_2": 60, ...}, "reasoning": "..."}""",

    "growth_coach": """You are the Growth Coach. Review 10 agent outputs for the same lead. Score each output 0-100 based on:
- Pipeline velocity: does this agent push high-intent leads through?
- Action bias: does the agent make a clear decision or waffle?
- Volume awareness: does the agent consider pipeline capacity?
Return ONLY: {"scores": {"agent_1": 75, "agent_2": 60, ...}, "reasoning": "..."}""",

    "strategy_expert": """You are the Strategy Expert. Review 10 agent outputs for the same lead. Score each output 0-100 based on:
- Market awareness: does the agent consider geography/seasonality/trends?
- Niche fit: does the agent recognize cross-niche opportunities?
- Pivot intelligence: could this lead open a new market angle?
Return ONLY: {"scores": {"agent_1": 75, "agent_2": 60, ...}, "reasoning": "..."}""",

    "brand_purist": """You are the Brand Purist. Review 10 agent outputs for the same lead. Score each output 0-100 based on:
- Authenticity: does the agent's reasoning feel premium or spammy?
- Quality filter: would this dispatch reflect well on the Empire brand?
- Brand guard: does the agent flag anything that could hurt our reputation?
Return ONLY: {"scores": {"agent_1": 75, "agent_2": 60, ...}, "reasoning": "..."}""",

    "judge": """You are the AGI Judge — FINAL ARBITER. Review the scores from the CFO, Growth Coach,
Strategy Expert, and Brand Purist for all 10 agents. The Purist carries the MOST weight.

Return the FINAL consensus score for each agent (0-100) and declare the winner.
Return ONLY: {"scores": {"agent_1": 80, ...}, "winner": best_agent_id, "winner_score": 85, "verdict": "DISPATCH"|"REJECT", "reasoning": "..."}""",

    "hybrid": """You are the HYBRID SYNTHESIZER — the final weighted blend of all 5 panel perspectives.

You receive the 5 panel member votes (CFO, Growth Coach, Strategy Expert, Brand Purist, AGI Judge)
and all 10 agent outputs + critiques.

Your job: produce the FINAL weighted blend. Weights:
- Brand Purist: 30% (quality & reputation guard)
- AGI Judge: 25% (final arbiter judgment)
- CFO: 15% (financial soundness)
- Growth Coach: 15% (pipeline velocity)
- Strategy Expert: 15% (market awareness)

For each agent, compute: final_score = sum(panel_member_score * weight) for all 5 members.
If any panel member is missing/invalid for an agent, re-weight remaining members proportionally.

Then declare ONE winner (highest score) and ONE verdict:
- DISPATCH if winner_score >= 80
- REJECT otherwise

Return ONLY JSON:
{"scores": {"agent_1": 82.5, ...}, "winner": best_agent_id, "winner_score": 85.0,
 "verdict": "DISPATCH"|"REJECT", "reasoning": "synthesized explanation referencing the 5 perspectives..."}""",
}


def _build_panel_prompt(lead: Dict, outputs: List[Dict], critiques: Optional[List[Dict]] = None) -> str:
    """Build the prompt showing all 10 agent outputs + critiques for panel review."""
    lines = [
        f"Lead: {lead.get('address', lead.get('name', '?'))} · {lead.get('city', '?')}",
        f"Lead ID: {lead.get('id', 'N/A')}",
        "",
        "─── 10 AGENT OUTPUTS + CRITIQUES ───",
    ]
    crit_map = {}
    if critiques:
        crit_map = {c.get("target_id"): c for c in critiques}
    for out in outputs:
        aid = out.get("agent_id", "?")
        c = crit_map.get(aid, {})
        crit_info = ""
        if c:
            crit_info = (
                f" [CRITIQUED by Agent{c.get('critic_id')}: "
                f"agrees={c.get('agrees')}, severity={c.get('severity')}/10, "
                f"adj={c.get('suggested_adjustment')}, note:{c.get('critique_text', '')[:80]}]"
            )
        lines.append(
            f"Agent {aid} (temp={out.get('temperature', '?')}): "
            f"score={out.get('quality_score', '?')} "
            f"action={out.get('recommended_action', '?')} "
            f"margin={out.get('margin_estimate', '?')} "
            f"risks={out.get('risk_flags', [])} "
            f"reasoning: {out.get('reasoning', '?')[:120]}"
            f"{crit_info}"
        )
    lines.append("\nScore all 10 agents considering the critiques. Return JSON only.")
    return "\n".join(lines)


def _build_hybrid_prompt(lead: Dict, outputs: List[Dict], panel_votes: Dict, critiques: Optional[List[Dict]] = None) -> str:
    """Build the prompt for the hybrid synthesizer — includes all 5 panel votes."""
    lines = [
        f"Lead: {lead.get('address', lead.get('name', '?'))} · {lead.get('city', '?')}",
        f"Lead ID: {lead.get('id', 'N/A')}",
        "",
        "─── 10 AGENT OUTPUTS ───",
    ]
    for out in outputs:
        lines.append(
            f"Agent {out.get('agent_id', '?')} (temp={out.get('temperature', '?')}): "
            f"score={out.get('quality_score', '?')} "
            f"action={out.get('recommended_action', '?')} "
            f"margin={out.get('margin_estimate', '?')} "
            f"risks={out.get('risk_flags', [])}"
        )
    
    lines.append("")
    lines.append("─── 5 PANEL MEMBER VOTES ───")
    for role in ["cfo", "growth_coach", "strategy_expert", "brand_purist", "judge"]:
        pv = panel_votes.get(role, {})
        if isinstance(pv, dict):
            scores = pv.get("scores", {})
            reasoning = pv.get("reasoning", "")[:100]
            lines.append(f"{role.upper()}: scores={scores} | reasoning: {reasoning}")
        else:
            lines.append(f"{role.upper()}: NO VOTE")
    
    if critiques:
        lines.append("")
        lines.append("─── CRITIQUE ROUND ───")
        for c in critiques:
            lines.append(
                f"Agent{c.get('critic_id')}→Agent{c.get('target_id')}: "
                f"severity={c.get('severity')}/10 agrees={c.get('agrees')} "
                f"adj={c.get('suggested_adjustment')} | {c.get('critique_text', '')[:80]}"
            )
    
    lines.append("\nCompute the FINAL weighted blend (Purist 30%, Judge 25%, CFO/Growth/Strategy 15% each).")
    lines.append("Return JSON only with scores, winner, winner_score, verdict, reasoning.")
    return "\n".join(lines)


# Module-level shared client for panel member calls (eager-init for speed, no race)
_panel_client: Optional[httpx.AsyncClient] = None

def _init_panel_client():
    global _panel_client
    if _panel_client is None:
        _panel_client = httpx.AsyncClient(
            timeout=httpx.Timeout(40.0, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

def _get_panel_client() -> httpx.AsyncClient:
    global _panel_client
    if _panel_client is None or _panel_client.is_closed:
        _init_panel_client()
    return _panel_client


async def _call_panel_member(name: str, system: str, prompt: str) -> Dict:
    """Call Ollama for a single panel member's scoring. Uses shared client."""
    try:
        client = _get_panel_client()
        r = await client.post(
            f"{OLLAMA_URL.rstrip('/')}/api/chat",
            json={
                "model": "llama3.2:3b",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3, "num_predict": 350},
            },
        )
        r.raise_for_status()
        raw = r.json().get("message", {}).get("content", "{}")
        return _parse_json(raw)
    except Exception as e:
        log.error(f"[panel_court] {name} panel call failed: {e}")
        return {"_error": str(e), "scores": {}}


async def _run_voting_panel(lead: Dict, outputs: List[Dict], critiques: Optional[List[Dict]] = None, *, wisdom_fn: Optional[Awaitable[str]] = None) -> Dict:
    """Run all 5 panel members in parallel, then the hybrid synthesizer.

    Args:
        wisdom_fn: optional async callable returning the latest dream wisdom.
            When provided, injected by the caller (PanelCourt.get_latest_wisdom).
            When None, falls back to the module-level import (back-compat).
    """
    prompt = _build_panel_prompt(lead, outputs, critiques)
    # Inject dream wisdom context into the prompt
    try:
        fn = wisdom_fn if wisdom_fn is not None else _module_get_latest_wisdom
        wisdom = await fn() if fn else ""
        if wisdom:
            prompt = wisdom + "\n\n" + prompt
    except Exception:
        pass

    tasks = []
    for role in ["cfo", "growth_coach", "strategy_expert", "brand_purist", "judge"]:
        tasks.append(_call_panel_member(role, PANEL_SYSTEMS[role], prompt))

    cfo, growth, strategy, purist, judge = await asyncio.gather(*tasks)

    panel_votes = {
        "cfo": cfo,
        "growth_coach": growth,
        "strategy_expert": strategy,
        "brand_purist": purist,
        "judge": judge,
    }

    # ── Phase 2.5: Hybrid synthesizer ────────────────────────────
    hybrid = {}
    try:
        hybrid_prompt = _build_hybrid_prompt(lead, outputs, panel_votes, critiques)
        hybrid = await _call_panel_member("hybrid", PANEL_SYSTEMS["hybrid"], hybrid_prompt)
    except Exception as e:
        log.error(f"[panel_court] hybrid synthesizer failed: {e}")
        hybrid = {"_error": str(e), "scores": {}}

    panel_votes["hybrid"] = hybrid
    return panel_votes


def _compute_consensus(panel_votes: Dict, outputs: List[Dict]) -> Dict:
    """Compute the final consensus score from panel votes. Prefers hybrid blend if available."""
    # Try hybrid synthesizer first — it already computed the weighted blend
    hybrid = panel_votes.get("hybrid", {})
    if isinstance(hybrid, dict) and hybrid.get("scores") and not hybrid.get("_error"):
        hybrid_scores_raw = hybrid.get("scores", {})
        consensus = {}
        for key, score in hybrid_scores_raw.items():
            aid = _extract_agent_id(key)
            if aid is not None:
                try:
                    consensus[aid] = round(float(score), 1)
                except (TypeError, ValueError):
                    pass
        if consensus:
            winner_id = max(consensus, key=consensus.get)
            winner_score = consensus[winner_id]
            verdict = hybrid.get("verdict", "REJECT")
            if winner_score < 80:
                verdict = "REJECT"
            return {
                "per_agent_scores": consensus,
                "winner_agent_id": winner_id,
                "winner_score": winner_score,
                "verdict": verdict,
                "judge_reasoning": panel_votes.get("judge", {}).get("reasoning", ""),
                "hybrid_reasoning": hybrid.get("reasoning", ""),
            }

    # ── Fallback: mathematical weighted average ──────────────────
    panel_weights = {
        "cfo": 0.15,
        "growth_coach": 0.15,
        "strategy_expert": 0.15,
        "brand_purist": 0.30,
        "judge": 0.25,
    }

    agent_weighted_sum: Dict[int, float] = {}
    agent_weight_total: Dict[int, float] = {}

    for role, weight in panel_weights.items():
        votes = panel_votes.get(role, {})
        scores = votes.get("scores", {})
        if not isinstance(scores, dict):
            continue
        for key, score in scores.items():
            aid = _extract_agent_id(key)
            if aid is None:
                continue
            try:
                s = float(score)
            except (TypeError, ValueError):
                continue
            if aid not in agent_weighted_sum:
                agent_weighted_sum[aid] = 0.0
                agent_weight_total[aid] = 0.0
            agent_weighted_sum[aid] += s * weight
            agent_weight_total[aid] += weight

    consensus = {}
    for aid in agent_weighted_sum:
        total_w = agent_weight_total[aid]
        consensus[aid] = round(agent_weighted_sum[aid] / total_w, 1) if total_w > 0 else 0

    if consensus:
        winner_id = max(consensus, key=consensus.get)
        winner_score = consensus[winner_id]
    else:
        winner_id = 1
        winner_score = 50

    judge_out = panel_votes.get("judge", {})
    verdict = judge_out.get("verdict", "REJECT")
    if winner_score < 80:
        verdict = "REJECT"

    return {
        "per_agent_scores": consensus,
        "winner_agent_id": winner_id,
        "winner_score": winner_score,
        "verdict": verdict,
        "judge_reasoning": judge_out.get("reasoning", ""),
        "hybrid_reasoning": "",
    }


def _extract_agent_id(key: str) -> Optional[int]:
    """Extract agent number from various key formats: 'agent_1', 'Agent 1', '1'"""
    import re
    match = re.search(r"(\d+)", str(key))
    if match:
        aid = int(match.group(1))
        if 1 <= aid <= 10:
            return aid
    return None


def _parse_json(raw: str) -> Dict:
    """Parse JSON from LLM output, handling markdown fences."""
    clean = raw.strip()
    if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
    elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"_parse_error": True, "_raw": raw[:200]}


# ── PANEL COURT ORCHESTRATOR ─────────────────────────────────────────
class PanelCourt:
    """
    10-Agent Ensemble Voting System.

    Flow:
      1. AgentPool runs all 10 agents in parallel → 10 scored outputs
      2. 5-role voting panel reviews all 10 outputs → per-agent scores
      3. Consensus computed → highest-scoring agent wins
      4. Winner dispatched; 9 losers learn from winner's approach
    """

    SCORE_THRESHOLD = 80   # Minimum consensus score (0-100) to dispatch

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        live_broadcaster: Optional[Any] = None,
        get_latest_wisdom: Optional[Awaitable[str]] = None,
        sb: Optional["SupabaseClient"] = None,
    ):
        """
        Args:
            ollama_url: optional Ollama endpoint (defaults to OLLAMA_URL env var).
            live_broadcaster: optional broadcaster for WebSocket pool snapshots.
                When None, falls back to the module-level `live_broadcaster`
                import (back-compat). In EMPIRE_TESTING=1 mode, the module
                fallback is None and broadcasting is skipped.
            get_latest_wisdom: optional async callable returning the latest
                dream-loop wisdom string. When None, falls back to the
                module-level import (back-compat).
            sb: optional Supabase client. When provided, the court uses
                it directly for all DB operations (logging decisions,
                dispatches). When None, falls back to the lazy
                `_get_sb()` helper (back-compat).
        """
        self._url = (ollama_url or OLLAMA_URL).rstrip("/")
        self.pool = AgentPool()
        self.temperature_history: List[List[float]] = []
        self.stats: Dict[str, int] = {
            "ensemble_runs": 0,
            "dispatched": 0,
            "rejected": 0,
            "panel_errors": 0,
        }
        # Resolved dependencies: prefer injected, fall back to module-level.
        # In EMPIRE_TESTING=1 mode the module-level imports may be None.
        self.live_broadcaster = live_broadcaster if live_broadcaster is not None else _module_live_broadcaster
        self.get_latest_wisdom = get_latest_wisdom if get_latest_wisdom is not None else _module_get_latest_wisdom
        self.sb = sb  # may be None; methods fall back to _get_sb() if so

    async def run_ensemble(
        self, lead: Dict, market_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Full ensemble pipeline: 10 agents score → 5 panels vote → consensus → dispatch.
        Performance: shared HTTP clients, compact prompts, 25s agent timeout, parallel phases.
        """
        self.stats["ensemble_runs"] += 1

        # ── Phase 1: 10 agents score the lead in parallel ────────────
        log.info(f"[panel_court] ensemble run for lead {lead.get('id', '?')[:8]}")
        outputs = await self.pool.ensemble_score(lead, market_context)

        # ── Phase 1.5: Critique Round — each agent challenges another ─
        critiques = await self.pool.ensemble_critique(outputs, lead)

        # ── Phase 2: 5-role voting panel reviews all 10 outputs ──────
        try:
            panel_votes = await _run_voting_panel(lead, outputs, critiques, wisdom_fn=self.get_latest_wisdom)
        except Exception as e:
            log.error(f"[panel_court] voting panel failed: {e}")
            self.stats["panel_errors"] += 1
            panel_votes = {"judge": {"scores": {}, "verdict": "REJECT", "reasoning": str(e)}}

        # ── Phase 3: Compute consensus and pick winner ───────────────
        consensus = _compute_consensus(panel_votes, outputs)
        # Apply critique survival & exposure bonuses
        per_agent = consensus.get("per_agent_scores", {})
        for c in critiques:
            cid = c.get("critic_id")
            tid = c.get("target_id")
            sev = c.get("severity", 0)
            ts = per_agent.get(tid, 50)
            # Survival bonus: target survived critique with low severity or agreed
            if sev <= 4 and c.get("agrees", True):
                per_agent[tid] = min(100, per_agent.get(tid, 50) + 2.5)
            # Exposure bonus: critic identified a real flaw the target scored poorly on
            if sev >= 7 and ts < 70:
                per_agent[cid] = min(100, per_agent.get(cid, 50) + 3.0)
        # Apply accuracy_weight bonus: agents with proven real-world conversion get edge
        for aid in list(per_agent.keys()):
            if 1 <= aid <= 10:
                agent = self.pool.agents[aid - 1]
                per_agent[aid] = round(per_agent[aid] * agent.accuracy_weight, 1)
        # Re-pick winner with accuracy-adjusted scores
        if per_agent:
            winner_id = max(per_agent, key=per_agent.get)
            winner_score = per_agent[winner_id]
        else:
            winner_id = 1
            winner_score = 50
        consensus["per_agent_scores"] = per_agent
        consensus["winner_agent_id"] = winner_id
        consensus["winner_score"] = winner_score
        # Re-evaluate verdict with accuracy-adjusted winner score
        verdict = "DISPATCH" if winner_score >= self.SCORE_THRESHOLD else "REJECT"
        consensus["verdict"] = verdict

        # ── Phase 4: Learning loop — losers adapt toward winner ──────
        winner = self.pool.agents[winner_id - 1] if 1 <= winner_id <= 10 else None
        if winner:
            for agent in self.pool.agents:
                won = (agent.id == winner_id)
                agent.record_result(won, float(consensus.get("per_agent_scores", {}).get(agent.id, 50)))
                if not won:
                    agent.learn_from_winner(winner.temperature)
            # Snapshot temperature convergence after learning
            temps = [round(a.temperature, 3) for a in self.pool.agents]
            self.temperature_history.append(temps)
            if len(self.temperature_history) > 200:
                self.temperature_history = self.temperature_history[-200:]

        # ── Broadcast pool snapshot via WebSocket for real-time SPA orbital ──
        try:
            if self.live_broadcaster and hasattr(self.live_broadcaster, 'broadcast'):
                snapshot = self.pool_snapshot()
                await self.live_broadcaster.broadcast({
                    "type": "panel_court_pool",
                    "agents": snapshot["agents"],
                    "stats": snapshot["stats"],
                    "total_runs": snapshot["total_runs"],
                    "total_wins": snapshot["total_wins"],
                    "temperature_history": snapshot["temperature_history"],
                    "winner_agent_id": winner_id if winner else 0,
                    "consensus_score": winner_score,
                    "verdict": verdict,
                })
        except Exception:
            pass

        # ── Phase 5: Stats tracking ──────────────────────────────────
        if verdict == "DISPATCH":
            self.stats["dispatched"] += 1
        else:
            self.stats["rejected"] += 1

        # ── Build result ─────────────────────────────────────────────
        result = {
            "lead_id": lead.get("id", "unknown"),
            "lead_summary": f"{lead.get('address', lead.get('name', '?'))} · {lead.get('city', '?')}",
            "winner_agent_id": winner_id,
            "consensus_score": winner_score,
            "verdict": verdict,
            "per_agent_scores": consensus["per_agent_scores"],
            "agent_outputs": [
                {
                    "agent_id": o.get("agent_id"),
                    "quality_score": o.get("quality_score"),
                    "recommended_action": o.get("recommended_action"),
                    "temperature": o.get("temperature"),
                    "reasoning": (o.get("reasoning", "") or "")[:200],
                }
                for o in outputs
            ],
            "panel_votes": {
                k: v.get("scores", {}) for k, v in panel_votes.items() if isinstance(v, dict)
            },
            "judge_reasoning": consensus.get("judge_reasoning", ""),
            "hybrid_reasoning": consensus.get("hybrid_reasoning", ""),
            "agent_critiques": [
                {
                    "critic_id": c.get("critic_id"),
                    "target_id": c.get("target_id"),
                    "critique_text": (c.get("critique_text", "") or "")[:200],
                    "severity": c.get("severity", 0),
                    "suggested_adjustment": c.get("suggested_adjustment", 0),
                    "agrees": c.get("agrees", True),
                }
                for c in critiques
            ],
            "agent_pool": [a.to_dict() for a in self.pool.agents],
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        # ── Persist ──────────────────────────────────────────────────
        self._log_decision(result)

        return result

    def _log_decision(self, result: Dict) -> None:
        """Persist ensemble result to panel_court_decisions."""
        try:
            sb = self.sb if self.sb is not None else _get_sb()
            sb.table("panel_court_decisions").insert({
                "lead_id": result["lead_id"],
                "lead_summary": result["lead_summary"],
                "winner_agent_id": result["winner_agent_id"],
                "score": result["consensus_score"],
                "verdict": result["verdict"],
                "per_agent_scores": json.dumps(result["per_agent_scores"]),
                "agent_outputs": json.dumps(result["agent_outputs"], ensure_ascii=False),
                "panel_votes": json.dumps(result["panel_votes"]),
                "judge_reasoning": result.get("judge_reasoning", "")[:500],
                "hybrid_reasoning": result.get("hybrid_reasoning", "")[:800],
                "agent_critiques": json.dumps(result.get("agent_critiques", [])),
                "agent_pool_snapshot": json.dumps(result["agent_pool"]),
                "created_at": result["ts"],
            }).execute()
        except Exception as e:
            log.warning(f"[panel_court] db log failed (table may not exist yet): {e}")

    async def execute_dispatch(
        self, lead: Dict, buyer: Dict, result: Dict
    ) -> Dict[str, Any]:
        """Execute dispatch after the ensemble picks a winner."""
        sb = self.sb if self.sb is not None else _get_sb()
        try:
            r = sb.table("dispatches").insert({
                "lead_id": lead["id"],
                "status": "sent",
                "meta": json.dumps({
                    "source": "panel_court.ensemble",
                    "buyer_id": buyer.get("id"),
                    "buyer_name": buyer.get("name"),
                    "lead_phone": lead.get("phone"),
                    "lead_address": lead.get("address"),
                    "lead_city": lead.get("city"),
                    "panel_court_score": result["consensus_score"],
                    "panel_court_verdict": result["verdict"],
                    "winner_agent_id": result["winner_agent_id"],
                    "dispatched_at": datetime.now(timezone.utc).isoformat(),
                }),
            }).execute()

            if r.data:
                dispatch_id = r.data[0].get("id")
                log.info(
                    f"[panel_court] Agent #{result['winner_agent_id']} won ensemble "
                    f"(score={result['consensus_score']}) → dispatched {lead['id'][:8]}"
                )
                sb.table("radar_targets").update({
                    "status": "converted",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", lead["id"]).execute()
                return {"ok": True, "dispatch_id": dispatch_id}
        except Exception as e:
            log.error(f"[panel_court] execute_dispatch error: {e}")
            return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "no rows returned"}

    async def record_real_outcome(self, winner_agent_id: int, converted: bool) -> None:
        """
        Called after dispatch when a lead's real-world outcome is known.
        Feeds accuracy data back into the agent pool so agents that pick
        actually-converting leads get higher accuracy weights over time.
        """
        if 1 <= winner_agent_id <= 10:
            agent = self.pool.agents[winner_agent_id - 1]
            agent.record_real_outcome(converted)
            log.info(
                f"[panel_court] Agent #{winner_agent_id} real outcome: "
                f"{'converted' if converted else 'not converted'} "
                f"(accuracy_weight={agent.accuracy_weight})"
            )

    def pool_snapshot(self) -> Dict:
        """Return agent pool stats for the SPA."""
        return {
            "agents": [a.to_dict() for a in self.pool.agents],
            "stats": self.stats,
            "total_runs": sum(a.total_runs for a in self.pool.agents),
            "total_wins": sum(a.wins for a in self.pool.agents),
            "temperature_history": self.temperature_history,
        }


# ── CONVENIENCE WRAPPER ──────────────────────────────────────────────
_PANEL_COURT_SINGLETON: Optional[PanelCourt] = None

def _get_panel_court() -> PanelCourt:
    global _PANEL_COURT_SINGLETON
    if _PANEL_COURT_SINGLETON is None:
        _PANEL_COURT_SINGLETON = PanelCourt()
    return _PANEL_COURT_SINGLETON


async def panel_court_score_lead(lead: Dict, market_context: Optional[Dict] = None) -> Dict:
    """
    Score a lead through the 10-agent ensemble + 5-role voting panel.
    Returns a dict compatible with mesh_dispatcher's score_lead_quality() format.
    """
    pc = _get_panel_court()
    result = await pc.run_ensemble(lead, market_context)

    action = "dispatch" if result["verdict"] == "DISPATCH" else "skip"

    return {
        "quality_score": result["consensus_score"],
        "reasoning": result.get("hybrid_reasoning", result.get("judge_reasoning", result["verdict"])),
        "recommended_action": action,
        # Panel Court ensemble-specific fields
        "panel_court_score": result["consensus_score"],
        "panel_court_verdict": result["verdict"],
        "panel_court_winner_id": result["winner_agent_id"],
        "panel_court_agent_pool": result["agent_pool"],
        "panel_court_per_agent": result["per_agent_scores"],
    }


# ── STANDALONE CLI ───────────────────────────────────────────────────
async def run_once(lead_id: Optional[str] = None, dry_run: bool = False) -> Dict:
    """Test entry point: run full ensemble on one lead."""
    sb = _get_sb()
    pc = PanelCourt()

    if lead_id:
        r = sb.table("radar_targets").select("*").eq("id", lead_id).limit(1).execute()
        leads = r.data or []
    else:
        r = sb.table("radar_targets").select("*").eq("status", "active").not_.is_("phone", "null").limit(1).execute()
        leads = r.data or []

    if not leads:
        return {"error": "no leads found", "dry_run": dry_run}

    lead = leads[0]
    result = await pc.run_ensemble(lead)

    if not dry_run and result["verdict"] == "DISPATCH":
        buyers_r = sb.table("buyers").select("*").limit(1).execute()
        if buyers_r.data:
            await pc.execute_dispatch(lead, buyers_r.data[0], result)

    return {
        "lead_id": lead["id"],
        "lead_addr": lead.get("address", "?"),
        "winner_agent": result["winner_agent_id"],
        "score": result["consensus_score"],
        "verdict": result["verdict"],
        "dry_run": dry_run,
        "per_agent_scores": result["per_agent_scores"],
        "pool": pc.pool_snapshot(),
    }


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    lid = None
    for arg in sys.argv[1:]:
        if arg.startswith("--lead="):
            lid = arg.split("=", 1)[1]
    result = asyncio.run(run_once(lead_id=lid, dry_run=dry))
    print(json.dumps(result, indent=2, default=str))
