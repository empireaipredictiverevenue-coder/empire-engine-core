"""
EMPIRE V49 · BRAIN DECIDE
==========================
Go/No-Go scoring with reasoning. Replaces orchestrator's "accept all" placeholder.

Phase 9: Personality-aware decisions. When a BrainPersonality instance is
attached, the system prompt and temperature are adjusted per niche, and
confidence thresholds are personality-aware.

Thinking Levels (Phase 10):
  - LOW:    Fast, minimal context, cheap. For simple/repetitive decisions.
            Uses small model, 0 retries, no memory/vault/trading context.
  - MEDIUM: Standard balanced processing with few-shot memory.
            Default behavior matching previous phase.
  - MAX:    Deep reasoning, full context, large model. For high-value leads,
            complex decisions, or novel situations. Injects vault knowledge,
            trading signals, memory, and dream wisdom.
"""
import logging
from enum import Enum
from typing import Dict, Optional
from empire_ai_router import AIRouter
import os, sys
sys.path.insert(0, "/root/empire-v49")
try:
    from empire_dream import get_latest_wisdom
except ImportError:
    get_latest_wisdom = None

log = logging.getLogger("empire.brain.decide")


# ═════════════════════════════════════════════════════════════════════════
# THINKING LEVELS — Control cognitive depth per decision
# ═════════════════════════════════════════════════════════════════════════

class ThinkingLevel(str, Enum):
    """Three tiers of brain cognitive effort.
    
    LOW:   Fast, cheap, minimal — for simple/repetitive decisions.
           No memory, no vault, no trading context. Small model, 0 retries.
           
    MEDIUM: Standard balanced processing with few-shot memory.
            Default behavior matching previous phase.
            
    MAX:   Deep reasoning with full context — for high-value leads or
           complex decisions. Large model, vault knowledge, trading signals,
           dream wisdom, more retries.
    """
    LOW = "low"
    MEDIUM = "medium"
    MAX = "max"


# Per-level configuration presets (can be overridden per niche)
THINKING_LEVEL_CONFIG = {
    ThinkingLevel.LOW: {
        "label": "Low",
        "description": "Fast, minimal context, cheap — for simple decisions",
        "model": None,  # Use task default (llama3.2:3b)
        "max_tokens": 100,
        "temperature": 0.05,
        "retries": 0,
        "include_memory": False,
        "include_vault": False,
        "include_trading_signals": False,
        "include_dream_wisdom": False,
        "decision_prompt": "Make a quick GO/NO-GO decision. Be concise. No analysis beyond the essentials.",
    },
    ThinkingLevel.MEDIUM: {
        "label": "Medium",
        "description": "Standard processing with few-shot memory — default",
        "model": None,  # Use task default
        "max_tokens": 200,
        "temperature": 0.10,
        "retries": 1,
        "include_memory": True,
        "include_vault": False,
        "include_trading_signals": False,
        "include_dream_wisdom": False,
        "decision_prompt": "Decide: should we enroll this target in outreach?",
    },
    ThinkingLevel.MAX: {
        "label": "Max",
        "description": "Deep reasoning with full context — for high-value leads",
        "model": None,  # Will use a larger model if available
        "max_tokens": 500,
        "temperature": 0.20,
        "retries": 2,
        "include_memory": True,
        "include_vault": True,
        "include_trading_signals": True,
        "include_dream_wisdom": True,
        "decision_prompt": "Analyze this lead thoroughly. Consider market conditions, past outcomes, and vault knowledge. Provide detailed reasoning.",
    },
}

BRAIN_SYSTEM_PROMPT = """You are the decision engine for the Empire AI autonomous revenue engine.
Given a storm alert and a target business, decide whether to enroll them in outreach.

Return ONLY valid JSON with these keys:
  - decision: "GO" or "NO_GO"
  - confidence: float 0.0-1.0
  - reasoning: one sentence explaining your decision
"""


