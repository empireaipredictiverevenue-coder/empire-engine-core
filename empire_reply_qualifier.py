"""
EMPIRE V49 · REPLY QUALIFIER
=============================
Classifies inbound email replies into actionable categories.
"""
import logging
from typing import Dict
from empire_ai_router import AIRouter

log = logging.getLogger("empire.reply.qualifier")

QUALIFIER_SYSTEM = """You classify B2B email replies to outreach about storm damage repair.

Return ONLY JSON with keys:
  - intent: one of "interested", "question", "not_now", "wrong_person", "unsubscribe", "spam"
  - confidence: 0.0-1.0
  - summary: one sentence
  - next_action: one of "dispatch_contractor", "ask_followup", "remove_from_list", "no_action"

Rules:
  - "unsubscribe" → next_action MUST be "remove_from_list"
  - "interested" with damage details → "dispatch_contractor"
  - Vague interest → "ask_followup"
  - Hostile or "stop emailing" → "remove_from_list"
"""


class ReplyQualifier:
    def __init__(self, router: AIRouter):
        self.router = router

    async def qualify(self, reply_text: str, original_subject: str = "") -> Dict:
        if not reply_text or not reply_text.strip():
            return {"intent": "spam", "confidence": 0.0, "summary": "empty reply",
                    "next_action": "no_action"}

        body = reply_text[:4000]
        prompt = f"""ORIGINAL SUBJECT: {original_subject}

REPLY:
{body}

Classify and return JSON only."""

        result = await self.router.generate_json(
            prompt=prompt,
            task="reply.qualify",
            system=QUALIFIER_SYSTEM,
            temperature=0.1,
            max_tokens=200,
        )
        if "_error" in result:
            return {"intent": "question", "confidence": 0.0,
                    "summary": "qualifier unavailable", "next_action": "no_action"}
        return {
            "intent": (result.get("intent") or "question").lower(),
            "confidence": float(result.get("confidence", 0.5) or 0.5),
            "summary": result.get("summary", ""),
            "next_action": (result.get("next_action") or "no_action").lower(),
        }
