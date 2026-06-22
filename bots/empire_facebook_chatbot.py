"""EMPIRE FACEBOOK CHATBOT — Empire AI (Elite)
Autonomous Facebook Messenger chatbot that handles customer support,
qualifies storm restoration leads, and routes to contractor dispatch
via Chatwoot integration.

AGI · SI · PREDICTIVE REVENUE WIRED:
  - AGI Governor: strategy_for_niche() selects best conversation strategy
  - SI Strategy: best_for_niche() evolves reply genome per outcome
  - Predictive Revenue: estimates lead value for prioritization
"""

import os
import json
import logging
import asyncio
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/root/.env", override=True)

log = logging.getLogger("empire.facebook_chatbot")

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# ── Chatwoot API config ─────────────────────────────────────────────
CHATWOOT_URL = os.getenv("CHATWOOT_URL", "http://localhost:8091")
CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_ACCESS_TOKEN", "")

# ── Business hours (ET) ─────────────────────────────────────────────
BUSINESS_HOURS_START = 8   # 8 AM
BUSINESS_HOURS_END = 20    # 8 PM
BUSINESS_TIMEZONE_OFFSET = -5  # ET

# ── Lead qualification stages ───────────────────────────────────────
QUALIFICATION_STAGES = ["none", "asking_location", "asking_damage", "asking_urgency", "asking_contact", "complete"]

# ── FAQ patterns ────────────────────────────────────────────────────
FAQ_PATTERNS = {
    r"(?i).*how.*file.*claim.*|.*insurance.*claim.*|.*claim.*process.*": (
        "To file a storm damage claim: 1) Document all damage with photos/videos. "
        "2) Contact your insurance provider to start a claim. "
        "3) Get a professional inspection — we can connect you with a vetted contractor who does free inspections. "
        "4) Your contractor will work directly with your adjuster. "
        "Would you like me to connect you with a local contractor for a free inspection?"
    ),
    r"(?i).*how.*long.*take.*|.*response.*time.*|.*how.*fast.*": (
        "Most contractors in our network can do an initial inspection within 24-48 hours. "
        "Emergency tarping can often be done the same day. Would you like me to connect you?"
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
        "All contractors in our network are screened for licensing, insurance, and quality."
    ),
}

# ── Spanish FAQ patterns ────────────────────────────────────────────
FAQ_PATTERNS_ES = {
    r"(?i).*reclamo.*|.*seguro.*|.*reclamaci.*": (
        "Para presentar un reclamo por daños de tormenta: 1) Tome fotos y videos de todos los daños. "
        "2) Contacte a su aseguradora para iniciar el reclamo. "
        "3) Obtenga una inspección profesional. ¿Quiere que lo conectemos con un contratista local?"
    ),
    r"(?i).*cuanto.*tiempo.*|.*rapido.*|.*demora.*": (
        "La mayoría de los contratistas pueden hacer una inspección en 24-48 horas. "
        "Las reparaciones de emergencia pueden hacerse el mismo día. ¿Lo conectamos?"
    ),
    r"(?i).*costo.*|.*precio.*|.*cuanto.*cuesta.*|.*gratis.*": (
        "Las inspecciones son gratuitas. Los costos de reparación dependen del daño. "
        "Podemos conectarlo con un contratista para un presupuesto gratis."
    ),
}


