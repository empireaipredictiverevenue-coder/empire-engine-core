"""
EMPIRE V49 · EMAIL DRAFTER
===========================
Llama 3.1 8b writes per-storm-per-warehouse drafts.
Drafts land in email_drafts table with status='pending'.

Phase 9 Polish: Personality-aware drafting. When a BrainPersonality instance
is provided, the drafter adjusts its system prompt and temperature per niche
(same way BrainDecider does).
"""
import logging
from typing import Dict, Optional, Callable
from datetime import datetime, timezone

from empire_ai_router import AIRouter

log = logging.getLogger("empire.drafter")

DRAFTER_SYSTEM = """You are a senior B2B email copywriter for National Storm Hub, a service that connects
storm-damaged commercial properties with vetted repair contractors.

You draft brief, professional outreach emails to facility managers and operations leads.

STRICT RULES:
- Return ONLY valid JSON with keys: subject, body
- Body MUST be plain text, no HTML, no markdown
- Body MUST be under 120 words
- Body MUST mention the specific storm event + location
- Body MUST end with a clear single CTA (reply YES, or click to schedule)
- Tone: professional, urgent without panic, respectful of recipient's time
- NEVER promise specific damage amounts or insurance outcomes
- NEVER guarantee contractor availability
- NEVER claim affiliation with FEMA, NWS, government, or insurance providers
- Use second person ("your facility")
- No exclamation marks, no all-caps, no emoji
- Sign as "National Storm Hub Dispatch Team"
"""


class EmailDrafter:
    def __init__(self, router: AIRouter, get_db: Callable):
        self.router = router
        self._get_db = get_db
        # Optional Phase 9.5 personality engine for niche-adjusted tone
        self.personality = None

    async def draft_for_target(
        self,
        target: Dict,
        alert_summary: Dict,
        brain_decision: Dict,
        target_id: Optional[str] = None,
        strike_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Generate a draft, insert into email_drafts. Returns the draft row dict or None.
        Uses personality-adjusted system prompt if personality engine is wired.
        """
        name = target.get("warehouse_name") or "Facility"
        addr = target.get("address") or ""
        event = alert_summary.get("event") or "severe weather"
        area = alert_summary.get("area") or "your area"
        severity = alert_summary.get("severity") or "Severe"

        # Personality-adjusted system prompt + temperature
        system_prompt = DRAFTER_SYSTEM
        temperature = 0.5

        # Extract niche from brain_decision or target
        niche = brain_decision.get("niche", "") or target.get("niche", "__global__")
        if self.personality is not None and niche:
            try:
                system_prompt = self.personality.build_system_prompt(
                    niche, base_prompt=DRAFTER_SYSTEM
                )
                temperature = self.personality.recommended_temperature(niche)
                # Bump temperature slightly for creative drafting vs deterministic decisions
                temperature = min(1.0, temperature + 0.15)
                log.debug(
                    f"[drafter] personality-adjusted draft for {niche}: "
                    f"persona={self.personality.personality_for_niche(niche).get('persona')} "
                    f"temp={temperature}"
                )
            except Exception as e:
                log.debug(f"[drafter] personality adjustment skipped: {e}")

        prompt = f"""Draft an outreach email for this scenario:

BUSINESS: {name}
ADDRESS: {addr}
STORM EVENT: {event}
SEVERITY: {severity}
AFFECTED AREA: {area}

Brain rationale for outreach: {brain_decision.get("reasoning", "")}

Return JSON only, no preamble."""

        result = await self.router.generate_json(
            prompt=prompt,
            task="email.draft",
            system=system_prompt,
            temperature=temperature,
            max_tokens=500,
            context={
                "target": name,
                "storm": event,
                "severity": severity,
                "niche": niche,
                "personality_adjusted": self.personality is not None,
            },
        )

        if "_error" in result:
            log.warning(f"[drafter] LLM failed for {name}: {result.get('_error')}")
            return None

        subject = (result.get("subject") or "").strip()
        body = (result.get("body") or "").strip()
        if not subject or not body:
            log.warning(f"[drafter] empty subject/body for {name}")
            return None

        # Safety filters
        if len(body) > 2000:
            body = body[:2000]
        if any(banned in body.lower() for banned in ["fema", "government", "guarantee"]):
            log.warning(f"[drafter] banned phrase in body for {name}, dropping")
            return None

        to_email = target.get("email")
        if not to_email:
            return None

        try:
            db = self._get_db()
            row = {
                "target_id": target_id,
                "strike_id": strike_id,
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "storm_event": event,
                "storm_area": area,
                "brain_confidence": brain_decision.get("confidence"),
                "status": "pending",
                "meta": {
                    "target_name": name,
                    "target_addr": addr,
                    "severity": severity,
                    "model_used": "llama3.1:latest",
                    "personality_adjusted": self.personality is not None,
                    "niche": niche,
                },
            }
            r = db.table("email_drafts").insert(row).execute()
            saved = (r.data or [{}])[0]
            log.info(f"[drafter] draft {saved.get('id')} created for {name} -> {to_email}")
            return saved
        except Exception as e:
            log.error(f"[drafter] insert failed for {name}: {e}")
            return None
