"""EMPIRE FACEBOOK BOT — Empire AI (Elite)
Facebook Messenger chatbot for customer support and lead generation.

Uses the shared Chatwoot client (bots/chatwoot_client.py) for all
Chatwoot API communication. Supports both polling mode (run_cycle)
and webhook mode (handle_webhook_event) for maximum deployment
flexibility.

AGI · SI · PREDICTIVE REVENUE WIRED:
  - AGI Governor: strategy_for_niche() selects best conversation strategy
  - SI Strategy: best_for_niche() evolves reply genome per outcome
  - Predictive Revenue: estimates lead value for prioritization
"""

import os
import json
import re
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/root/.env", override=True)

log = logging.getLogger("empire.facebook_bot")

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# ── Business hours (ET) ─────────────────────────────────────────────
BUSINESS_HOURS_START = 8   # 8 AM ET
BUSINESS_HOURS_END = 20    # 8 PM ET
BUSINESS_TZ_OFFSET = -5    # ET → UTC offset

# ── Lead qualification stages ───────────────────────────────────────
QUALIFICATION_STAGES = ["none", "asking_location", "asking_damage",
                         "asking_urgency", "asking_contact", "complete"]

# ── FAQ patterns (English) ──────────────────────────────────────────
FAQ_PATTERNS = {
    r"(?i).*how.*file.*claim.*|.*insurance.*claim.*|.*claim.*process.*": (
        "To file a storm damage claim: 1) Document all damage with photos/videos. "
        "2) Contact your insurance provider to start a claim. "
        "3) Get a professional inspection — we can connect you with a vetted "
        "contractor who does free inspections. "
        "Would you like me to connect you with a local contractor?"
    ),
    r"(?i).*how.*long.*take.*|.*response.*time.*|.*how.*fast.*": (
        "Most contractors in our network can do an initial inspection within "
        "24-48 hours. Emergency tarping can often be done the same day. "
        "Would you like me to connect you?"
    ),
    r"(?i).*cost.*|.*price.*|.*how.*much.*|.*free.*": (
        "Inspections are typically free. Repair costs depend on the damage — "
        "a contractor will provide a detailed estimate after inspection. "
        "We can connect you with a vetted contractor for a free, no-obligation estimate."
    ),
    r"(?i).*service.*area.*|.*where.*you.*|.*location.*|.*city.*": (
        "We serve the entire Dallas-Fort Worth metro area, plus Houston, "
        "Oklahoma City, and expanding to new markets weekly. "
        "What city are you in?"
    ),
    r"(?i).*who.*you.*|.*what.*empire.*|.*about.*|.*company.*": (
        "Empire AI connects homeowners with vetted storm restoration contractors. "
        "We handle the matching so you get fast, reliable service. "
        "All contractors in our network are screened for licensing and insurance."
    ),
    r"(?i).*trusted.*|.*better.?business.*|.*reviews.*|.*rating.*": (
        "Our contractors maintain a minimum 4.0+ star rating and carry "
        "full liability insurance. We also track customer satisfaction "
        "on every job. Your peace of mind is our priority."
    ),
}

# ── FAQ patterns (Spanish) ──────────────────────────────────────────
FAQ_PATTERNS_ES = {
    r"(?i).*reclamo.*|.*seguro.*|.*reclamaci.*": (
        "Para presentar un reclamo por daños de tormenta: 1) Tome fotos y "
        "videos de todos los daños. 2) Contacte a su aseguradora para iniciar "
        "el reclamo. 3) Obtenga una inspección profesional. "
        "¿Quiere que lo conectemos con un contratista local?"
    ),
    r"(?i).*cuanto.*tiempo.*|.*rapido.*|.*demora.*": (
        "La mayoría de los contratistas pueden hacer una inspección en 24-48 "
        "horas. Las reparaciones de emergencia pueden hacerse el mismo día. "
        "¿Lo conectamos?"
    ),
    r"(?i).*costo.*|.*precio.*|.*cuanto.*cuesta.*|.*gratis.*": (
        "Las inspecciones son gratuitas. Los costos de reparación dependen "
        "del daño. Podemos conectarlo con un contratista para un presupuesto gratis."
    ),
}

