"""
EMPIRE V49 · BRAIN DECIDE
==========================
Go/No-Go scoring with reasoning. Replaces orchestrator's "accept all" placeholder.

Phase 9: Personality-aware decisions. When a BrainPersonality instance is
attached, the system prompt and temperature are adjusted per niche, and
confidence thresholds are personality-aware.
"""
import logging
from typing import Dict, Optional
from empire_ai_router import AIRouter
import os, sys
sys.path.insert(0, "/root/empire-v49")
try:
    from empire_dream import get_latest_wisdom
except ImportError:
    get_latest_wisdom = None

log = logging.getLogger("empire.brain.decide")

BRAIN_SYSTEM_PROMPT = """You are the decision engine for a B2B storm-damage lead-generation system.
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

    async def decide(
        self,
        target: Dict,
        alert_summary: Dict,
        memory_context: str = "",
        personality_niche: Optional[str] = None,
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

        # Resolve niche for personality
        niche = personality_niche or self._get_niche(target)

        memory_block = f"\n{memory_context}\n" if memory_context else ""

        # Phase 9: Build personality-adjusted system prompt
        system_prompt = BRAIN_SYSTEM_PROMPT
        temperature = 0.1
        go_fallback = "NO_GO"
        confidence_threshold = 0.6

        if self.personality is not None:
            system_prompt = self.personality.build_system_prompt(niche, base_prompt=BRAIN_SYSTEM_PROMPT)
            temperature = self.personality.recommended_temperature(niche)
            go_fallback = self.personality.go_fallback(niche)
            confidence_threshold = self.personality.confidence_threshold(niche)
            log.debug(
                f"[brain.decide] personality for {niche}: "
                f"persona={self.personality.personality_for_niche(niche).get('persona')} "
                f"temp={temperature} threshold={confidence_threshold}"
            )

        # Inject dream wisdom alongside memory context (computed BEFORE the f-string)
        dream_block = ""
        if get_latest_wisdom:
            try:
                dream_wisdom = await get_latest_wisdom()
                if dream_wisdom:
                    dream_block = "\n\n=== DREAM WISDOM (cross-system patterns) ===\n" + dream_wisdom
            except Exception:
                pass
        memory_block = (memory_block or "") + dream_block

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
{memory_block}
Decide: should we enroll this target in storm-strike outreach?
Return JSON only."""

        result = await self.router.generate_json(
            prompt=prompt,
            task="brain.decide",
            system=system_prompt,
            temperature=temperature,
            max_tokens=200,
            context={"target_name": name, "storm_event": alert_summary.get("event"),
                     "severity": alert_summary.get("severity"),
                     "niche": niche, "personality_prompted": self.personality is not None},
        )

        if "_error" in result:
            log.warning(f"[brain.decide] LLM failed for {name}: {result.get('_error')}")
            return {"decision": go_fallback, "confidence": 0.0, "reasoning": "brain unavailable",
                    "niche": niche, "personality": self.personality.personality_for_niche(niche).get("persona") if self.personality else "default"}

        decision = (result.get("decision") or go_fallback).upper()
        if decision not in ("GO", "NO_GO"):
            decision = go_fallback
        try:
            confidence = float(result.get("confidence", 0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        # Apply confidence threshold check (post-decision filter)
        # If confidence is below the threshold, override to NO_GO
        if decision == "GO" and confidence < confidence_threshold:
            log.info(
                f"[brain.decide] GO overridden to NO_GO for {name}: "
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
        }