class BrainDecider:
    def __init__(self, router: AIRouter):
        self.router = router
        # Optional Phase 9 personality engine (set by hub.py at startup)
        self.personality = None

    def _get_niche(self, target: Dict) -> str:
        """Extract niche from target's raw_tags or other metadata."""
        raw = target.get("raw_tags") or {}
        if isinstance(raw, dict):
            niche = raw.get("niche") or target.get("niche", "")
            if niche:
                return niche
        city = target.get("city", "") or ""
        state = target.get("state", "") or ""
        # Fallback: infer niche from type tags
        types = raw.get("types") if isinstance(raw, dict) else []
        if not isinstance(types, list):
            types = []
        type_str = " ".join(types).lower()
        if "warehouse" in type_str or "distribution" in type_str or "logistics" in type_str:
            return "Warehouse & Distribution"
        if "manufacturing" in type_str or "industrial" in type_str:
            return "Industrial"
        if "retail" in type_str or "commercial" in type_str:
            return "Commercial Property"
        return "Storm Damage Restoration"

    def resolve_thinking_level(
        self,
        niche: str,
        asset_value: float = 0.0,
        explicit: Optional[ThinkingLevel] = None,
    ) -> ThinkingLevel:
        """
        Resolve the thinking level for a decision.
        Resolution order:
          1. Explicit override (passed by caller)
          2. Personality-niche override (configured per niche in BrainPersonality)
          3. Asset-value auto-selection (high-value leads = MAX)
          4. Default: MEDIUM
        """
        if explicit is not None:
            return explicit

        # Check personality per-niche thinking level
        if self.personality:
            try:
                niche_level = self.personality.thinking_level_for_niche(niche)
                if niche_level:
                    return ThinkingLevel(niche_level)
            except Exception:
                pass

        # Auto-select based on lead value
        if asset_value >= 5_000_000:
            return ThinkingLevel.MAX
        elif asset_value >= 1_000_000:
            return ThinkingLevel.MAX

        return ThinkingLevel.MEDIUM

    async def decide(
        self,
        target: Dict,
        alert_summary: Dict,
        memory_context: str = "",
        personality_niche: Optional[str] = None,
        thinking_level: Optional[ThinkingLevel] = None,
        trading_context: str = "",
    ) -> Dict:
        name = target.get("warehouse_name") or target.get("name") or "Unknown"
        addr = target.get("address") or "no address"
        phone = target.get("phone") or "no phone"
        email = target.get("email") or "no email"
        website = target.get("website") or "no website"
        raw = target.get("raw_tags") or {}
        types = raw.get("types") if isinstance(raw, dict) else []
        if not isinstance(types, list):
            types = []
        asset_value = float(target.get("asset_value") or 0)

        # Resolve niche for personality
        niche = personality_niche or self._get_niche(target)

        # Resolve thinking level
        level = self.resolve_thinking_level(
            niche=niche,
            asset_value=asset_value,
            explicit=thinking_level,
        )
        level_config = THINKING_LEVEL_CONFIG.get(level, THINKING_LEVEL_CONFIG[ThinkingLevel.MEDIUM])

        # Phase 9: Build personality-adjusted system prompt
        system_prompt = BRAIN_SYSTEM_PROMPT
        temperature = level_config["temperature"]
        go_fallback = "NO_GO"
        confidence_threshold = 0.6

        if self.personality is not None:
            system_prompt = self.personality.build_system_prompt(niche, base_prompt=BRAIN_SYSTEM_PROMPT)
            # Blend: personality sets base temperature, level adjusts final
            persona_temp = self.personality.recommended_temperature(niche)
            temperature = (persona_temp + level_config["temperature"]) / 2
            go_fallback = self.personality.go_fallback(niche)
            confidence_threshold = self.personality.confidence_threshold(niche)

        # ── Build context blocks based on thinking level ──────────────
        context_blocks = []

        # Memory context
        memory_block = ""
        if level_config["include_memory"] and memory_context:
            memory_block = f"\n{memory_context}\n"
            context_blocks.append(memory_block)

        # Vault knowledge
        vault_block = ""
        if level_config["include_vault"]:
            try:
                from empire_skills_init import build_brain_context
                vault_context = build_brain_context()
                if vault_context:
                    vault_block = f"\n=== BRAIN VAULT KNOWLEDGE ===\n{vault_context[:2000]}\n"
                    context_blocks.append(vault_block)
            except Exception:
                pass

        # Trading signals
        trading_block = ""
        if level_config["include_trading_signals"] and trading_context:
            trading_block = f"\n=== MARKET INTELLIGENCE ===\n{trading_context}\n"
            context_blocks.append(trading_block)

        # Dream wisdom
        dream_block = ""
        if level_config["include_dream_wisdom"] and get_latest_wisdom:
            try:
                dream_wisdom = await get_latest_wisdom()
                if dream_wisdom:
                    dream_block = "\n\n=== DREAM WISDOM (cross-system patterns) ===\n" + dream_wisdom[:1000]
                    context_blocks.append(dream_block)
            except Exception:
                pass

        combined_context = "\n".join(context_blocks)

        # ── Build the decision prompt ────────────────────────────────
        prompt = f"""STORM:
  Event: {alert_summary.get("event")}
  Severity: {alert_summary.get("severity")}
  Urgency: {alert_summary.get("urgency")}
  Area: {alert_summary.get("area")}

TARGET:
  Name: {name}
  Address: {addr}
  Phone: {phone}
  Email: {email}
  Website: {website}
  Type tags: {", ".join(types) if types else "unknown"}
  Asset value: ${asset_value:,.0f}
{combined_context}
{level_config['decision_prompt']}
Return JSON only."""

        result = await self.router.generate_json(
            prompt=prompt,
            task="brain.decide",
            system=system_prompt,
            temperature=temperature,
            max_tokens=level_config["max_tokens"],
            retries=level_config["retries"],
            context={"target_name": name, "storm_event": alert_summary.get("event"),
                     "severity": alert_summary.get("severity"),
                     "niche": niche, "personality_prompted": self.personality is not None,
                     "thinking_level": level.value},
        )

        if "_error" in result:
            log.warning(f"[brain.decide] LLM failed for {name} (level={level.value}): {result.get('_error')}")
            return {"decision": go_fallback, "confidence": 0.0, "reasoning": "brain unavailable",
                    "niche": niche, "personality": self.personality.personality_for_niche(niche).get("persona") if self.personality else "default",
                    "thinking_level": level.value}

        decision = (result.get("decision") or go_fallback).upper()
        if decision not in ("GO", "NO_GO"):
            decision = go_fallback
        try:
            confidence = float(result.get("confidence", 0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        # Apply confidence threshold check (post-decision filter)
        if decision == "GO" and confidence < confidence_threshold:
            log.info(
                f"[brain.decide] GO overridden to NO_GO for {name} (level={level.value}): "
                f"confidence {confidence:.2f} < threshold {confidence_threshold:.2f}"
            )
            decision = "NO_GO"
            reasoning = result.get("reasoning", "") + (
                f" [confidence {confidence:.2f} below {self.personality.personality_for_niche(niche).get('persona','default')} threshold {confidence_threshold:.2f}]"
            )
        else:
            reasoning = result.get("reasoning", "no reasoning")

        return {
            "decision": decision,
            "confidence": confidence,
            "reasoning": reasoning,
            "niche": niche,
            "personality": self.personality.personality_for_niche(niche).get("persona") if self.personality else "default",
            "confidence_threshold": confidence_threshold,
            "thinking_level": level.value,
            "max_tokens": level_config["max_tokens"],
            "temperature": round(temperature, 3),
            "retries": level_config["retries"],
        }