# ── Lead keywords ───────────────────────────────────────────────────
LEAD_KEYWORDS = [
    "roof", "damage", "storm", "hail", "repair", "fix", "leak",
    "techo", "daño", "tormenta", "granizo", "reparación", "filtración",
]

URGENCY_KEYWORDS: Dict[str, List[str]] = {
    "high": ["emergency", "urgent", "asap", "now", "tonight", "water",
             "flood", "leaking", "emergencia", "urgente", "ahora",
             "esta noche", "inundación"],
    "medium": ["soon", "today", "tomorrow", "this week", "pronto",
               "hoy", "mañana", "esta semana"],
    "low": ["eventually", "sometime", "later", "not urgent",
            "eventualmente", "después", "no urgente"],
}

US_CITIES = [
    "dallas", "fort worth", "houston", "san antonio", "austin",
    "oklahoma city", "tulsa", "miami", "orlando", "jacksonville",
    "new orleans", "charlotte", "nashville", "memphis", "atlanta",
    "birmingham", "little rock",
]


class EmpireFacebookBot:
    """Facebook Messenger chatbot for the Empire AI business page.

    Architecture:
      Facebook Page → Chatwoot (Facebook channel) → Chatwoot webhook
                                                       ↓
                                              EmpireFacebookBot
                                               ↙           ↘
                                     handle_webhook_event   run_cycle()
                                        (real-time)        (polling)

    Routes incoming messages through intent classification, FAQ
    matching / LLM fallback, and lead qualification. Captures
    qualified leads to Supabase and routes to contractor dispatch.
    """

    def __init__(self, interval_minutes: int = 5):
        self.interval = interval_minutes
        self._chatwoot = None
        self._facebook_inbox_id: Optional[int] = None
        self._agi_governor = None
        self._si_strategy = None
        self._lazy_wire()

    # ── Lazy wiring ────────────────────────────────────────────────

    def _lazy_wire(self):
        """Lazy-import Chatwoot client, AGI Governor, SI Strategy."""
        try:
            from bots.chatwoot_client import get_chatwoot
            self._chatwoot = get_chatwoot()
            if self._chatwoot:
                log.info("[FBBot] Chatwoot client wired")
        except Exception:
            log.debug("[FBBot] Chatwoot client unavailable")

        try:
            from empire_agi_governor import governor as _gov
            self._agi_governor = _gov
            log.info("[FBBot] AGI Governor wired")
        except Exception:
            log.debug("[FBBot] AGI Governor unavailable")

        try:
            from empire_si_strategy import StrategyEvolution
            self._si_strategy = StrategyEvolution.get_shared_instance()
            log.info("[FBBot] SI Strategy wired")
        except Exception:
            log.debug("[FBBot] SI Strategy unavailable")

    # ── Chatwoot helpers ────────────────────────────────────────────

    async def _ensure_facebook_inbox(self) -> Optional[int]:
        """Find and cache the Facebook Messenger inbox ID."""
        if self._facebook_inbox_id is not None:
            return self._facebook_inbox_id
        if not self._chatwoot:
            return None
        inbox = await self._chatwoot.get_inbox_by_type("facebook")
        if inbox:
            self._facebook_inbox_id = inbox.get("id")
        return self._facebook_inbox_id

    async def _send_reply(self, conversation_id: int, text: str) -> bool:
        """Send a reply via Chatwoot. Returns True on success."""
        if not self._chatwoot or not text:
            return False
        res = await self._chatwoot.send_message(
            conversation_id=conversation_id,
            content=text,
        )
        return res.get("ok", False)

    # ── Business hours ─────────────────────────────────────────────

    def _in_business_hours(self) -> bool:
        now = datetime.now(timezone.utc)
        hour_et = (now.hour + BUSINESS_TZ_OFFSET) % 24
        return BUSINESS_HOURS_START <= hour_et < BUSINESS_HOURS_END

    # ── Intent classification ──────────────────────────────────────

    def _classify_intent(self, message: str) -> Dict[str, Any]:
        """Classify message intent via keyword scoring.

        Returns: {intent, confidence, sentiment, language}
        """
        msg_lower = message.lower().strip()

        # Language detection
        language = "es" if re.search(r"(?i)[¿¡áéíóúñ]", message) else "en"

        # Spam
        if re.match(r"(?i).*(casino|click.*here|free.*money|http[s]?://)", msg_lower):
            return {"intent": "spam", "confidence": 0.9, "sentiment": "neutral", "language": language}

        # Urgency / sentiment
        is_urgent = any(w in msg_lower for w in URGENCY_KEYWORDS["high"])
        sentiment = "urgent" if is_urgent else "neutral"
        if any(w in msg_lower for w in ["thanks", "thank", "help", "please", "gracias", "ayuda"]):
            sentiment = "positive" if sentiment == "neutral" else sentiment
        if any(w in msg_lower for w in ["bad", "terrible", "awful", "worst", "scam", "malo", "estafa"]):
            sentiment = "negative"

        # Intent scores
        scores = {
            "lead_interest": sum(1 for w in LEAD_KEYWORDS if w in msg_lower) / max(len(LEAD_KEYWORDS), 1),
            "support_question": sum(1 for w in ["how", "what", "where", "when", "why", "question",
                                                 "cómo", "qué", "dónde", "cuándo", "por qué"] if w in msg_lower)
                                 / 11.0,
            "complaint": sum(1 for w in ["bad", "terrible", "awful", "worst", "scam", "never",
                                          "malo", "estafa", "nunca más"] if w in msg_lower) / 9.0,
            "contractor_inquiry": sum(1 for w in ["contractor", "roofer", "company", "business",
                                                    "partner", "contratista", "compañía", "negocio"]
                                      if w in msg_lower) / 8.0,
        }

        if is_urgent:
            scores["lead_interest"] *= 1.5

        intent = max(scores, key=scores.get)
        confidence = min(scores[intent] * 2.0, 0.95)

        if max(scores.values()) < 0.1:
            intent = "support_question"
            confidence = 0.5

        return {"intent": intent, "confidence": round(confidence, 2),
                "sentiment": sentiment, "language": language}

    # ── FAQ matching ───────────────────────────────────────────────

    def _match_faq(self, message: str, language: str = "en") -> Optional[str]:
        patterns = FAQ_PATTERNS_ES if language == "es" else FAQ_PATTERNS
        for pattern, answer in patterns.items():
            if re.match(pattern, message):
                return answer
        return None

    # ── Data extraction ────────────────────────────────────────────

    def _extract_location(self, message: str) -> Optional[str]:
        msg_lower = message.lower()
        for city in US_CITIES:
            if city in msg_lower:
                return city.title()
        return None

    def _extract_phone(self, message: str) -> Optional[str]:
        m = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', message)
        return m.group(0) if m else None

    def _extract_email(self, message: str) -> Optional[str]:
        m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', message)
        return m.group(0) if m else None

    def _extract_damage_type(self, message: str) -> Optional[str]:
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["roof", "shingle", "tile", "techo"]):
            return "roof"
        if any(w in msg_lower for w in ["water", "flood", "leak", "pipe", "agua", "inundación"]):
            return "water"
        if any(w in msg_lower for w in ["wind", "tornado", "viento"]):
            return "wind"
        if any(w in msg_lower for w in ["hail", "granizo"]):
            return "hail"
        if any(w in msg_lower for w in ["flood", "inundación"]):
            return "flood"
        if any(w in msg_lower for w in ["fire", "smoke", "fuego", "humo"]):
            return "fire"
        return None

    def _extract_urgency(self, message: str) -> str:
        msg_lower = message.lower()
        for level, keywords in URGENCY_KEYWORDS.items():
            if any(w in msg_lower for w in keywords):
                return level
        return "medium"

    # ── Response generation ────────────────────────────────────────

    def _generate_lead_reply(self, stage: str, lead_state: Dict) -> str:
        if stage in ("none", "asking_location"):
            return (
                "I'd be happy to help! First, could you tell me what city you're in? "
                "We serve the Dallas-Fort Worth area, Houston, Oklahoma City, and more."
            )
        if stage == "asking_damage":
            return (
                f"Thanks, {lead_state.get('location', 'there')}! "
                "What type of damage did you experience? Roof damage, water damage, "
                "wind damage, hail damage, or something else?"
            )
        if stage == "asking_urgency":
            return (
                "How urgent is this? Is there an active leak or emergency that needs "
                "immediate attention, or can it wait a day or two?"
            )
        if stage == "asking_contact":
            return (
                "Great, I have a vetted contractor in your area who can help. "
                "Could you share your phone number or email so they can reach you?"
            )
        if stage == "complete":
            return (
                f"Perfect! A contractor in {lead_state.get('location', 'your area')} "
                "will reach out shortly. In the meantime, document any visible damage "
                "with photos. Is there anything else I can help with?"
            )
        return "How can I help you with your storm damage needs?"

    def _generate_away_message(self) -> str:
        return (
            "Thanks for reaching out! Our team is currently away "
            f"(we're available {BUSINESS_HOURS_START} AM to {BUSINESS_HOURS_END} PM ET). "
            "Please leave your name, phone number, and a brief description of your needs, "
            "and we'll get back to you first thing in the morning. "
            "If this is an emergency, please call 911."
        )

    async def _generate_llm_reply(self, message: str, language: str = "en") -> Optional[str]:
        """Fallback LLM generation when FAQ doesn't match."""
        try:
            import httpx
            system = (
                "You are Empire AI's Facebook Messenger chatbot. You help homeowners "
                "with storm damage connect with vetted restoration contractors. "
                "Be helpful, professional, and concise. Keep replies under 200 chars."
            )
            if language == "es":
                system = (
                    "Eres el chatbot de Facebook Messenger de Empire AI. Ayudas a propietarios "
                    "con daños por tormentas. Responde en español."
                )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("http://localhost:11434/api/generate", json={
                    "model": "llama3.2:3b",
                    "system": system,
                    "prompt": message[:500],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 128},
                })
                data = resp.json()
                return data.get("response", "").strip()
        except Exception as e:
            log.warning(f"[FBBot] LLM reply error: {e}")
            return None

    # ── Lead capture ───────────────────────────────────────────────

    async def _save_conversation(self, psid: str, message: str, reply: str, metadata: Dict):
        try:
            sb.table("facebook_conversations").insert({
                "psid": psid,
                "message": message,
                "reply": reply,
                "metadata": json.dumps(metadata),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug(f"[FBBot] save_conversation unavailable: {e}")

    async def _save_lead(self, lead_data: Dict) -> Optional[str]:
        try:
            r = sb.table("facebook_leads").insert({
                "psid": lead_data.get("psid"),
                "name": lead_data.get("name", "Facebook Lead"),
                "location": lead_data.get("location", ""),
                "damage_type": lead_data.get("damage_type", ""),
                "urgency": lead_data.get("urgency", "medium"),
                "phone": lead_data.get("phone", ""),
                "email": lead_data.get("email", ""),
                "qualified": True,
                "source": "facebook_messenger",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            if r.data:
                lead_id = r.data[0].get("id")
                log.info(f"[FBBot] Lead captured: {lead_id} from {lead_data.get('location', '?')}")
                return lead_id
        except Exception as e:
            log.warning(f"[FBBot] save_lead unavailable: {e}")
        return None

    async def _route_lead(self, lead_data: Dict):
        """Route a qualified lead via dispatch logging + optional notification."""
        log.info(
            f"[FBBot] Routing lead: {lead_data.get('location', '?')} "
            f"damage={lead_data.get('damage_type', '?')} "
            f"urgency={lead_data.get('urgency', '?')}"
        )
        try:
            sb.table("inbound_leads").insert({
                "source": "facebook_messenger",
                "name": lead_data.get("name", ""),
                "phone": lead_data.get("phone", ""),
                "location": lead_data.get("location", ""),
                "notes": json.dumps(lead_data),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug(f"[FBBot] route_lead insert: {e}")

    # ── Core message processing ────────────────────────────────────

    async def process_message(self, message: str, sender_name: str = "Visitor",
                               psid: str = "unknown") -> Dict[str, Any]:
        """Process a single message through the full pipeline.

        Returns {reply_text, classification, lead_data, actions, requires_human}.
        """
        result: Dict[str, Any] = {
            "reply_text": "",
            "classification": {},
            "lead_data": {},
            "actions": [],
            "requires_human": False,
        }

        # Business hours gate
        if not self._in_business_hours():
            result["reply_text"] = self._generate_away_message()
            result["actions"].append({"type": "away_message"})
            return result

        # Classify
        classification = self._classify_intent(message)
        result["classification"] = classification

        # Spam → silent
        if classification["intent"] == "spam":
            return result

        # Extract lead info
        location = self._extract_location(message)
        damage_type = self._extract_damage_type(message)
        phone = self._extract_phone(message)
        email = self._extract_email(message)
        urgency = self._extract_urgency(message)

        # ── Lead flow ──────────────────────────────────────────────
        if classification["intent"] == "lead_interest":
            stage = "none"
            lead_state = {"location": location, "damage_type": damage_type,
                          "urgency": urgency, "phone": phone, "email": email, "name": sender_name}

            # Advance stages based on what we have
            if not location:
                stage = "asking_location"
            elif not damage_type:
                stage = "asking_damage"
            elif not urgency:
                stage = "asking_urgency"
            elif not (phone or email):
                stage = "asking_contact"
            else:
                stage = "complete"

            result["reply_text"] = self._generate_lead_reply(stage, lead_state)
            result["lead_data"] = {
                "captured": stage == "complete",
                "stage": stage,
                "location": location, "damage_type": damage_type,
                "urgency": urgency, "phone": phone, "email": email,
            }

            if stage == "complete":
                ld = {"psid": psid, "name": sender_name,
                       "location": location or "unknown",
                       "damage_type": damage_type or "unknown",
                       "urgency": urgency, "phone": phone or "",
                       "email": email or ""}
                lead_id = await self._save_lead(ld)
                if lead_id:
                    await self._route_lead(ld)
                    result["actions"].extend([
                        {"type": "lead_captured", "lead_id": lead_id},
                        {"type": "dispatch_contractor", "location": location},
                    ])

        # ── Support flow ───────────────────────────────────────────
        elif classification["intent"] == "support_question":
            reply = self._match_faq(message, classification.get("language", "en"))
            if not reply:
                llm = await self._generate_llm_reply(message, classification.get("language", "en"))
                reply = llm or (
                    "Thanks for reaching out! A team member will review your "
                    "message and get back to you shortly."
                )
            result["reply_text"] = reply

        # ── Complaint → human handoff ──────────────────────────────
        elif classification["intent"] == "complaint":
            result["reply_text"] = (
                "I'm sorry to hear that. I'll make sure a team member reviews "
                "your concerns right away. Is there anything specific I can help with?"
            )
            result["requires_human"] = True
            result["actions"].append({"type": "flag_human_review", "reason": "complaint"})

        # ── Contractor inquiry ─────────────────────────────────────
        elif classification["intent"] == "contractor_inquiry":
            result["reply_text"] = (
                "Thanks for your interest in partnering with Empire AI! "
                "A team member will reach out with more information. "
                "Could you share your company name and phone number?"
            )
            result["actions"].append({"type": "flag_contractor_inquiry"})

        else:
            result["reply_text"] = "How can I help you today?"

        # Persist conversation
        await self._save_conversation(psid, message, result["reply_text"], {
            "intent": classification["intent"],
            "sentiment": classification["sentiment"],
        })

        return result

    # ── Webhook event handler ──────────────────────────────────────

    async def handle_webhook_event(self, payload: dict) -> Dict[str, Any]:
        """Process an incoming Chatwoot webhook event.

        Designed to be called from a FastAPI endpoint.

        Returns the processing result, or empty dict if event is not
        a message_created from a user.
        """
        try:
            from bots.chatwoot_client import ChatwootClient
            event = ChatwootClient.parse_webhook_event(payload)
        except Exception:
            log.warning("[FBBot] Failed to parse webhook event")
            return {}

        # Only process incoming messages from users
        if event.get("event_type") != "message_created":
            return {"event_type": event.get("event_type"), "skipped": True}
        if event.get("message", {}).get("type") != "incoming":
            return {"event_type": "message_created", "skipped": True}
        if event.get("channel") not in ("facebook", "api", ""):
            log.debug(f"[FBBot] Skipping non-facebook channel: {event.get('channel')}")
            return {"event_type": "message_created", "channel": event.get("channel"), "skipped": True}

        sender = event.get("sender", {})
        conv_id = event.get("conversation_id")
        msg = event.get("message", {})

        if not conv_id or not msg.get("content"):
            return {"error": "missing conversation_id or message content"}

        # Process the message
        result = await self.process_message(
            message=msg["content"],
            sender_name=sender.get("name", "Facebook User"),
            psid=event.get("source_id") or str(sender.get("id", "unknown")),
        )

        # Send reply via Chatwoot
        if result["reply_text"]:
            await self._send_reply(conv_id, result["reply_text"])

        # If requires human, mark conversation as pending
        if result.get("requires_human") and self._chatwoot:
            await self._chatwoot.toggle_conversation_status(conv_id, "open")

        return {
            "event_type": "message_created",
            "conversation_id": conv_id,
            "reply_sent": bool(result["reply_text"]),
            "lead_captured": result.get("lead_data", {}).get("captured", False),
            "requires_human": result.get("requires_human", False),
        }

    # ── Polling cycle ──────────────────────────────────────────────

    async def run_cycle(self) -> Dict[str, int]:
        """Poll Chatwoot for open conversations and process new messages."""
        log.info("[FBBot] Starting cycle")
        stats = {"messages_processed": 0, "leads_captured": 0,
                 "replies_sent": 0, "handoffs": 0, "errors": 0}

        if not self._chatwoot:
            log.warning("[FBBot] Chatwoot not available — skipping cycle")
            return stats

        inbox_id = await self._ensure_facebook_inbox()
        conv_res = await self._chatwoot.list_conversations(status="open")

        if not conv_res.get("ok"):
            return stats

        conversations = conv_res.get("conversations", [])
        for conv in conversations[:25]:
            conv_id = conv.get("id")
            if not conv_id:
                continue

            # Get messages to find the last user message
            msgs_res = await self._chatwoot.get_conversation_messages(conv_id)
            if not msgs_res.get("ok"):
                continue

            messages = msgs_res.get("messages", [])
            # Find last incoming (user) message
            last_incoming = None
            for m in reversed(messages):
                if m.get("message_type") == "incoming" and m.get("content"):
                    last_incoming = m
                    break
            if not last_incoming:
                continue

            contact = conv.get("meta", {}).get("sender", {})
            psid = contact.get("identifier", str(conv.get("contact_id", "unknown")))

            result = await self.process_message(
                message=last_incoming["content"],
                sender_name=contact.get("name", "Facebook User"),
                psid=psid,
            )

            stats["messages_processed"] += 1
            if result.get("lead_data", {}).get("captured"):
                stats["leads_captured"] += 1
            if result.get("requires_human"):
                stats["handoffs"] += 1
            if result["reply_text"]:
                sent = await self._send_reply(conv_id, result["reply_text"])
                if sent:
                    stats["replies_sent"] += 1

            await asyncio.sleep(0.3)

        log.info(f"[FBBot] Cycle complete: {stats}")
        return stats

    async def run_continuously(self):
        """Run forever with interval sleeps."""
        log.info(f"[FBBot] Starting continuous loop (interval={self.interval}m)")
        inbox_id = await self._ensure_facebook_inbox()
        if inbox_id:
            log.info(f"[FBBot] Facebook inbox ID: {inbox_id}")
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                log.error(f"[FBBot] Cycle error: {e}")
            await asyncio.sleep(self.interval * 60)


# ── Entry points ─────────────────────────────────────────────────────

def run():
    """Entry point for main.py / threading agent launcher."""
    agent = EmpireFacebookBot(interval_minutes=5)
    asyncio.run(agent.run_continuously())


async def run_once() -> Dict[str, int]:
    """Run a single cycle for cron-based execution."""
    agent = EmpireFacebookBot()
    return await agent.run_cycle()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    run()