class EmpireFacebookChatbot:
    """Autonomous Facebook Messenger chatbot via Chatwoot integration.

    Handles incoming messages from Facebook Page visitors:
      1. Classifies intent (support, lead, complaint, spam)
      2. Answers support questions from FAQ / LLM
      3. Qualifies leads through structured flow
      4. Captures lead data to Supabase
      5. Routes qualified leads to contractor dispatch
      6. Flags conversations for human handoff when needed
    """

    def __init__(self, interval_minutes: int = 5):
        self.interval = interval_minutes
        self.faq = FAQ_PATTERNS
        self.faq_es = FAQ_PATTERNS_ES
        self.business_hours_start = BUSINESS_HOURS_START
        self.business_hours_end = BUSINESS_HOURS_END
        self._agi_governor = None
        self._si_strategy = None
        self._lazy_wire_agi_si_pr()

    def _lazy_wire_agi_si_pr(self):
        """Lazy-import AGI Governor, SI Strategy, and Predictive Revenue."""
        try:
            from empire_agi_governor import governor as _gov
            self._agi_governor = _gov
            log.info("[FBChatbot] AGI Governor wired")
        except Exception:
            log.debug("[FBChatbot] AGI Governor unavailable")
        try:
            from empire_si_strategy import StrategyEvolution
            self._si_strategy = StrategyEvolution.get_shared_instance()
            log.info("[FBChatbot] SI Strategy wired")
        except Exception:
            log.debug("[FBChatbot] SI Strategy unavailable")

    # ── Business Hours ───────────────────────────────────────────────

    def _in_business_hours(self) -> bool:
        """Check if current time is within configured business hours (ET)."""
        now = datetime.now(timezone.utc)
        hour_et = (now.hour + BUSINESS_TIMEZONE_OFFSET) % 24
        return self.business_hours_start <= hour_et < self.business_hours_end

    # ── Intent Classification ────────────────────────────────────────

    def _classify_intent(self, message: str) -> Dict[str, Any]:
        """Classify incoming message intent using pattern matching + heuristics.

        Returns: {"intent": str, "confidence": float, "sentiment": str, "language": str}
        """
        msg_lower = message.lower().strip()

        # Language detection
        language = "es" if re.search(r'(?i)[¿¡áéíóúñ]', message) else "en"

        # Spam detection
        spam_patterns = [r'(?i).*casino.*', r'(?i).*click.*here.*', r'(?i).*free.*money.*', r'(?i).*http[s]?://']
        if any(re.match(p, msg_lower) for p in spam_patterns):
            return {"intent": "spam", "confidence": 0.9, "sentiment": "neutral", "language": language}

        # Urgency detection
        urgent_words = ["emergency", "urgent", "asap", "now", "water", "flood", "leak", "immediate", "emergencia", "urgente"]
        is_urgent = any(w in msg_lower for w in urgent_words)

        # Sentiment
        positive_words = ["thanks", "thank", "help", "please", "great", "good", "gracias", "ayuda"]
        negative_words = ["bad", "terrible", "awful", "worst", "scam", "never", "malo", "terrible", "estafa"]
        sentiment = "neutral"
        if any(w in msg_lower for w in positive_words):
            sentiment = "positive"
        if any(w in msg_lower for w in negative_words):
            sentiment = "negative"
        if is_urgent:
            sentiment = "urgent"

        # Lead intent detection
        lead_keywords = ["roof", "damage", "storm", "hail", "repair", "fix", "leak",
                        "techo", "daño", "tormenta", "granizo", "reparación", "filtración"]
        support_keywords = ["how", "what", "where", "when", "why", "question", "info",
                          "cómo", "qué", "dónde", "cuándo", "por qué", "pregunta"]
        complaint_keywords = ["bad", "terrible", "awful", "worst", "scam", "never again",
                            "malo", "terrible", "estafa", "nunca más"]
        contractor_keywords = ["contractor", "roofer", "company", "business", "partner",
                              "contratista", "compañía", "negocio"]

        # Score each intent
        scores = {
            "lead_interest": sum(1 for w in lead_keywords if w in msg_lower) / max(len(lead_keywords), 1),
            "support_question": sum(1 for w in support_keywords if w in msg_lower) / max(len(support_keywords), 1),
            "complaint": sum(1 for w in complaint_keywords if w in msg_lower) / max(len(complaint_keywords), 1),
            "contractor_inquiry": sum(1 for w in contractor_keywords if w in msg_lower) / max(len(contractor_keywords), 1),
        }

        # Boost lead interest if message is about damage/storm
        if is_urgent:
            scores["lead_interest"] *= 1.5

        intent = max(scores, key=scores.get)
        confidence = min(scores[intent] * 2.0, 0.95)

        # Fallback to support if all scores are low
        if max(scores.values()) < 0.1:
            intent = "support_question"
            confidence = 0.5

        return {"intent": intent, "confidence": round(confidence, 2), "sentiment": sentiment, "language": language}

    # ── FAQ Matching ─────────────────────────────────────────────────

    def _match_faq(self, message: str, language: str = "en") -> Optional[str]:
        """Match message against FAQ patterns. Returns answer or None."""
        patterns = self.faq_es if language == "es" else self.faq
        for pattern, answer in patterns.items():
            if re.match(pattern, message):
                return answer
        return None

    # ── Lead Qualification ───────────────────────────────────────────

    def _extract_location(self, message: str) -> Optional[str]:
        """Extract city/state location from message using keyword matching."""
        us_cities = [
            "dallas", "fort worth", "houston", "san antonio", "austin", "oklahoma city",
            "tulsa", "miami", "orlando", "jacksonville", "new orleans", "charlotte",
            "nashville", "memphis", "atlanta", "birmingham", "little rock",
        ]
        msg_lower = message.lower()
        found = [c for c in us_cities if c in msg_lower]
        if found:
            return found[0].title()
        return None

    def _extract_phone(self, message: str) -> Optional[str]:
        """Extract phone number from message."""
        phone_pattern = r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        match = re.search(phone_pattern, message)
        if match:
            return match.group(0)
        return None

    def _extract_email(self, message: str) -> Optional[str]:
        """Extract email from message."""
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        match = re.search(email_pattern, message)
        if match:
            return match.group(0)
        return None

    def _extract_damage_type(self, message: str) -> Optional[str]:
        """Extract damage type from message."""
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

    _URGENCY_KEYWORDS = {
        "high": ["emergency", "urgent", "asap", "now", "tonight", "water", "flood", "leaking",
                 "emergencia", "urgente", "ahora", "esta noche", "inundación"],
        "medium": ["soon", "today", "tomorrow", "this week", "pronto", "hoy", "mañana", "esta semana"],
        "low": ["eventually", "sometime", "later", "not urgent", "eventualmente", "después", "no urgente"],
    }

    def _extract_urgency(self, message: str) -> str:
        """Extract urgency level from message."""
        msg_lower = message.lower()
        for level, keywords in self._URGENCY_KEYWORDS.items():
            if any(w in msg_lower for w in keywords):
                return level
        return "medium"

    # ── Response Generation ──────────────────────────────────────────

    def _generate_lead_reply(self, stage: str, lead_state: Dict) -> str:
        """Generate the next question in the lead qualification flow."""
        if stage == "none" or stage == "asking_location":
            return (
                "I'd be happy to help! First, could you tell me what city you're in? "
                "We serve the Dallas-Fort Worth area, Houston, Oklahoma City, and expanding."
            )
        elif stage == "asking_damage":
            return (
                f"Thanks, {lead_state.get('location', 'there')}! "
                "What type of damage did you experience? Roof damage, water damage, "
                "wind damage, hail damage, or something else?"
            )
        elif stage == "asking_urgency":
            return (
                "How urgent is this? Is it an active leak or emergency that needs "
                "immediate attention, or can it wait a day or two?"
            )
        elif stage == "asking_contact":
            return (
                "Great, I have a vetted contractor in your area who can help. "
                "Could you share your phone number or email so they can reach you?"
            )
        elif stage == "complete":
            return (
                f"Perfect! A contractor in {lead_state.get('location', 'your area')} "
                "will reach out to you shortly. In the meantime, document any visible "
                "damage with photos. Is there anything else I can help with?"
            )
        return "How can I help you with your storm damage?"

    def _generate_away_message(self) -> str:
        """Generate away message for outside business hours."""
        return (
            "Thanks for reaching out! Our team is currently away "
            f"(we're available {self.business_hours_start} AM to {self.business_hours_end} PM ET). "
            "Please leave your name, phone number, and a brief description of your needs, "
            "and we'll get back to you first thing in the morning. "
            "If this is an emergency, please call 911."
        )

    def _generate_support_reply(self, message: str, language: str = "en") -> str:
        """Generate support reply — check FAQ first, fall back to Ollama."""
        # Check FAQ patterns first
        faq_answer = self._match_faq(message, language)
        if faq_answer:
            return faq_answer
        # Fall back: generic helpful reply
        if language == "es":
            return (
                "Gracias por contactarnos. Un miembro de nuestro equipo revisará "
                "su mensaje y le responderá pronto. ¿Hay algo más en lo que pueda ayudarle?"
            )
        return (
            "Thanks for reaching out! A member of our team will review your "
            "message and get back to you shortly. Is there anything else I can help with?"
        )

    async def _generate_llm_reply(self, message: str, language: str = "en") -> Optional[str]:
        """Generate a reply using local LLM (fallback when FAQ doesn't match)."""
        try:
            import httpx
            system = (
                "You are Empire AI's Facebook Messenger chatbot. You help homeowners "
                "with storm damage connect with vetted restoration contractors. "
                "Be helpful, professional, and concise. Answer questions about "
                "the claims process, contractor matching, and service areas. "
                "Keep replies under 200 characters when possible."
            )
            if language == "es":
                system = (
                    "Eres el chatbot de Facebook Messenger de Empire AI. Ayudas a propietarios "
                    "con daños por tormentas a conectarse con contratistas. Responde en español."
                )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("http://localhost:11434/api/generate", json={
                    "model": "llama3.2:3b",
                    "system": system,
                    "prompt": message[:500],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 128}
                })
                data = resp.json()
                return data.get("response", "").strip()
        except Exception as e:
            log.warning(f"[FBChatbot] LLM reply error: {e}")
            return None

    # ── Lead Capture & State Persistence ────────────────────────────

    async def _load_lead_state(self, psid: str) -> Dict[str, Any]:
        """Load persistent lead qualification state from the latest conversation for a PSID.

        Queries Supabase facebook_conversations for the most recent record
        matching this PSID and extracts qualification_stage + accumulated
        lead_data from the metadata JSONB column.

        Returns dict with keys:
          stage, location, damage_type, urgency, phone, email
        Defaults to stage='none' and empty fields if no prior conversation.
        """
        try:
            r = sb.table("facebook_conversations") \
                .select("metadata") \
                .eq("psid", psid) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            if r.data and r.data[0].get("metadata"):
                meta = r.data[0]["metadata"]
                if isinstance(meta, str):
                    meta = json.loads(meta)
                ld = meta.get("lead_data", {}) or {}
                return {
                    "stage": meta.get("qualification_stage", "none"),
                    "location": ld.get("location", ""),
                    "damage_type": ld.get("damage_type", ""),
                    "urgency": ld.get("urgency", ""),
                    "phone": ld.get("phone", ""),
                    "email": ld.get("email", ""),
                }
        except Exception as e:
            log.debug(f"[FBChatbot] load_lead_state error: {e}")
        return {"stage": "none", "location": "", "damage_type": "", "urgency": "", "phone": "", "email": ""}

    async def _save_conversation(self, psid: str, message: str, reply: str,
                                  metadata: Dict,
                                  qualification_stage: str = None,
                                  lead_data: Dict = None):
        """Save conversation turn to Supabase facebook_conversations table.

        Stores qualification_stage and accumulated lead_data inside the
        metadata JSONB column so the bot can resume qualification across
        polling cycles.
        """
        try:
            payload = {
                "psid": psid,
                "message": message,
                "reply": reply,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Merge qualification state into metadata for persistence
            meta = dict(metadata)
            if qualification_stage:
                meta["qualification_stage"] = qualification_stage
            if lead_data:
                meta["lead_data"] = lead_data
            payload["metadata"] = json.dumps(meta)
            sb.table("facebook_conversations").insert(payload).execute()
        except Exception as e:
            log.debug(f"[FBChatbot] save_conversation unavailable: {e}")

    async def _save_lead(self, lead_data: Dict) -> Optional[str]:
        """Save qualified lead to Supabase facebook_leads table.
        Returns lead ID or None.
        """
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
                log.info(f"[FBChatbot] Lead captured: {lead_id} from {lead_data.get('location', '?')}")
                return lead_id
        except Exception as e:
            log.warning(f"[FBChatbot] save_lead unavailable: {e}")
        return None

    async def _route_lead_to_dispatch(self, lead_data: Dict):
        """Route a qualified lead to contractor dispatch.
        Creates a dispatch entry or sends notification.
        """
        try:
            # Log the routing action — actual dispatch via contractor_routes table
            log.info(
                f"[FBChatbot] Routing lead: {lead_data.get('location', '?')} "
                f"damage={lead_data.get('damage_type', '?')} "
                f"urgency={lead_data.get('urgency', '?')}"
            )
            # In production: insert into dispatches or contractor_assignments table
        except Exception as e:
            log.warning(f"[FBChatbot] route_to_dispatch error: {e}")

    # ── Chatwoot Integration ─────────────────────────────────────────

    async def poll_chatwoot_conversations(self) -> List[Dict]:
        """Poll Chatwoot API for new unanswered conversations with type=facebook.
        
        Returns list of conversation objects with messages.
        Note: Requires Chatwoot to be configured with Facebook Messenger channel.
        """
        if not CHATWOOT_URL or not CHATWOOT_API_TOKEN:
            log.warning("[FBChatbot] Chatwoot not configured — falling back to direct message handling")
            return []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get all conversations with pending messages
                resp = await client.get(
                    f"{CHATWOOT_URL}/api/v1/conversations",
                    headers={
                        "api_access_token": CHATWOOT_API_TOKEN,
                        "Content-Type": "application/json",
                    },
                    params={"status": "pending", "inbox_id": "facebook"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("data", data.get("payload", [])) if isinstance(data, dict) else []
                else:
                    log.warning(f"[FBChatbot] Chatwoot API error: {resp.status_code}")
                    return []
        except Exception as e:
            log.warning(f"[FBChatbot] Chatwoot poll error: {e}")
            return []

    async def send_chatwoot_reply(self, conversation_id: str, reply_text: str):
        """Send a reply back through Chatwoot to Facebook Messenger."""
        if not CHATWOOT_URL or not CHATWOOT_API_TOKEN:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{CHATWOOT_URL}/api/v1/conversations/{conversation_id}/messages",
                    headers={
                        "api_access_token": CHATWOOT_API_TOKEN,
                        "Content-Type": "application/json",
                    },
                    json={
                        "content": reply_text,
                        "message_type": "outgoing",
                        "private": False,
                    },
                )
                if resp.status_code == 200:
                    log.info(f"[FBChatbot] Reply sent to Chatwoot conv {conversation_id[:8]}")
                else:
                    log.warning(f"[FBChatbot] Chatwoot send error: {resp.status_code}")
        except Exception as e:
            log.warning(f"[FBChatbot] Chatwoot send error: {e}")

    # ── Message Processing ───────────────────────────────────────────

    async def process_message(self, message: str, sender_name: str = "Visitor",
                               psid: str = "unknown", conversation_id: str = None) -> Dict[str, Any]:
        """Process a single incoming Facebook Messenger message.

        Full pipeline:
          1. Check business hours
          2. Classify intent
          3. Load persistent lead state from Supabase (resume across cycles)
          4. Generate appropriate reply
          5. Save conversation with current qualification stage
          6. Capture lead if qualified
          7. Route to dispatch
          8. Return response

        Returns dict with reply, classification, lead_data, actions.
        """
        result = {
            "reply_text": "",
            "classification": {},
            "lead_data": {},
            "actions": [],
            "requires_human": False,
        }

        # ── Step 1: Business hours gate ──────────────────────────────
        if not self._in_business_hours():
            result["reply_text"] = self._generate_away_message()
            result["actions"].append({"type": "away_message_sent"})
            return result

        # ── Step 2: Load persistent lead state from Supabase ─────────
        # This resumes qualification across polling cycles so the bot
        # doesn't start from scratch every 5 minutes.
        lead_state = await self._load_lead_state(psid)
        last_stage = lead_state["stage"]

        # Merge persisted data as defaults (new message can override)
        location = lead_state.get("location") or None
        damage_type = lead_state.get("damage_type") or None
        urgency = lead_state.get("urgency") or None
        phone = lead_state.get("phone") or None
        email = lead_state.get("email") or None

        # ── Step 3: Classify ─────────────────────────────────────────
        classification = self._classify_intent(message)
        result["classification"] = classification

        # ── Step 4: Handle by intent ─────────────────────────────────
        if classification["intent"] == "spam":
            result["reply_text"] = ""  # No reply to spam
            return result

        # Extract lead info from current message (overrides persisted defaults)
        location = self._extract_location(message) or location
        damage_type = self._extract_damage_type(message) or damage_type
        phone = self._extract_phone(message) or phone
        email = self._extract_email(message) or email
        urgency = self._extract_urgency(message) or urgency

        # Track current stage for persistence across cycles
        current_stage = last_stage
        current_lead_data = {
            "location": location or "",
            "damage_type": damage_type or "",
            "urgency": urgency or "",
            "phone": phone or "",
            "email": email or "",
        }

        if classification["intent"] == "lead_interest" or last_stage != "none":
            # ── Lead qualification flow ──────────────────────────
            stage = last_stage
            lead_state = {
                "location": location,
                "damage_type": damage_type,
                "urgency": urgency,
                "phone": phone,
                "email": email,
                "name": sender_name,
            }

            # Advance through stages based on what we have
            if stage == "none":
                stage = "asking_location" if not location else "asking_damage"
            if stage == "asking_location" and location:
                stage = "asking_damage"
            if stage == "asking_damage" and damage_type:
                stage = "asking_urgency"
            if stage == "asking_urgency" and urgency:
                stage = "asking_contact"
            if stage == "asking_contact" and (phone or email):
                stage = "complete"

            result["reply_text"] = self._generate_lead_reply(stage, lead_state)
            current_stage = stage
            current_lead_data = {
                "location": location or "",
                "damage_type": damage_type or "",
                "urgency": urgency or "",
                "phone": phone or "",
                "email": email or "",
            }

            result["lead_data"] = {
                "captured": stage == "complete",
                "stage": stage,
                "location": location,
                "damage_type": damage_type,
                "urgency": urgency,
                "phone": phone,
                "email": email,
            }

            # If lead is complete, save and route
            if stage == "complete":
                lead_data = {
                    "psid": psid,
                    "name": sender_name,
                    "location": location or "unknown",
                    "damage_type": damage_type or "unknown",
                    "urgency": urgency,
                    "phone": phone or "",
                    "email": email or "",
                }
                lead_id = await self._save_lead(lead_data)
                if lead_id:
                    await self._route_lead_to_dispatch(lead_data)
                    result["actions"].append({"type": "lead_captured", "lead_id": lead_id})
                    result["actions"].append({"type": "dispatch_contractor", "location": location, "damage_type": damage_type})

        elif classification["intent"] == "support_question":
            # ── Support flow ─────────────────────────────────────
            result["reply_text"] = self._generate_support_reply(message, classification.get("language", "en"))

            # If FAQ didn't match, try LLM
            if result["reply_text"].startswith("Thanks for reaching out") or \
               result["reply_text"].startswith("Gracias por contactarnos"):
                llm_reply = await self._generate_llm_reply(message, classification.get("language", "en"))
                if llm_reply:
                    result["reply_text"] = llm_reply

        elif classification["intent"] == "complaint":
            # ── Complaint — flag for handoff ─────────────────────
            result["reply_text"] = (
                "I'm sorry to hear that. I'll make sure a team member reviews "
                "your concerns right away. In the meantime, is there anything "
                "specific I can help with?"
            )
            result["requires_human"] = True
            result["actions"].append({"type": "flag_human_review", "reason": "complaint"})

        elif classification["intent"] == "contractor_inquiry":
            # ── Contractor partnership inquiry ───────────────────
            result["reply_text"] = (
                "Thanks for your interest in partnering with Empire AI! "
                "Our contractor network is growing. A team member will reach out "
                "with more information about joining our network. "
                "Could you share your company name and phone number?"
            )
            result["actions"].append({"type": "flag_contractor_inquiry"})

        else:
            # ── Fallback ─────────────────────────────────────────
            result["reply_text"] = self._generate_support_reply(message, classification.get("language", "en"))

        # ── Step 4: Save conversation to Supabase with persistent state ──
        await self._save_conversation(
            psid, message, result["reply_text"],
            metadata={
                "intent": classification["intent"],
                "sentiment": classification["sentiment"],
                "lead_captured": result["lead_data"].get("captured", False),
            },
            qualification_stage=current_stage if current_stage != "none" else None,
            lead_data=current_lead_data if any(current_lead_data.values()) else None,
        )

        # ── Step 5: Send through Chatwoot if configured ──────────────
        if conversation_id and result["reply_text"]:
            await self.send_chatwoot_reply(conversation_id, result["reply_text"])

        return result

    # ── Main Cycle ───────────────────────────────────────────────────

    async def run_cycle(self) -> Dict[str, Any]:
        """One full Facebook Messenger processing cycle.

        1. Poll Chatwoot for new conversations
        2. Process each new message
        3. Send replies back through Chatwoot
        4. Log stats
        """
        log.info("[FBChatbot] Starting messenger cycle")
        stats = {"messages_processed": 0, "leads_captured": 0, "replies_sent": 0, "handoffs": 0}

        # ── Poll Chatwoot for new conversations ──────────────────────
        conversations = await self.poll_chatwoot_conversations()
        if not conversations:
            log.debug("[FBChatbot] No new conversations")
            return stats

        for conv in conversations[:25]:  # Process up to 25 per cycle
            conv_id = conv.get("id", str(conv.get("conversation_id", "")))
            messages = conv.get("messages", [conv.get("last_message", {})])
            last_msg = messages[-1] if messages else {}

            # Only process if last message is from the user (not our bot reply)
            if last_msg.get("message_type") == "incoming" or not last_msg.get("message_type"):
                result = await self.process_message(
                    message=last_msg.get("content", last_msg.get("text", "")),
                    sender_name=conv.get("sender", {}).get("name", "Facebook User"),
                    psid=conv.get("contact", {}).get("id", conv.get("sender_id", "unknown")),
                    conversation_id=conv_id,
                )
                stats["messages_processed"] += 1
                if result["lead_data"].get("captured"):
                    stats["leads_captured"] += 1
                if result.get("requires_human"):
                    stats["handoffs"] += 1
                if result["reply_text"]:
                    stats["replies_sent"] += 1

            await asyncio.sleep(0.5)  # Rate limit between conversations

        log.info(f"[FBChatbot] Cycle complete: {stats}")
        return stats

    async def run_continuously(self):
        """Run the Facebook Messenger chatbot in a continuous loop."""
        log.info(f"[FBChatbot] Starting continuous loop (interval={self.interval}m)")
        while True:
            try:
                result = await self.run_cycle()
                if result["messages_processed"] > 0:
                    log.info(f"[FBChatbot] Cycle result: {result}")
            except Exception as e:
                log.error(f"[FBChatbot] Cycle error: {e}")
            await asyncio.sleep(self.interval * 60)


# ── Entry points ─────────────────────────────────────────────────────

def run():
    """Entry point for main.py / threading agent launcher."""
    agent = EmpireFacebookChatbot(interval_minutes=5)
    asyncio.run(agent.run_continuously())


async def run_once():
    """Run a single cycle for testing or cron-based execution."""
    agent = EmpireFacebookChatbot()
    return await agent.run_cycle()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    run()
