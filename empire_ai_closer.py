"""
EMPIRE V49 · AI CLOSER — AGI-BRAINED + SYNTHETIC INTELLIGENCE VOICE PIPELINE
==============================================================================
Replaces the VAPI_CLOSER stub with the in-house voice + brain stack:

  Lead Inbound → BrainDecider (GO/NO_GO) → Strategy Selection (AGI Governor)
                                           ↓
         ┌─────────────────────────────────┴─────────────────────────────────┐
         │  GO + high conf  │  GO + medium conf  │  GO + low conf  │  NO_GO  │
         │  Live Kokoro TTS │  Static NCCO call   │  SMS/Email      │  Nurture│
         │  (streaming)     │  (Vonage built-in)  │  follow-up      │  drip   │
         └────────────────────────────────────────────────────────────────────┘
                                           ↓
                          Outcome → AGI Governor → SI Strategy Evolution

Architecture:
  - BrainDecider scores every lead via Ollama LLM (Go/No-Go + confidence)
  - AGI Governor picks the best SI-evolved strategy per niche (genome-based)
  - VoiceStreamingAgent triggers live Kokoro TTS for high-confidence GOs
  - VoiceRouter handles static NCCO calls for medium-confidence GOs
  - SMSEngine / EmailEngine for nurture fallbacks
  - Compliance checks (TCPA, DNC, calling hours) before any call
  - Outcomes feed back to StrategyEvolution for continuous learning

Confidence thresholds:
  AGI_STREAM_THRESHOLD  = 0.7  → live Kokoro TTS streaming call
  STATIC_CALL_THRESHOLD = 0.4  → static NCCO call (Vonage built-in TTS)
  Below 0.4                    → nurture (email/SMS drip)

Supabase tables:
  - ai_closer_decisions: full decision trail with brain scores + strategy + outcomes
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Callable

sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("empire.ai.closer")

# ── Confidence thresholds for routing ───────────────────────────────
AGI_STREAM_THRESHOLD  = float(os.environ.get("CLOSER_AGI_STREAM_THRESHOLD", "0.7"))
STATIC_CALL_THRESHOLD = float(os.environ.get("CLOSER_STATIC_CALL_THRESHOLD", "0.4"))
# ── Voice profile for live TTS ──────────────────────────────────────
DEFAULT_VOICE = os.environ.get("CLOSER_DEFAULT_VOICE", "am_michael")
# ── Multi-turn objection handling ──────────────────────────────────
MAX_OBJECTION_TURNS = int(os.environ.get("CLOSER_MAX_OBJECTION_TURNS", "3"))
OBJECTION_TURN_TIMEOUT = float(os.environ.get("CLOSER_OBJECTION_TIMEOUT", "12.0"))

# ═════════════════════════════════════════════════════════════════════════
# MRR-BASED ENGAGEMENT TIERS
# ═════════════════════════════════════════════════════════════════════════
# Each tier determines:
#   - engagement_level: 'basic' | 'full' | 'premium' (script quality / patterns)
#   - routing_bias:     confidence boost added to thresholds (more aggressive = higher)
#   - preferred_channel: the ideal outbound channel for this tier
#   - human_handoff:     whether this tier triggers human operator escalation
#   - script_generation: 'template' | 'agi' | 'agi_premium' (which script engine)
#
# Tiers are evaluated top-down; the first match (lead_mrr >= threshold) wins.
MRR_TIERS = [
    {
        "name": "EXECUTIVE_WHALE",
        "threshold": 10000.0,
        "engagement_level": "premium",
        "routing_bias": 0.40,
        "preferred_channel": "agi_stream",
        "human_handoff": False,
        "script_generation": "agi_premium",
        "operator_notify": False,
    },
    {
        "name": "ENTERPRISE",
        "threshold": 2000.0,
        "engagement_level": "premium",
        "routing_bias": 0.25,
        "preferred_channel": "agi_stream",
        "human_handoff": False,
        "script_generation": "agi_premium",
        "operator_notify": True,
    },
    {
        "name": "PREMIUM",
        "threshold": 500.0,
        "engagement_level": "premium",
        "routing_bias": 0.15,
        "preferred_channel": "agi_stream",
        "human_handoff": False,
        "script_generation": "agi_premium",
        "operator_notify": False,
    },
    {
        "name": "GROWTH",
        "threshold": 200.0,
        "engagement_level": "full",
        "routing_bias": 0.08,
        "preferred_channel": "static_call",
        "human_handoff": False,
        "script_generation": "agi",
        "operator_notify": False,
    },
    {
        "name": "STARTER",
        "threshold": 50.0,
        "engagement_level": "full",
        "routing_bias": 0.03,
        "preferred_channel": "static_call",
        "human_handoff": False,
        "script_generation": "agi",
        "operator_notify": False,
    },
    {
        "name": "BROADCAST",
        "threshold": 0.0,
        "engagement_level": "basic",
        "routing_bias": 0.0,
        "preferred_channel": "nurture",
        "human_handoff": False,
        "script_generation": "template",
        "operator_notify": False,
    },
]

# Default tier used when no MRR data is available (conservative)
DEFAULT_TIER = MRR_TIERS[-1]  # BROADCAST

def get_mrr_tier(lead_mrr: float) -> dict:
    """Return the highest MRR tier a lead qualifies for based on their MRR."""
    for tier in MRR_TIERS:
        if lead_mrr >= tier["threshold"]:
            return tier
    return DEFAULT_TIER


def get_engagement_level_for_mrr(lead_mrr: float) -> str:
    """Shorthand: return just the engagement level for a given MRR."""
    return get_mrr_tier(lead_mrr)["engagement_level"]


def get_routing_bias_for_mrr(lead_mrr: float) -> float:
    """Shorthand: return just the routing confidence bias for a given MRR."""
    return get_mrr_tier(lead_mrr)["routing_bias"]


def get_script_generation_mode(lead_mrr: float) -> str:
    """Shorthand: return the script generation mode for a given MRR."""
    return get_mrr_tier(lead_mrr)["script_generation"]


def should_human_handoff(lead_mrr: float) -> bool:
    """Shorthand: return whether human operator should be notified."""
    return get_mrr_tier(lead_mrr)["human_handoff"]


def get_preferred_channel(lead_mrr: float) -> str:
    """Shorthand: return the preferred channel for a given MRR."""
    return get_mrr_tier(lead_mrr)["preferred_channel"]

# ── Nurture sequence types ──────────────────────────────────────────
NURTURE_STORM = "storm_strike"
NURTURE_GENERIC = "generic_outreach"


# ═════════════════════════════════════════════════════════════════════════
# HUMAN CLOSING ENGINE — Models Real Human Sales Closer Behavior
# ═════════════════════════════════════════════════════════════════════════


class HumanClosingEngine:
    """
    Models how real human salespeople close deals. The AI Closer uses this
    engine to emulate human closing behavior:

    **Lead Persona Detection** — Classifies leads into personality types
    (Analytical, Decisive, Relationship-driven, Price-sensitive, Skeptical)
    based on their responses and behavior, then adapts the approach.

    **Human Closer Personas** — The system can adopt different closing
    styles modeled after real top-performing salespeople:
      - The Consultative Closer (asks questions, listens, guides)
      - The Urgency Driver (time pressure, scarcity, deadlines)
      - The Value Articulator (paints the ROI picture)
      - The Relationship Builder (trust, rapport, social proof)
      - The Direct Closer (assumptive, straightforward)

    **Conversational Flow** — Models the stages of a human call:
      OPENING → DISCOVERY → PRESENTATION → OBJECTION → CLOSE
    Each stage has different goals, techniques, and exit criteria.

    **Buying Signals** — Recognizes keywords and patterns that indicate
    the lead is ready to commit versus still needing nurturing.

    All layers are advisory — the ClosingExpert can use signals from this
    engine to tailor scripts and objection responses like a real human would.
    """

    # ── LEAD PERSONA TYPES ──────────────────────────────────────────────
    LEAD_PERSONAS = {
        "analytical": {
            "label": "Analytical",
            "traits": ["data-driven", "detail-oriented", "needs proof", "compares options"],
            "keywords": ["show me", "statistics", "data", "research", "compare", "specs", "numbers", "percentage"],
            "approach": "Lead with data, case studies, and verifiable results. Use social proof with numbers.",
            "voice_tone": "measured, precise",
            "preferred_technique": "summary_close",
        },
        "decisive": {
            "label": "Decisive",
            "traits": ["wants bottom line", "impatient", "action-oriented", "direct"],
            "keywords": ["bottom line", "get to the point", "what's this about", "fast", "quick", "just tell me"],
            "approach": "Get straight to the point. Lead with the outcome, not the process. Respect their time.",
            "voice_tone": "confident, brisk",
            "preferred_technique": "direct_ask",
        },
        "relationship": {
            "label": "Relationship-Driven",
            "traits": ["trust first", "wants referrals", "values reputation", "long-term thinking"],
            "keywords": ["who else", "referral", "reputation", "trust", "company behind", "who's involved"],
            "approach": "Build rapport first. Use social proof, testimonials, and third-party validation. Be transparent.",
            "voice_tone": "warm, conversational",
            "preferred_technique": "trust_building",
        },
        "price_sensitive": {
            "label": "Price-Sensitive",
            "traits": ["cost-conscious", "compares value", "risk-averse", "needs ROI clarity"],
            "keywords": ["cost", "free", "charge", "pricing", "expensive", "worth", "value", "save"],
            "approach": "Emphasize zero-cost inspection, insurance coverage, and cost of inaction. Value reversal.",
            "voice_tone": "reassuring, patient",
            "preferred_technique": "value_reversal",
        },
        "skeptical": {
            "label": "Skeptical",
            "traits": ["guarded", "questions legitimacy", "wants verification", "past bad experiences"],
            "keywords": ["scam", "legit", "real", "verify", "prove", "BBB", "license", "accreditation"],
            "approach": "Validate their concern. Lead with credentials, licensing, and verifiable proof. Offer third-party verification.",
            "voice_tone": "respectful, transparent",
            "preferred_technique": "trust_building",
        },
    }

    # ── HUMAN CLOSER PERSONAS (modeled after real top performers) ────────
    CLOSER_PERSONAS = {
        "consultative": {
            "name": "The Consultative Closer",
            "description": "Asks discovery questions, listens carefully, and guides the lead to their own conclusion. Modeled after top B2B sales consultants.",
            "strengths": ["high-trust relationships", "needs discovery", "long-term value"],
            "signature_pattern": "'{lead_name}, help me understand — what's your biggest concern about the property right now? That's exactly why I'm calling.'",
        },
        "urgency_driver": {
            "name": "The Urgency Driver",
            "description": "Creates genuine time-based scarcity. Modeled after disaster restoration closers who know the insurance window is real.",
            "strengths": ["time-sensitive deals", "high-intent leads", "storm response"],
            "signature_pattern": "'I want to be straight with you, {lead_name} — the insurance window on this type of damage closes in {hours} hours. We have teams in {location} right now.'",
        },
        "value_articulator": {
            "name": "The Value Articulator",
            "description": "Paints a vivid picture of the ROI. Shows what they gain vs what they lose. Modeled after enterprise SaaS closers.",
            "strengths": ["ROI discussions", "commercial clients", "budget objections"],
            "signature_pattern": "'Here's what I've seen happen with properties like yours in {location}: the average claim is ${amount}. The inspection is free, and if there's damage, insurance covers it.'",
        },
        "relationship_builder": {
            "name": "The Relationship Builder",
            "description": "Leads with empathy, social proof, and long-term partnership framing. Modeled after restoration industry veterans.",
            "strengths": ["referral networks", "repeat clients", "community reputation"],
            "signature_pattern": "'We've already helped {count} property owners in your area this week. Your neighbor at {address} just signed up. Everyone's in the same boat after this storm.'",
        },
        "direct_closer": {
            "name": "The Direct Closer",
            "description": "Assumptive, confident, straightforward. Doesn't waste time. Modeled after top-performing phone sales reps.",
            "strengths": ["high-volume calls", "time-pressed leads", "decisive buyers"],
            "signature_pattern": "'{lead_name}, our team is in {location} today and tomorrow. I can have someone at your property by {time}. Does morning or afternoon work better?'",
        },
    }

    # ── CONVERSATIONAL FLOW STATES ───────────────────────────────────────
    FLOW_STATES = [
        {
            "state": "opening",
            "goal": "Get permission to continue. Establish relevance.",
            "duration_seconds": 15,
            "success_signal": "lead responds with interest or asks a question",
            "techniques": ["rapport_opener", "permission_ask"],
        },
        {
            "state": "discovery",
            "goal": "Uncover the lead's situation, concerns, and readiness.",
            "duration_seconds": 20,
            "success_signal": "lead shares specific concerns or asks about process",
            "techniques": ["needs_discovery", "mirror_pacing"],
        },
        {
            "state": "presentation",
            "goal": "Present the solution framed around the lead's specific situation.",
            "duration_seconds": 25,
            "success_signal": "lead engages with the offering, asks about next steps",
            "techniques": ["value_presentation", "social_proof"],
        },
        {
            "state": "objection",
            "goal": "Address concerns and rebuild certainty.",
            "duration_seconds": 20,
            "success_signal": "lead's concern is addressed, they move toward acceptance",
            "techniques": ["empathy_bridge", "value_reversal"],
        },
        {
            "state": "close",
            "goal": "Get a commitment on next steps.",
            "duration_seconds": 15,
            "success_signal": "lead agrees to inspection or visit",
            "techniques": ["soft_close", "trial_close", "direct_ask"],
        },
    ]

    # ── BUYING SIGNALS ──────────────────────────────────────────────────
    BUYING_SIGNALS = {
        "ready_to_commit": [
            "how do I start", "what's the next step", "when can you come",
            "can you do", "sign me up", "let's do it", "send someone",
            "schedule it", "book it", "go ahead",
        ],
        "needs_more_info": [
            "tell me more", "how does it work", "what's included",
            "is there a warranty", "how long does it take", "what about",
        ],
        "hesitating": [
            "let me think", "I'll call you back", "not sure yet", "maybe later",
            "let me check", "I need to ask", "let me get back",
        ],
    }

    def __init__(self):
        self.stats = {
            "personas_detected": 0,
            "buying_signals_caught": 0,
            "closer_persona_used": "consultative",
            "hesitation_routed_to_engagement": 0,
        }
        self._current_persona: Optional[str] = None
        self._current_closer: str = "consultative"
        self._flow_state: str = "opening"

    # ── LEAD PERSONA DETECTION ─────────────────────────────────────────

    def detect_lead_persona(self, lead_text: str = "") -> str:
        """
        Detect the lead's personality type from their text (objection,
        transcript, or response). Falls back to the lead's source/type
        if no text is available.

        Returns the persona key (analytical, decisive, relationship,
        price_sensitive, skeptical) or 'unknown'.
        """
        if not lead_text or len(lead_text.strip()) < 3:
            return "unknown"

        lead_lower = lead_text.lower()
        scores = {}

        for persona_key, persona_data in self.LEAD_PERSONAS.items():
            score = 0
            for kw in persona_data["keywords"]:
                if kw in lead_lower:
                    score += 2
            for trait in persona_data["traits"]:
                if any(word in lead_lower for word in trait.split()):
                    score += 1
            if score > 0:
                scores[persona_key] = score

        if not scores:
            return "unknown"

        detected = max(scores, key=scores.get)
        self._current_persona = detected
        self.stats["personas_detected"] += 1
        return detected

    # ── SELECT CLOSER PERSONA ───────────────────────────────────────────

    def select_closer_persona(
        self,
        lead_persona: str = "unknown",
        lead_mrr: float = 0.0,
        strategy: str = "",
        confidence: float = 0.5,
    ) -> str:
        """
        Select the best human closer persona based on lead persona and
        context. Real human salespeople adapt their style to the prospect.
        """
        # Map lead persona to best closer persona
        persona_to_closer = {
            "analytical": "consultative",     # data-driven leads need consultative approach
            "decisive": "direct_closer",       # decisive leads want direct approach
            "relationship": "relationship_builder",  # relationship leads need rapport
            "price_sensitive": "value_articulator",  # price concerns need value articulation
            "skeptical": "relationship_builder",     # skepticism needs trust building
        }

        # High-MRR leads get the value articulator
        if lead_mrr >= 5000:
            self._current_closer = "value_articulator"
            return "value_articulator"

        # Aggressive strategies use urgency driver
        if "AGGRESSIVE" in strategy or "STRIKE" in strategy:
            self._current_closer = "urgency_driver"
            return "urgency_driver"

        # Use the persona-based mapping
        recommended = persona_to_closer.get(lead_persona)
        if recommended:
            self._current_closer = recommended
            return recommended

        # Default: consultative is safe for any lead
        self._current_closer = "consultative"
        return "consultative"

    # ── BUYING SIGNAL DETECTION ─────────────────────────────────────────

    def detect_buying_signal(self, lead_text: str) -> Optional[str]:
        """
        Detect whether the lead is giving a buying signal.
        Returns the signal type ('ready_to_commit', 'needs_more_info',
        'hesitating') or None if no signal detected.
        """
        if not lead_text:
            return None

        lead_lower = lead_text.lower()

        for signal_type, keywords in self.BUYING_SIGNALS.items():
            for kw in keywords:
                if kw in lead_lower:
                    self.stats["buying_signals_caught"] += 1
                    return signal_type

        return None

    # ── FLOW STATE MANAGEMENT ───────────────────────────────────────────

    def advance_flow(self, current_script: str, lead_response: str = "") -> str:
        """
        Advance the conversational flow state based on the lead's response.
        Like a real human closer, the system moves through stages:
        opening → discovery → presentation → objection → close.

        Returns the next flow state to transition into.
        """
        state_order = [s["state"] for s in self.FLOW_STATES]

        if not self._flow_state or self._flow_state not in state_order:
            self._flow_state = "opening"
            return "opening"

        # If lead shows buying signal, jump to close
        if lead_response:
            signal = self.detect_buying_signal(lead_response)
            if signal == "ready_to_commit":
                self._flow_state = "close"
                return "close"
            if signal == "hesitating":
                self.stats["hesitation_routed_to_engagement"] += 1
                # Stay in current state or move back to objection
                if self._flow_state not in ("objection", "opening"):
                    self._flow_state = "objection"
                    return "objection"

        # Natural progression
        current_idx = state_order.index(self._flow_state)
        if current_idx < len(state_order) - 1:
            next_state = state_order[current_idx + 1]
            self._flow_state = next_state
            return next_state

        return self._flow_state

    # ── HUMAN CLOSING SCRIPT GENERATION ────────────────────────────────

    def build_human_script(
        self,
        lead_name: str,
        location: str,
        niche: str = "",
        strategy: str = "",
        confidence: float = 0.5,
        lead_mrr: float = 0.0,
        lead_persona: str = "unknown",
        closer_persona: Optional[str] = None,
    ) -> str:
        """
        Generate a closing script that sounds like a real human closer.
        Uses the selected closer persona's signature pattern and adapts
        it to the lead's persona and context.
        """
        closer_key = closer_persona or self._current_closer
        closer_data = self.CLOSER_PERSONAS.get(closer_key, self.CLOSER_PERSONAS["consultative"])

        # Start with the closer persona's signature pattern, personalized
        sig_pattern = closer_data["signature_pattern"]
        sig_pattern = sig_pattern.replace("{lead_name}", lead_name or "there")
        sig_pattern = sig_pattern.replace("{location}", location or "your area")
        sig_pattern = sig_pattern.replace("{hours}", "48")
        sig_pattern = sig_pattern.replace("{amount}", "$15,000")
        sig_pattern = sig_pattern.replace("{count}", "12")
        sig_pattern = sig_pattern.replace("{address}", "your street")
        sig_pattern = sig_pattern.replace("{time}", "this afternoon")

        # Add lead-persona-tailored opening based on detected persona
        persona_data = self.LEAD_PERSONAS.get(lead_persona)
        persona_opener = ""
        if persona_data:
            if lead_persona == "analytical":
                persona_opener = (
                    f"{lead_name}, I want to share something specific with you. "
                    f"Our AI detected a {67}% probability of structural stress "
                    f"in your area — that's based on {len(niche or 'similar')} "
                    f"properties we've assessed nearby."
                )
            elif lead_persona == "decisive":
                persona_opener = (
                    f"{lead_name}, I'll be brief. We're in {location} today "
                    f"assessing storm damage. Free inspection, insurance-covered "
                    f"if we find anything. I need {2} minutes of your time."
                )
            elif lead_persona == "relationship":
                persona_opener = (
                    f"{lead_name}, I'm glad I caught you. We've been working "
                    f"with property owners in {location} for years, and I want "
                    f"to make sure you're taken care of like your neighbors "
                    f"have been. We're BBB accredited with an A+ rating."
                )
            elif lead_persona == "price_sensitive":
                persona_opener = (
                    f"{lead_name}, I want to be upfront — the inspection costs "
                    f"you nothing. Our team is already in the area. If we find "
                    f"damage, your insurance covers it. If we don't, you haven't "
                    f"spent a dime. There's no risk to you."
                )
            elif lead_persona == "skeptical":
                persona_opener = (
                    f"{lead_name}, I understand your caution — there are a lot "
                    f"of storm chasers out there. Let me send you our company "
                    f"verification, license numbers, and BBB rating right now. "
                    f"You can verify everything before we take another step."
                )

        # Build the full script: persona opener + signature pattern + soft close
        script_parts = [persona_opener, sig_pattern] if persona_opener else [sig_pattern]

        # If high confidence, add an assumptive close
        if confidence >= 0.7:
            close_line = (
                f"How's your calendar look? I'll have a specialist at "
                f"your property in {location} within 24 hours."
            )
            script_parts.append(close_line)

        return "\n\n".join(p.strip() for p in script_parts if p.strip())

    def snapshot(self) -> dict:
        """Return HumanClosingEngine stats for the AICloser snapshot."""
        return {
            **self.stats,
            "current_persona": self._current_persona,
            "active_closer": self._current_closer,
            "flow_state": self._flow_state,
            "personas_available": list(self.LEAD_PERSONAS.keys()),
            "closer_personas_available": list(self.CLOSER_PERSONAS.keys()),
        }


# ═════════════════════════════════════════════════════════════════════════
# CLOSING EXPERT — AGI Scripts · Objection Handling · Human Engagement
# ═════════════════════════════════════════════════════════════════════════


class ClosingExpert:
    """
    Expert closing engine that brings three capabilities to the AI Closer:

    1. **AGI-Generated Scripts** — Uses the synthetic brain / Ollama to
       generate personalized closing scripts tailored to the lead, niche,
       strategy, and confidence level.

    2. **Objection Handling** — Structured knowledge base of common objections
       with expert responses, organized by niche and objection type.

    3. **Human Engagement Skills** — Rapport-building patterns, urgency
       escalation, pacing/mirroring language, and emotional intelligence
       signals woven into every script.

    All three layers are optional — the AICloser falls back to hardcoded
    templates if the expert is not wired or if AGI generation fails.
    """

    # ── OBJECTION KNOWLEDGE BASE ───────────────────────────────────────
    # Organized by category with expert responses that can be adapted per niche.
    OBJECTIONS = {
        "not_interested": {
            "label": "Not interested / don't need it",
            "response": (
                "I understand completely — most property owners say the same "
                "until they see the assessment. We're dispatching a adjuster "
                "to your area anyway; let me schedule a no-obligation "
                "inspection so you have the information before you decide."
            ),
            "technique": "assumptive_close",
        },
        "too_expensive": {
            "label": "Too expensive / budget concerns",
            "response": (
                "The inspection is completely free — there's no cost to you. "
                "If there IS damage, your insurance policy likely covers it "
                "in full. We handle the paperwork so you don't have to. "
                "The only expense is ignoring potential damage that gets worse."
            ),
            "technique": "value_reversal",
        },
        "need_to_think": {
            "label": "Need to think about it / call me later",
            "response": (
                "I appreciate that — you're smart to be thorough. The challenge "
                "is that storm windows close fast; if we don't inspect within "
                "48 hours, the insurance adjuster may question whether the "
                "damage was pre-existing. Let me lock in a quick assessment "
                "slot — if it's not what we expect, no obligation."
            ),
            "technique": "limited_time",
        },
        "already_have_contractor": {
            "label": "Already working with someone",
            "response": (
                "That's great — you're ahead of the curve. The reason I'm "
                "calling is that our AI flagged your property for a specific "
                "type of damage that standard inspections often miss: "
                "internal structural stress from the pressure wave. Even if "
                "your current contractor checked, this requires a thermal "
                "scan. We do it at no cost and share the results with your "
                "contractor."
            ),
            "technique": "value_add",
        },
        "not_the_decision_maker": {
            "label": "Not the decision maker / need to talk to someone",
            "response": (
                "Who should I speak with? I'll make it easy — I can send a "
                "one-page summary of what our AI detected to their phone or "
                "email right now. What's the best way to reach them?"
            ),
            "technique": "direct_ask",
        },
        "call_back_later": {
            "label": "Call back later / busy now",
            "response": (
                "Absolutely — I don't want to keep you. Let me send you a "
                "text with the best time to call back. What's your preference, "
                "morning or afternoon tomorrow?"
            ),
            "technique": "schedule_commitment",
        },
        "scam_worried": {
            "label": "Worried about scam / legitimacy",
            "response": (
                "That's a fair concern — there are a lot of storm chasers out "
                "there. We're different: we're AI-predictive, not door-knocking. "
                "You can verify us at empire-ai.co.uk. We're BBB accredited "
                "and all our adjusters are licensed. I'll send you our "
                "verification details right now."
            ),
            "technique": "trust_building",
        },
    }

    # ── CLOSING TECHNIQUES ─────────────────────────────────────────────
    TECHNIQUES = {
        "assumptive_close": "Assume the lead is ready and act as if the next step is a given.",
        "value_reversal": "Reframe the cost of inaction as higher than the cost of action.",
        "limited_time": "Create urgency around a genuine time constraint.",
        "value_add": "Offer something extra that the competition doesn't.",
        "direct_ask": "Ask directly for the commitment or next step.",
        "schedule_commitment": "Get a small commitment now (a time) to build momentum.",
        "trust_building": "Provide third-party validation and credentials.",
        "puppy_dog_close": "Let them try it (inspection) risk-free first.",
        "sharp_angle": "Turn every objection into a reason to move forward now.",
        "summary_close": "Summarize all the value points and ask for the close.",
    }

    # ── HUMAN ENGAGEMENT PATTERNS ──────────────────────────────────────
    ENGAGEMENT_PATTERNS = {
        "rapport_opener": (
            "Hi {name}, this is {agent_name} from Empire AI. "
            "I'm calling about the weather system that came through {location} "
            "recently — our predictive models flagged your property specifically."
        ),
        "urgency_escalator": (
            "I want to be upfront with you: the window for filing a "
            "comprehensive claim closes fast. After {deadline_hours} hours, "
            "insurers start asking whether the damage was pre-existing. "
            "We're dispatching teams to {location} right now."
        ),
        "social_proof": (
            "We've already inspected {nearby_count} properties in your area "
            "this week and found damage at {percent_with_damage}% of them. "
            "Your neighbor at {nearby_address} just signed up."
        ),
        "empathy_bridge": (
            "I know getting calls like this can feel overwhelming, especially "
            "after a storm. The last thing I want is to add to your stress. "
            "That's why we handle everything — the inspection, the paperwork, "
            "the insurance follow-up. You just say yes and we do the rest."
        ),
        "mirror_pacing": (
            "You mentioned {lead_concern} — that makes complete sense. "
            "A lot of property owners we talk to feel the same way. "
            "Here's what we've found works best for people in your situation..."
        ),
        "soft_close": (
            "How does your calendar look this week? I can have a specialist "
            "out to {location} within {response_time} hours. "
            "What works better for you — morning or afternoon?"
        ),
        "trial_close": (
            "If we can get a team out there by tomorrow to assess the "
            "property at no cost to you, is there any reason not to "
            "at least find out what we're dealing with?"
        ),
    }

    def __init__(
        self,
        *,
        ai_router: Any = None,
        synthetic_brain_url: str = "",
        synthetic_brain_key: str = "",
        agent_name: str = "Empire AI Predictive Cloud",
        default_deadline_hours: int = 48,
        human_closing: Any = None,
    ):
        self.ai_router = ai_router
        self.synthetic_brain_url = synthetic_brain_url or os.environ.get(
            "SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005"
        )
        self.synthetic_brain_key = synthetic_brain_key or os.environ.get(
            "SYNTHETIC_BRAIN_API_KEY", ""
        )
        self.agent_name = agent_name
        self.default_deadline_hours = default_deadline_hours
        self.human_closing = human_closing
        self.stats = {
            "scripts_generated": 0,
            "objections_handled": 0,
            "agi_failures": 0,
        }

    # ── AGI SCRIPT GENERATION ──────────────────────────────────────────

    async def generate_script(
        self,
        lead_name: str,
        location: str,
        niche: str,
        strategy: str,
        confidence: float,
        lead_mrr: float = 0.0,
        pain_points: Optional[list] = None,
        engagement_level: str = "full",
    ) -> Optional[str]:
        """
        Generate a personalized closing script using the synthetic brain or
        Ollama. Falls back to None if AGI is unavailable.

        Args:
            lead_name: Name of the lead/property
            location: City, state location
            niche: Industry niche
            strategy: SI-evolved strategy
            confidence: Brain confidence score 0.0-1.0
            lead_mrr: Known MRR of the lead (0 if unknown)
            pain_points: Key pain points to address
            engagement_level: 'basic', 'full', or 'premium'

        Returns:
            Generated script string, or None if AGI unavailable/failed.
        """
        # Try synthetic brain first
        if self.synthetic_brain_key:
            script = await self._generate_via_synthetic_brain(
                lead_name, location, niche, strategy,
                confidence, lead_mrr, pain_points, engagement_level,
            )
            if script:
                self.stats["scripts_generated"] += 1
                return script

        # Fall back to ai_router (Ollama-based)
        if self.ai_router:
            script = await self._generate_via_router(
                lead_name, location, niche, strategy,
                confidence, lead_mrr, pain_points, engagement_level,
            )
            if script:
                self.stats["scripts_generated"] += 1
                return script

        self.stats["agi_failures"] += 1
        return None

    async def _generate_via_synthetic_brain(
        self, lead_name: str, location: str, niche: str, strategy: str,
        confidence: float, lead_mrr: float, pain_points: Optional[list],
        engagement_level: str,
    ) -> Optional[str]:
        """Call the synthetic brain's LLM endpoint for script generation."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Build a rich context for the LLM
                pain_context = ""
                if pain_points:
                    pps = [p.get("pain_point", "") if isinstance(p, dict) else str(p) for p in pain_points[:3]]
                    pain_context = "\nKey pain points to address: " + "; ".join(pps)

                mrr_context = f"\nLead MRR: ${lead_mrr:.0f}/mo — {'high-value account, prioritize premium treatment' if lead_mrr >= 500 else 'standard account'}" if lead_mrr > 0 else ""

                prompt = (
                    f"Generate a persuasive, human-sounding sales script for an AI-powered "
                    f"outbound call. The call is to {lead_name} at {location}.\n"
                    f"Niche: {niche}\n"
                    f"Strategy: {strategy.replace('_', ' ').title()}\n"
                    f"Lead confidence score: {confidence:.2f}/1.0\n"
                    f"Engagement level: {engagement_level}{mrr_context}{pain_context}\n\n"
                    f"RULES:\n"
                    f"- Natural, conversational tone — NOT robotic or salesy\n"
                    f"- Start with a brief rapport-building opener (name, context, permission-based)\n"
                    f"- Include urgency without being pushy\n"
                    f"- End with a soft close / call to action\n"
                    f"- Max 4 sentences, keep it tight\n"
                    f"- Return ONLY the script text, no explanations\n"
                )

                r = await client.post(
                    f"{self.synthetic_brain_url}/api/v1/synthetic/generate_script",
                    json={"prompt": prompt, "max_tokens": 300},
                    headers={"X-API-Key": self.synthetic_brain_key},
                    timeout=25.0,
                )
                if r.status_code == 200:
                    data = r.json()
                    script = data.get("script") or data.get("text") or data.get("response", "")
                    if script and len(script.strip()) > 20:
                        return script.strip()
        except Exception as e:
            log.debug(f"[closing_expert] synthetic brain script gen failed: {e}")
        return None

    async def _generate_via_router(
        self, lead_name: str, location: str, niche: str, strategy: str,
        confidence: float, lead_mrr: float, pain_points: Optional[list],
        engagement_level: str,
    ) -> Optional[str]:
        """Fall back to the AI Router (Ollama) for script generation."""
        try:
            system_prompt = (
                "You are an expert B2B sales closer for a property restoration "
                "company. Generate a short, persuasive outbound call script. "
                "Use natural language, build rapport, create urgency, and end "
                "with a soft close. Return ONLY the script text, no labels."
            )
            user_prompt = (
                f"Lead: {lead_name}, Location: {location}, Niche: {niche}, "
                f"Strategy: {strategy}, Confidence: {confidence:.2f}. "
                f"Generate a 3-4 sentence call script."
            )
            result = await self.ai_router.generate_json(
                prompt=user_prompt,
                task="closing_expert.script",
                system=system_prompt,
                temperature=0.3,
                max_tokens=300,
            )
            if result and not result.get("_error"):
                script = result.get("script") or result.get("text") or ""
                if len(script.strip()) > 20:
                    return script.strip()
        except Exception as e:
            log.debug(f"[closing_expert] router script gen failed: {e}")
        return None

    # ── OBJECTION HANDLING ─────────────────────────────────────────────

    def handle_objection(
        self,
        objection_key: str,
        lead_name: str = "",
        location: str = "",
        niche: str = "",
    ) -> Optional[Dict]:
        """
        Handle a known objection with an expert response.

        Args:
            objection_key: Key from self.OBJECTIONS dict
            lead_name: Personalize the response
            location: Location context
            niche: Niche for niche-specific variations

        Returns:
            Dict with 'response' (script), 'technique', and 'label', or None
            if the objection is unknown.
        """
        obj = self.OBJECTIONS.get(objection_key)
        if not obj:
            return None

        self.stats["objections_handled"] += 1
        response = obj["response"]

        # Personalize with lead name and location
        if lead_name:
            response = response.replace("the property", f"{lead_name}")
            response = response.replace("your property", f"your property at {location}") if location else response

        return {
            "response": response,
            "technique": obj["technique"],
            "label": obj["label"],
        }

    def get_objection_response(
        self,
        objection_text: str,
        lead_name: str = "",
        location: str = "",
    ) -> Dict:
        """
        Match free-form objection text to the closest known objection key
        and return the expert response.

        Uses simple keyword matching. Falls back to a generic response if
        no match is found.
        """
        objection_text = objection_text.lower().strip()

        # Keyword matching
        keyword_map = [
            (["not interested", "no thanks", "don't need", "not for me", "stop calling"], "not_interested"),
            (["too expensive", "can't afford", "too much", "budget", "cost", "price"], "too_expensive"),
            (["think about", "call me later", "not now", "later", "maybe later", "some other time"], "need_to_think"),
            (["already have", "already using", "already working", "current contractor", "my guy"], "already_have_contractor"),
            (["not the owner", "talk to my", "not my decision", "manager", "boss", "husband", "wife"], "not_the_decision_maker"),
            (["busy", "in a meeting", "can't talk", "call back", "bad time"], "call_back_later"),
            (["scam", "legit", "real", "fraud", "trust", "verify"], "scam_worried"),
        ]

        for keywords, obj_key in keyword_map:
            if any(kw in objection_text for kw in keywords):
                result = self.handle_objection(obj_key, lead_name, location)
                if result:
                    return result

        # Generic fallback
        self.stats["objections_handled"] += 1
        return {
            "response": (
                f"I hear you, and I respect that. The only reason I'm calling "
                f"is that our AI — which has {90 if lead_name else 'a high'}% accuracy rate "
                f"on property damage prediction — flagged your property "
                f"specifically. Let me send you the details by text so you "
                f"can review it on your own time. Does that work?"
            ),
            "technique": "value_add",
            "label": "Generic — value add follow-up",
        }

    # ── HUMAN ENGAGEMENT LAYER ─────────────────────────────────────────

    def apply_engagement(
        self,
        script: str,
        lead_name: str = "",
        location: str = "",
        niche: str = "",
        strategy: str = "",
        confidence: float = 0.5,
        patterns: Optional[list] = None,
    ) -> str:
        """
        Wrap a base script with human engagement patterns.

        Args:
            script: The base script to enhance
            lead_name: Personalization context
            location: Location for geo-specific patterns
            niche: Niche for tailored engagement
            strategy: Strategy for tone alignment
            confidence: Confidence score affects which patterns are used
            patterns: List of pattern names to apply (default: auto-select based on confidence)

        Returns:
            Enhanced script with engagement patterns woven in.
        """
        if not patterns:
            # Auto-select patterns based on confidence
            patterns = []
            if confidence >= 0.8:
                # High confidence — use rapport opener + soft close
                patterns = ["rapport_opener", "soft_close"]
            elif confidence >= 0.6:
                # Medium confidence — add urgency + social proof
                patterns = ["rapport_opener", "urgency_escalator", "soft_close"]
            elif confidence >= 0.4:
                # Lower confidence — add empathy + trial close
                patterns = ["empathy_bridge", "trial_close"]
            else:
                # Low confidence — gentle nurture tone
                patterns = ["empathy_bridge", "soft_close"]

        # Apply patterns
        result_parts = []
        for pattern_name in patterns:
            template = self.ENGAGEMENT_PATTERNS.get(pattern_name)
            if not template:
                continue
            # Personalize the pattern
            personalized = template.replace("{name}", lead_name or "there")
            personalized = personalized.replace("{location}", location or "your area")
            personalized = personalized.replace("{agent_name}", self.agent_name)
            personalized = personalized.replace("{deadline_hours}", str(self.default_deadline_hours))
            personalized = personalized.replace("{nearby_count}", str(12))  # dynamic in future
            personalized = personalized.replace("{percent_with_damage}", str(67))  # dynamic in future
            personalized = personalized.replace("{nearby_address}", "123 Main St")  # dynamic in future
            personalized = personalized.replace("{lead_concern}", "the timeline")
            personalized = personalized.replace("{response_time}", "24")
            result_parts.append(personalized)

        # Insert the core script between opener and closer patterns
        enhanced = "\n\n".join(result_parts)

        # If we have a core script and patterns, weave them together
        if script and enhanced:
            # Put the core script between rapport opener and closing
            if len(result_parts) >= 2:
                enhanced = result_parts[0] + "\n\n" + script + "\n\n" + "\n\n".join(result_parts[1:])
        elif script:
            enhanced = script

        return enhanced.strip()

    # ── COMPLETE SCRIPT GENERATION (AGI + OBJECTIONS + ENGAGEMENT) ────

    async def build_complete_script(
        self,
        lead_name: str,
        location: str,
        niche: str,
        strategy: str,
        confidence: float,
        lead_mrr: float = 0.0,
        pain_points: Optional[list] = None,
        engagement_level: str = "full",
        known_objections: Optional[list] = None,
        lead_persona: str = "unknown",
    ) -> str:
        """
        Build a complete closing script with all three layers:

        1. AGI-generated core script (personalized to lead + strategy)
        2. Objection pre-buttals woven in (if known objections provided)
        3. Human engagement patterns (rapport, urgency, soft close)
        4. Human closing engine — models how real salespeople close

        Falls back gracefully if any layer fails.

        Returns the final script string.
        """

        # Step 0: If human_closing engine is wired, use it to enrich the script
        # with real human closing patterns selected by persona
        if self.human_closing:
            # Select the best closer persona for this lead
            closer_key = self.human_closing.select_closer_persona(
                lead_persona=lead_persona,
                lead_mrr=lead_mrr,
                strategy=strategy,
                confidence=confidence,
            )

            # If AGI generation is unavailable, use the human script directly
            if not self.synthetic_brain_key and not self.ai_router:
                human_script = self.human_closing.build_human_script(
                    lead_name=lead_name,
                    location=location,
                    niche=niche,
                    strategy=strategy,
                    confidence=confidence,
                    lead_mrr=lead_mrr,
                    lead_persona=lead_persona,
                    closer_persona=closer_key,
                )
                return human_script

        # Step 1: Generate AGI-powered core script
        core = await self.generate_script(
            lead_name=lead_name,
            location=location,
            niche=niche,
            strategy=strategy,
            confidence=confidence,
            lead_mrr=lead_mrr,
            pain_points=pain_points,
            engagement_level=engagement_level,
        )

        # If AGI failed, build from the template-based approach
        if not core:
            core = self._build_hardcoded_script(
                lead_name=lead_name,
                location=location,
                niche=niche,
                strategy=strategy,
                confidence=confidence,
            )

        # Step 2: Pre-butt known objections if provided
        if known_objections:
            for obj_key in known_objections:
                obj_response = self.handle_objection(obj_key, lead_name, location)
                if obj_response and obj_response["technique"] != "generic_fallback":
                    core += "\n\n" + obj_response["response"]

        # Step 3: Apply human engagement patterns
        enhanced = self.apply_engagement(
            script=core,
            lead_name=lead_name,
            location=location,
            niche=niche,
            strategy=strategy,
            confidence=confidence,
        )

        return enhanced

    # ── HARDCODED FALLBACK (same logic as original _build_live_script) ──

    @staticmethod
    def _build_hardcoded_script(
        lead_name: str,
        location: str,
        niche: str,
        strategy: str,
        confidence: float,
    ) -> str:
        """Template-based fallback when AGI generation is unavailable."""
        if strategy == "AGGRESSIVE_STRIKE":
            opener = "urgent storm alert"
            tone = "We have crews standing by in your area and can dispatch immediately."
        elif strategy == "RECALL_SNIPER":
            opener = "targeted property assessment"
            tone = "Our predictive models identified your facility as high-priority for storm response."
        elif strategy == "FINANCIAL_STRIKE":
            opener = "verified insurance dispatch"
            tone = "We specialize in maximizing commercial claims — our average settlement is 3x higher."
        elif strategy == "UGLY_BANNER":
            opener = "storm response program"
            tone = "Our specialists are available to assess your property at no upfront cost."
        else:
            opener = "storm damage notification"
            tone = "A specialist is available to discuss your property's needs."

        if confidence >= 0.85:
            urgency = "This is time-sensitive — storm windows close fast."
        elif confidence >= 0.7:
            urgency = "Please hold while we connect you to a specialist."
        else:
            urgency = "We'll follow up with more details shortly."

        return (
            f"Hello, this is Empire AI Predictive Cloud with an {opener}. "
            f"Our weather intelligence detected severe storm activity near {location}. "
            f"We've identified {lead_name} as a match for our {strategy.replace('_', ' ').title()} program. "
            f"{tone} {urgency}"
        )


