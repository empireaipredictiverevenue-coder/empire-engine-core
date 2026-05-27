"""
EMPIRE V49 · BRAIN DECIDE
==========================
Go/No-Go scoring with reasoning. Replaces orchestrator's "accept all" placeholder.
"""
import logging
from typing import Dict
from empire_ai_router import AIRouter

log = logging.getLogger("empire.brain.decide")

BRAIN_SYSTEM_PROMPT = """You are the decision engine for a B2B storm-damage lead-generation system.
Given a storm alert and a target business, decide whether to enroll them in outreach.

Return ONLY valid JSON with these keys:
  - decision: "GO" or "NO_GO"
  - confidence: float 0.0-1.0
  - reasoning: one sentence explaining your decision

Criteria for GO:
  - Storm severity is Severe or Extreme
  - Target is commercial/industrial (warehouse, distribution, logistics, manufacturing, retail)
  - At least one contact channel (phone OR email OR website)
  - Geographic match to storm area

Criteria for NO_GO:
  - Residential property, school, government facility, place of worship
  - Storm is Minor/Moderate severity
  - No contact channels at all
  - Already-processed dup

Be conservative — when in doubt, NO_GO. Reputation > revenue per call.
"""


class BrainDecider:
    def __init__(self, router: AIRouter):
        self.router = router

    async def decide(self, target: Dict, alert_summary: Dict) -> Dict:
        name = target.get("warehouse_name") or "Unknown"
        addr = target.get("address") or "no address"
        phone = target.get("phone") or "no phone"
        email = target.get("email") or "no email"
        website = target.get("website") or "no website"
        raw = target.get("raw_tags") or {}
        types = raw.get("types") if isinstance(raw, dict) else []
        if not isinstance(types, list):
            types = []

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

Decide: should we enroll this target in storm-strike outreach?
Return JSON only."""

        result = await self.router.generate_json(
            prompt=prompt,
            task="brain.decide",
            system=BRAIN_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=200,
            context={"target_name": name, "storm_event": alert_summary.get("event"),
                     "severity": alert_summary.get("severity")},
        )

        if "_error" in result:
            log.warning(f"[brain.decide] LLM failed for {name}: {result.get('_error')}")
            return {"decision": "NO_GO", "confidence": 0.0, "reasoning": "brain unavailable"}

        decision = (result.get("decision") or "NO_GO").upper()
        if decision not in ("GO", "NO_GO"):
            decision = "NO_GO"
        try:
            confidence = float(result.get("confidence", 0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5
        return {
            "decision": decision,
            "confidence": confidence,
            "reasoning": result.get("reasoning", "no reasoning"),
        }