class AICloser:
    """
    AGI-powered sales closer that orchestrates the full voice pipeline.

    Dependencies (all injected — no hard imports):
      - brain_decider:    BrainDecider instance (Go/No-Go scoring)
      - voice_router:     VoiceRouter instance (static NCCO + streaming calls)
      - sms_engine:       SMSEngine instance (nurture fallback, optional)
      - email_engine:     EmailEngine instance (nurture fallback, optional)
      - get_db:           Callable returning Supabase client (for logging)
      - operator_number:  phone number for warm-forward connect (optional)
      - suite_subscriptions: SuiteSubscriptionEngine instance (MRR lookup, optional)
      - closing_expert:    ClosingExpert instance (AGI scripts, objection handling, engagement)
    """

    def __init__(
        self,
        *,
        brain_decider: Any = None,
        voice_router: Any = None,
        sms_engine: Any = None,
        email_engine: Any = None,
        get_db: Optional[Callable] = None,
        operator_number: str = "",
        stream_confidence: float = AGI_STREAM_THRESHOLD,
        static_confidence: float = STATIC_CALL_THRESHOLD,
        default_voice: str = DEFAULT_VOICE,
        pain_points: Any = None,
        suite_subscriptions: Any = None,
        closing_expert: Any = None,
        human_closing: Any = None,
    ):
        self.brain_decider = brain_decider
        self.voice_router = voice_router
        self.sms_engine = sms_engine
        self.email_engine = email_engine
        self.get_db = get_db
        self.operator_number = operator_number or os.environ.get("EMPIRE_OPERATOR_NUMBER", "")
        self.stream_confidence = stream_confidence
        self.static_confidence = static_confidence
        self.default_voice = default_voice
        self.pain_points = pain_points
        self.suite_subscriptions = suite_subscriptions
        self.closing_expert = closing_expert
        self.human_closing = human_closing or HumanClosingEngine()

        # MRR stats for prioritization
        self._mrr_cache: Dict[str, float] = {}

        # Lazy-loaded deps (imported on first use so the module is importable
        # without the full stack being wired)
        self._agi_governor = None
        self._streaming_agent = None
        self._synthetic_brain_url = os.environ.get("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")
        self._synthetic_brain_key = os.environ.get("SYNTHETIC_BRAIN_API_KEY", "")
        self._public_base_url = os.environ.get("EMPIRE_PUBLIC_BASE_URL", "")

        self.stats = {
            "leads_processed": 0,
            "brain_go": 0,
            "brain_no_go": 0,
            "agi_stream_calls": 0,
            "static_calls": 0,
            "nurture_routed": 0,
            "errors": 0,
            "multi_turn_calls": 0,
            "objection_turns": 0,
        }

        # Track current MRR tier for the active lead (set in close())
        self._current_tier: Optional[dict] = None

    # ── LAZY DEP LOADING ────────────────────────────────────────────
    def _ensure_governor(self):
        """Load the AGI Governor singleton instance (not the class)."""
        if self._agi_governor is None:
            from empire_agi_governor import governor as _gov
            self._agi_governor = _gov

    # ── MAIN CLOSE METHOD ───────────────────────────────────────────
    async def close(
        self,
        lead: Dict,
        alert_summary: Optional[Dict] = None,
        niche: Optional[str] = None,
        thinking_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full AI closer pipeline on a lead.

        Args:
            lead: dict with keys: name/warehouse_name, phone, email, address,
                  city, state, asset_value, damage_severity, source, type_tags
            alert_summary: optional storm alert context (event, severity, area)
            niche: optional explicit niche override (auto-inferred if omitted)

        Returns:
            dict with: decision, action, confidence, strategy, reasoning,
                       call_result (if call placed), niche
        """
        self.stats["leads_processed"] += 1

        # ── Normalize lead shape ────────────────────────────────────
        name = lead.get("warehouse_name") or lead.get("name") or "Unknown"
        phone = lead.get("phone") or lead.get("phone2") or ""
        email = lead.get("email") or ""
        address = lead.get("address") or ""
        city = lead.get("city") or ""
        state = lead.get("state") or ""

        # ── Infer niche ─────────────────────────────────────────────
        if not niche:
            niche = self._infer_niche(lead, alert_summary)

        # ── Phase 1: BrainDecider scores the lead ───────────────────
        if not self.brain_decider:
            log.warning("[ai_closer] brain_decider not wired — defaulting to GO")
            decision = {"decision": "GO", "confidence": 0.5, "reasoning": "brain unavailable"}
        else:
            alert_ctx = alert_summary or {
                "event": "Inbound Lead",
                "severity": lead.get("damage_severity") or "Moderate",
                "urgency": "Normal",
                "area": f"{city}, {state}".strip(", "),
            }
            # Pass thinking_level through (None = let BrainDecider handle resolution)
            # BrainDecider.resolve_thinking_level() checks explicit > personality-niche > asset value
            decision = await self.brain_decider.decide(
                target={
                    "warehouse_name": name,
                    "address": address,
                    "city": city,
                    "phone": phone,
                    "email": email,
                    "website": lead.get("website", ""),
                    "raw_tags": lead.get("type_tags") or {"types": ["commercial"]},
                },
                alert_summary=alert_ctx,
                thinking_level=thinking_level,
            )
            # Normalize decision keys
            decision["decision"] = (decision.get("decision") or "NO_GO").upper()
            try:
                decision["confidence"] = max(0.0, min(1.0, float(decision.get("confidence", 0))))
            except (TypeError, ValueError):
                decision["confidence"] = 0.5

        # ── Phase 2: Select SI-evolved strategy ─────────────────────
        strategy = await self._select_strategy(niche, decision)

        confidence = decision["confidence"]

        # Dynamic threshold adaptation per lane: successful lanes get
        # lower thresholds (more aggressive calls), struggling lanes get
        # higher thresholds (more conservative).
        self._ensure_governor()
        win_rate = 0.0
        if self._agi_governor and hasattr(self._agi_governor, "get_niche_win_rate"):
            win_rate = self._agi_governor.get_niche_win_rate(niche)
        adaptation_shift = 0.0
        if win_rate >= 0.20:
            adaptation_shift = -0.15  # more aggressive: lower thresholds
        elif win_rate >= 0.10:
            adaptation_shift = -0.05
        elif win_rate < 0.05:
            adaptation_shift = 0.10   # more conservative: raise thresholds

        # ── MRR-aware engagement tier ──────────────────────────────
        # Higher-value accounts get escalated to higher-touch channels:
        #   BROADCAST → nurture (SMS/email)
        #   STARTER   → static NCCO call + full script
        #   GROWTH    → static call + AGI full script
        #   PREMIUM   → live Kokoro streaming + AGI premium script
        #   ENTERPRISE→ live streaming + AGI premium + human operator notify
        self._lead_mrr = self._lookup_lead_mrr(lead)
        mrr_tier = get_mrr_tier(self._lead_mrr)
        tier_bias = mrr_tier["routing_bias"]
        self._current_tier = mrr_tier

        dynamic_stream_thresh = max(0.3, min(0.95, self.stream_confidence + adaptation_shift - tier_bias))
        dynamic_static_thresh = max(0.15, min(0.80, self.static_confidence + adaptation_shift - tier_bias))

        # ── Phase 3: Route based on decision + confidence ───────────
        if decision["decision"] == "GO" and confidence >= dynamic_stream_thresh:
            result = await self._dispatch_agi_stream(lead, decision, strategy, niche)
            self.stats["brain_go"] += 1
            # Only count stream if it wasn't blocked or fell back
            if result.get("action") == "agi_stream_call":
                self.stats["agi_stream_calls"] += 1
            elif result.get("action") == "static_call":
                self.stats["static_calls"] += 1

        elif decision["decision"] == "GO" and confidence >= dynamic_static_thresh:
            result = await self._dispatch_static_call(lead, decision, strategy, niche)
            self.stats["brain_go"] += 1
            if result.get("action") == "static_call":
                self.stats["static_calls"] += 1

        elif decision["decision"] == "GO":
            # Low confidence GO → nurture (SMS/Email drip)
            result = await self._dispatch_nurture(lead, decision, strategy, niche)
            self.stats["brain_go"] += 1
            self.stats["nurture_routed"] += 1

        else:
            # NO_GO → log and skip
            self.stats["brain_no_go"] += 1
            result = {
                "action": "no_go",
                "decision": decision["decision"],
                "confidence": confidence,
                "reasoning": decision.get("reasoning", ""),
                "strategy": strategy,
                "niche": niche,
                "lead_name": name,
                "lead_phone": phone,
            }

        # ── Phase 4: Record outcome to SI strategy evolution ────────
        await self._record_outcome(strategy, niche, result)

        # ── Phase 5: Persist decision log ───────────────────────────
        self._log_decision(lead, decision, strategy, niche, result)

        return result

    # ── STRATEGY SELECTION (AGI GOVERNOR + SI GENOME) ───────────────
    async def _select_strategy(self, niche: str, decision: Dict) -> str:
        """Pick the best SI-evolved strategy for this niche."""
        self._ensure_governor()
        try:
            # Governor already delegates to the shared SI StrategyEvolution instance
            if self._agi_governor:
                best = self._agi_governor.strategy_for_niche(niche)
                if best:
                    return best
        except Exception as e:
            log.debug(f"[ai_closer] strategy lookup via governor failed: {e}")

        # Ultimate fallback
        return "AGGRESSIVE_STRIKE"

    # ── PAIN POINTS HELPER ─────────────────────────────────────
    def _get_pain_points_used(self, niche: str) -> list:
        """Return top pain point IDs for a niche. Safe no-op if library not wired."""
        if not self.pain_points:
            return []
        try:
            return self.pain_points.get_script_pain_points(niche)
        except Exception:
            return []

    # ── AGI STREAM DISPATCH (live Kokoro TTS) ───────────────────────
    async def _dispatch_agi_stream(
        self, lead: Dict, decision: Dict, strategy: str, niche: str
    ) -> Dict:
        """High-confidence GO → live Kokoro TTS via synthetic_brain WebSocket."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        name = lead.get("warehouse_name") or lead.get("name") or "the property"
        city = lead.get("city") or "your area"
        state = lead.get("state") or ""
        location = f"{city}, {state}" if state else city

        # ── Compliance check before calling (same as static path) ───
        if phone:
            blocked = await self._run_compliance_check(phone)
            if blocked:
                return blocked

        # Build the live-call pitch script
        script = self._build_live_script(name, location, decision, strategy, niche)

        # Register the stream with synthetic_brain
        voice_id = None
        ws_url = None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Build the register_stream payload
                stream_payload = {
                    "script": script,
                    "voice": self.default_voice,
                    "public_base_url": self._public_base_url,
                }

                # If multi-turn is enabled, tell the synthetic brain to
                # send objection events through the WebSocket (same ws_url).
                # The _run_multi_turn_conversation() method listens on the WS
                # for objection/transcript events and routes them through
                # ClosingExpert for expert responses.
                if MAX_OBJECTION_TURNS > 0:
                    stream_payload["multi_turn"] = {
                        "enabled": True,
                        "max_turns": MAX_OBJECTION_TURNS,
                        "turn_timeout_s": OBJECTION_TURN_TIMEOUT,
                    }

                r = await client.post(
                    f"{self._synthetic_brain_url}/api/v1/synthetic/register_stream",
                    json=stream_payload,
                    headers={"X-API-Key": self._synthetic_brain_key},
                )
                if r.status_code == 200:
                    reg = r.json()
                    voice_id = reg.get("voice_id")
                    ws_url = reg.get("ws_url")
                    log.info(f"[ai_closer] stream registered: voice_id={voice_id}")
                else:
                    log.warning(f"[ai_closer] register_stream failed ({r.status_code}): {r.text[:200]}")
        except Exception as e:
            log.warning(f"[ai_closer] register_stream error: {e}")

        if not ws_url or not self.voice_router:
            log.warning("[ai_closer] stream registration failed — falling back to static call")
            return await self._dispatch_static_call(lead, decision, strategy, niche)

        # Place the streaming strike via VoiceRouter
        call_result = {}
        try:
            call_result = await self.voice_router.place_streaming_strike(
                to_number=phone,
                ws_url=ws_url,
                target_address=lead.get("address", ""),
                operator_number=self.operator_number,
                brain_decision=decision,
            )
        except Exception as e:
            log.error(f"[ai_closer] streaming strike failed: {e}")
            self.stats["errors"] += 1
            call_result = {"ok": False, "error": str(e)}

        # If streaming call failed, fall back to static NCCO
        if not call_result.get("ok"):
            log.warning("[ai_closer] streaming call failed — falling back to static call")
            return await self._dispatch_static_call(lead, decision, strategy, niche)

        # ── Multi-turn objection handling ────────────────────────────
        # After the call is connected, run the objection loop as a background
        # task so the dispatch returns immediately (the call is already live
        # via voice_router). The loop listens for objection events over the
        # WebSocket, routes them through ClosingExpert, and sends expert
        # responses back for Kokoro TTS delivery. Stats are updated when the
        # loop completes.
        #
        # Note: This depends on the synthetic brain supporting multiple WS
        # clients on the same stream, or the voice_router releasing the WS
        # connection after call setup. If the WS connect fails, the loop
        # silently returns 0 — no breakage, but multi-turn won't activate.
        asyncio.create_task(self._run_multi_turn_conversation(
            ws_url=ws_url,
            lead_name=name,
            location=location,
        ))

        # ── Track pain points used ──────────────────────────────────
        pain_points_used = self._get_pain_points_used(niche)

        return {
            "action": "agi_stream_call",
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "strategy": strategy,
            "niche": niche,
            "script": script[:200],
            "voice": self.default_voice,
            "voice_id": voice_id,
            "ws_url": ws_url,
            "call_result": call_result,
            "pain_points_used": pain_points_used,
            "lead_name": name,
            "lead_phone": phone,
            "multi_turn": {
                "objection_turns": "pending",
                "max_turns": MAX_OBJECTION_TURNS,
            },
        }

    # ── MULTI-TURN OBJECTION LOOP ─────────────────────────────────────
    async def _run_multi_turn_conversation(
        self,
        ws_url: str,
        lead_name: str,
        location: str,
    ) -> int:
        """
        Run multi-turn objection handling over the streaming call's WebSocket.

        After the streaming call is connected via VoiceRouter + synthetic brain,
        this method connects to the same WebSocket and listens for objection or
        transcript events from the lead. Each objection is routed through
        ClosingExpert's handle_lead_objection(), and the expert response is sent
        back through the WebSocket for Kokoro TTS delivery to the lead.

        Args:
            ws_url: WebSocket URL from synthetic_brain register_stream
            lead_name: Lead name for personalization
            location: Location for personalization

        Returns:
            Number of objection turns handled (0 if no objections received
            or multi-turn is disabled/unavailable).
        """
        max_turns = MAX_OBJECTION_TURNS
        turn_timeout = OBJECTION_TURN_TIMEOUT

        if max_turns <= 0 or not ws_url:
            return 0

        turns = 0

        try:
            import json

            try:
                import websockets
            except ImportError:
                log.debug("[ai_closer] websockets not installed — multi-turn disabled")
                return 0

            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
                max_size=2 ** 16,  # 64KB max message
            ) as ws:
                while turns < max_turns:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=turn_timeout)
                        data = json.loads(msg)

                        msg_type = data.get("type", "")
                        text = data.get("text", "")

                        if not text:
                            continue

                        if msg_type in ("objection", "transcript"):
                            log.info(
                                f"[ai_closer] multi-turn objection (turn {turns + 1}): "
                                f"{text[:100]}"
                            )

                            response = self.handle_lead_objection(
                                objection_text=text,
                                lead_name=lead_name,
                                location=location,
                            )

                            if not response or not response.get("response"):
                                log.debug(
                                    "[ai_closer] no expert response for objection, "
                                    "continuing"
                                )
                                continue

                            # Send the expert response back for Kokoro TTS
                            await ws.send(json.dumps({
                                "type": "tts",
                                "text": response["response"],
                            }))

                            turns += 1
                            log.info(
                                f"[ai_closer] objection response sent (turn {turns}): "
                                f"technique={response.get('technique', 'unknown')}"
                            )

                    except asyncio.TimeoutError:
                        # No objection within timeout — call likely ended
                        log.debug(
                            f"[ai_closer] multi-turn timeout after {turns} turns"
                        )
                        break
                    except json.JSONDecodeError:
                        log.debug("[ai_closer] multi-turn non-JSON message, skipping")
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        log.debug("[ai_closer] multi-turn WebSocket closed")
                        break

        except Exception as e:
            log.debug(f"[ai_closer] multi-turn conversation error: {e}")

        # Self-report stats since the caller fires this as a background task
        if turns > 0:
            self.stats["multi_turn_calls"] += 1
            self.stats["objection_turns"] += turns

        return turns

    # ── STATIC CALL DISPATCH (Vonage built-in TTS) ──────────────────
    async def _dispatch_static_call(
        self, lead: Dict, decision: Dict, strategy: str, niche: str
    ) -> Dict:
        """Medium-confidence GO → static NCCO call via VoiceRouter."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        name = lead.get("warehouse_name") or lead.get("name") or "Unknown"

        if not phone:
            return {
                "action": "no_phone",
                "decision": decision["decision"],
                "confidence": decision["confidence"],
                "reasoning": "no phone number available",
                "strategy": strategy,
                "niche": niche,
                "lead_name": name,
            }

        # Compliance check before calling
        blocked = await self._run_compliance_check(phone)
        if blocked:
            return blocked

        call_result = {}
        if self.voice_router:
            try:
                call_result = await self.voice_router.place_strike_call(
                    to_number=phone,
                    target_address=lead.get("address", ""),
                    asset_value=float(lead.get("asset_value") or 0),
                    operator_number=self.operator_number,
                    brain_decision=decision,
                )
            except Exception as e:
                log.error(f"[ai_closer] static call failed: {e}")
                self.stats["errors"] += 1
                call_result = {"ok": False, "error": str(e)}
        else:
            call_result = {"ok": False, "error": "voice_router not wired"}

        # ── Track pain points used ──────────────────────────────────
        pain_points_used = self._get_pain_points_used(niche)

        return {
            "action": "static_call",
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "strategy": strategy,
            "niche": niche,
            "call_result": call_result,
            "pain_points_used": pain_points_used,
            "lead_name": name,
            "lead_phone": phone,
        }

    # ── NURTURE DISPATCH (SMS/Email) ────────────────────────────────
    async def _dispatch_nurture(
        self, lead: Dict, decision: Dict, strategy: str, niche: str
    ) -> Dict:
        """Low-confidence GO or NO_GO → nurture via SMS/Email drip."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        email = lead.get("email") or ""
        name = lead.get("warehouse_name") or lead.get("name") or "Unknown"

        sms_result = None
        email_result = None

        # Try SMS if phone available and sms_engine wired
        if phone and self.sms_engine:
            try:
                body = (
                    f"Empire AI: Storm activity detected near your property. "
                    f"{name}, our {niche} program may apply. "
                    f"Reply STOP to opt out."
                )
                sms_result = await self.sms_engine.send_sms(phone, body)
            except Exception as e:
                log.warning(f"[ai_closer] SMS nurture failed: {e}")

        # Try email if available and email_engine wired
        if email and self.email_engine:
            try:
                email_result = await self.email_engine.enroll(
                    email=email,
                    target_addr=lead.get("address", ""),
                    sequence_type=NURTURE_STORM if "Storm" in niche else NURTURE_GENERIC,
                    meta={"niche": niche, "strategy": strategy},
                )
            except Exception as e:
                log.warning(f"[ai_closer] email nurture failed: {e}")

        # ── Track pain points used ──────────────────────────────────
        pain_points_used = self._get_pain_points_used(niche)

        return {
            "action": "nurture",
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "strategy": strategy,
            "niche": niche,
            "sms_result": sms_result,
            "email_result": email_result,
            "pain_points_used": pain_points_used,
            "lead_name": name,
            "lead_phone": phone,
            "lead_email": email,
        }

    # ── OUTCOME RECORDING (SI STRATEGY EVOLUTION FEEDBACK) ──────────
    async def _record_outcome(self, strategy: str, niche: str, result: Dict):
        """Feed the outcome back to the AGI Governor → StrategyEvolution + PainPoints."""
        self._ensure_governor()
        action = result.get("action", "")
        success = action in ("agi_stream_call", "static_call")

        # Look up the lead's actual MRR from suite subscriptions
        lead_mrr = 0.0
        lead_phone = result.get("lead_phone", "")
        if lead_phone and self.suite_subscriptions:
            lead_mrr = self._lookup_mrr_by_phone(lead_phone)

        # Estimate revenue per outcome: use actual MRR if available, else a
        # percentage-based estimate derived from call success
        revenue = 0.0
        call_result = result.get("call_result", {})
        if isinstance(call_result, dict) and call_result.get("ok"):
            if lead_mrr > 0:
                revenue = lead_mrr  # use the account's actual MRR
            else:
                revenue = 500.0  # base estimate per connected call

        try:
            if self._agi_governor and hasattr(self._agi_governor, "record_strategy_outcome"):
                self._agi_governor.record_strategy_outcome(strategy, niche, success, revenue)
        except Exception as e:
            log.debug(f"[ai_closer] outcome recording failed: {e}")

        # ── Record pain point outcomes ──────────────────────────────
        if self.pain_points:
            pain_points_used = result.get("pain_points_used", [])
            if pain_points_used:
                try:
                    self.pain_points.record_outcome(niche, pain_points_used, success)
                except Exception as e:
                    log.debug(f"[ai_closer] pain point outcome failed: {e}")

    # ── DECISION LOGGING ────────────────────────────────────────────
    def _log_decision(
        self, lead: Dict, decision: Dict, strategy: str, niche: str, result: Dict
    ):
        """Persist the full closer decision to ai_closer_decisions."""
        if not self.get_db:
            return
        try:
            pain_points_used = result.get("pain_points_used", [])
            db = self.get_db()
            db.table("ai_closer_decisions").insert({
                "lead_name": lead.get("warehouse_name") or lead.get("name", ""),
                "lead_phone": lead.get("phone") or lead.get("phone2", ""),
                "lead_email": lead.get("email", ""),
                "lead_address": lead.get("address", ""),
                "lead_city": lead.get("city", ""),
                "niche": niche,
                "brain_decision": decision.get("decision", ""),
                "brain_confidence": decision.get("confidence", 0),
                "brain_reasoning": (decision.get("reasoning", "") or "")[:300],
                "selected_strategy": strategy,
                "action_taken": result.get("action", ""),
                "pain_points_used": pain_points_used,
                "result_summary": result,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug(f"[ai_closer] decision log failed (table may not exist): {e}")

    # ── LIVE SCRIPT BUILDER ─────────────────────────────────────────
    def _build_live_script(
        self, name: str, location: str, decision: Dict, strategy: str, niche: str = ""
    ) -> str:
        """Build the live-call pitch script.

        Uses the ClosingExpert (AGI-generated, objection-aware, engagement-enhanced)
        when available. Falls back to the hardcoded strategy-based template when
        the expert is not wired or fails.
        """
        confidence = decision.get("confidence", 0)

        # Determine MRR tier and engagement level for this lead
        # Uses the lead's actual MRR (stored by close() in self._lead_mrr)
        lead_mrr = getattr(self, '_lead_mrr', 0.0) or 0.0
        mrr_tier = get_mrr_tier(lead_mrr)
        engagement_level = mrr_tier["engagement_level"]

        # Try to get pain points for the AGI pipeline
        pain_points_list = None
        if self.pain_points and niche:
            try:
                pain_points_list = self.pain_points.get_script_pain_points(niche)
            except Exception:
                pass

        # Use ClosingExpert if wired — AGI-generated, engagement-enhanced, objection-aware
        if self.closing_expert:
            try:
                # Wire the human_closing engine into ClosingExpert if it has one
                # but hasn't been initialized with it
                if self.human_closing and not self.closing_expert.human_closing:
                    self.closing_expert.human_closing = self.human_closing

                # Detect lead persona from available context (name, location, type)
                lead_persona = "unknown"
                if self.human_closing:
                    # Combine available lead data for persona signal
                    signal_text = f"{name} {location} {niche} {strategy}"
                    lead_persona = self.human_closing.detect_lead_persona(signal_text)

                script = self.closing_expert.build_complete_script(
                    lead_name=name,
                    location=location,
                    niche=niche,
                    strategy=strategy,
                    confidence=confidence,
                    lead_mrr=lead_mrr,
                    engagement_level=engagement_level,
                    pain_points=pain_points_list,
                    lead_persona=lead_persona,
                )
                return script
            except Exception as e:
                log.debug(f"[ai_closer] closing_expert.build_complete_script failed — using fallback: {e}")

        # ── Fallback: hardcoded strategy-based template ──────────────
        if strategy == "AGGRESSIVE_STRIKE":
            opener = "urgent storm alert"
            tone = "We have crews standing by in your area and can dispatch immediately."
        elif strategy == "RECALL_SNIPER":
            opener = "targeted property assessment"
            tone = "Our predictive models identified your facility as high-priority for storm response."
        elif strategy == "FINANCIAL_STRIKE":
            opener = "verified insurance dispatch"
            tone = "We specialize in maximizing commercial claims — our average settlement is 3x higher."
        elif strategy == "UGLY_BANNER":
            opener = "storm response program"
            tone = "Our specialists are available to assess your property at no upfront cost."
        else:
            opener = "storm damage notification"
            tone = "A specialist is available to discuss your property's needs."

        if confidence >= 0.85:
            urgency = "This is time-sensitive — storm windows close fast."
        elif confidence >= 0.7:
            urgency = "Please hold while we connect you to a specialist."
        else:
            urgency = "We'll follow up with more details shortly."

        base_script = (
            f"Hello, this is Empire AI Predictive Cloud with an {opener}. "
            f"Our weather intelligence detected severe storm activity near {location}. "
            f"We've identified {name} as a match for our {strategy.replace('_', ' ').title()} program. "
            f"{tone} {urgency}"
        )

        # ── Inject pain points if library is wired ──────────────────
        if self.pain_points and niche:
            try:
                base_script = self.pain_points.inject_pain_points(niche, base_script)
            except Exception as e:
                log.debug(f"[ai_closer] pain point injection skipped: {e}")

        return base_script

    # ── NICHE INFERENCE ─────────────────────────────────────────────
    @staticmethod
    def _infer_niche(lead: Dict, alert_summary: Optional[Dict] = None) -> str:
        """Infer the niche from lead metadata or alert context."""
        # Explicit niche in lead metadata
        try:
            meta = lead.get("meta") or {}
            explicit = meta.get("niche") if isinstance(meta, dict) else None
            if explicit:
                return str(explicit)[:80]
        except Exception:
            pass

        # From alert_summary event
        if alert_summary:
            event = (alert_summary.get("event") or "").lower()
            niche_map = [
                (("tornado",), "Tornado Damage Repair"),
                (("hurricane",), "Hurricane Damage Restoration"),
                (("hail",), "Hail Damage Repair"),
                (("flood", "flash flood"), "Flood Damage Restoration"),
                (("thunderstorm", "severe storm", "wind"), "Storm Damage Restoration"),
            ]
            for keywords, niche in niche_map:
                if any(kw in event for kw in keywords):
                    return niche
            if any(kw in event for kw in ("storm", "warning", "watch")):
                return "Storm Damage Restoration"

        # From lead type tags
        types = lead.get("type_tags", {}).get("types", []) if isinstance(lead.get("type_tags"), dict) else []
        if "roofing" in types or "contractor" in types:
            return "Roofing Restoration"
        if "warehouse" in types or "industrial" in types:
            return "Storm Damage Restoration"
        if "legal" in types or "medical" in types:
            return "Legal Intake"

        return "Roofing Restoration"

    # ── COMPLIANCE CHECK HELPER ────────────────────────────────────
    async def _run_compliance_check(self, phone: str) -> Optional[Dict]:
        """Run TCPA/DNC/calling-hours compliance check. Returns block dict if blocked."""
        try:
            from empire_outbound_dialer import compliance_check, ComplianceBlock
            compliance_check(phone)
        except ImportError:
            pass  # compliance module not available
        except ComplianceBlock as e:
            log.info(f"[ai_closer] compliance blocked call to {phone}: {e}")
            return {
                "action": "compliance_blocked",
                "block_reason": str(e),
                "lead_phone": phone,
            }
        except Exception as e:
            # Non-ComplianceBlock error (e.g. Supabase timeout) — log but don't block
            log.warning(f"[ai_closer] compliance check errored (allowing): {e}")
        return None


    # ── OBJECTION HANDLING ──────────────────────────────────────────────
    def handle_lead_objection(
        self,
        objection_text: str,
        lead_name: str = "",
        location: str = "",
    ) -> Optional[Dict]:
        """
        Route an objection from the call pipeline to the ClosingExpert for
        an expert response. Returns the response dict if the expert is wired,
        or None if not available.
        """
        if not self.closing_expert:
            return None
        try:
            return self.closing_expert.get_objection_response(
                objection_text=objection_text,
                lead_name=lead_name,
                location=location,
            )
        except Exception as e:
            log.debug(f"[ai_closer] objection handling failed: {e}")
            return None

    def available_objections(self) -> Dict:
        """Return the list of known objections with labels (for UI)."""
        if not self.closing_expert:
            return {}
        try:
            return {
                k: {"label": v["label"], "technique": v["technique"]}
                for k, v in self.closing_expert.OBJECTIONS.items()
            }
        except Exception:
            return {}

    # ── MRR LOOKUP HELPERS ─────────────────────────────────────────────
    def _lookup_mrr_by_phone(self, phone: str) -> float:
        """Look up the MRR for a lead by phone number from the suite subscriptions.
        Iterates active subscriptions and matches by phone if stored.
        Returns 0.0 if not found or not wired."""
        if not self.suite_subscriptions or not phone:
            return 0.0
        phone = phone.strip()
        # Check cache first
        if phone in self._mrr_cache:
            return self._mrr_cache[phone]
        try:
            subs = self.suite_subscriptions.list_subscriptions(status="ACTIVE")
            for sub in subs:
                # Subscriptions store customer_account_id; we match on lead phone
                # if the subscription notes or metadata contain the phone.
                sub_phone = ""
                notes = sub.get("notes", "") or ""
                # Check if subscription metadata has a phone field
                meta = sub.get("meta", {}) or {}
                if isinstance(meta, dict):
                    sub_phone = meta.get("phone", "")
                if not sub_phone and notes and phone in notes:
                    sub_phone = phone
                if sub_phone == phone:
                    mrr = float(sub.get("monthly_recurring_revenue", 0) or 0)
                    self._mrr_cache[phone] = mrr
                    return mrr
        except Exception as e:
            log.debug(f"[ai_closer] MRR lookup by phone failed: {e}")
        self._mrr_cache[phone] = 0.0
        return 0.0

    def _lookup_lead_mrr(self, lead: Dict) -> float:
        """Look up MRR for a lead dict, trying phone and email."""
        phone = lead.get("phone") or lead.get("phone2") or ""
        if phone:
            mrr = self._lookup_mrr_by_phone(phone)
            if mrr > 0:
                return mrr
        return 0.0

    @staticmethod
    def prioritize_leads(leads: list, closer: "AICloser" = None) -> list:
        """Sort leads by estimated MRR (highest first) so high-value
        accounts are processed first. If no closer instance is provided
        (no MRR lookup), falls back to original order.

        Args:
            leads: list of lead dicts
            closer: optional AICloser instance for MRR lookup

        Returns:
            Leads sorted by descending MRR (highest value first).
        """
        if not closer or not closer.suite_subscriptions:
            return leads
        try:
            def _mrr_key(lead: Dict) -> float:
                phone = lead.get("phone") or lead.get("phone2") or ""
                if not phone:
                    return 0.0
                return closer._lookup_mrr_by_phone(phone)
            return sorted(leads, key=_mrr_key, reverse=True)
        except Exception:
            return leads

    # ── SNAPSHOT FOR DASHBOARD ──────────────────────────────────────
    def snapshot(self) -> Dict:
        """Return closer stats for the SPA / mission control."""
        return {
            **self.stats,
            "stream_confidence": self.stream_confidence,
            "static_confidence": self.static_confidence,
            "voice_router_wired": self.voice_router is not None,
            "brain_decider_wired": self.brain_decider is not None,
            "sms_engine_wired": self.sms_engine is not None,
            "email_engine_wired": self.email_engine is not None,
            "synthetic_brain_url": self._synthetic_brain_url,
            "operator_number_configured": bool(self.operator_number),
            "closing_expert_wired": self.closing_expert is not None,
            "objections_available": len(self.available_objections()) if hasattr(self, 'available_objections') else 0,
            "mrr_tier_active": self._current_tier.get("name", "BROADCAST") if self._current_tier else "BROADCAST",
            "mrr_tiers_configured": [t["name"] for t in MRR_TIERS],
        }


# ── CONVENIENCE: DIRECT SCORE + ROUTE (NO CALL) ─────────────────────
async def ai_closer_score_only(
    closer: AICloser,
    lead: Dict,
    alert_summary: Optional[Dict] = None,
    niche: Optional[str] = None,
    thinking_level: Optional[str] = None,
) -> Dict:
    """
    Score a lead through brain + strategy selection without placing a call.
    Useful for pre-qualification (e.g. in the SPA pipeline view).

    thinking_level: "low" | "medium" | "max" — controls cognitive depth.
    Auto-selected based on asset value if not provided.
    """
    name = lead.get("warehouse_name") or lead.get("name") or "Unknown"
    if not niche:
        niche = closer._infer_niche(lead, alert_summary)

    # Brain score — pass thinking_level through (None = let BrainDecider resolve)
    if not closer.brain_decider:
        decision = {"decision": "GO", "confidence": 0.5, "reasoning": "brain unavailable"}
    else:
        alert_ctx = alert_summary or {
            "event": "Inbound Lead",
            "severity": "Moderate",
            "urgency": "Normal",
            "area": f"{lead.get('city', '')}, {lead.get('state', '')}".strip(", "),
        }
        decision = await closer.brain_decider.decide(
            target={
                "warehouse_name": name,
                "address": lead.get("address", ""),
                "city": lead.get("city", ""),
                "phone": lead.get("phone") or lead.get("phone2", ""),
                "email": lead.get("email", ""),
                "website": lead.get("website", ""),
                "raw_tags": lead.get("type_tags") or {"types": ["commercial"]},
            },
            alert_summary=alert_ctx,
            thinking_level=thinking_level,
        )
        decision["decision"] = (decision.get("decision") or "NO_GO").upper()
        try:
            decision["confidence"] = max(0.0, min(1.0, float(decision.get("confidence", 0))))
        except (TypeError, ValueError):
            decision["confidence"] = 0.5

    # Strategy
    strategy = await closer._select_strategy(niche, decision)

    confidence = decision["confidence"]
    if confidence >= closer.stream_confidence:
        route = "agi_stream_call"
    elif confidence >= closer.static_confidence:
        route = "static_call"
    elif decision["decision"] == "GO":
        route = "nurture"
    else:
        route = "no_go"

    return {
        "lead_name": name,
        "niche": niche,
        "strategy": strategy,
        "brain_decision": decision["decision"],
        "brain_confidence": confidence,
        "brain_reasoning": decision.get("reasoning", ""),
        "route": route,
    }
