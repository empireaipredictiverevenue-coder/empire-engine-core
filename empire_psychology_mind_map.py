"""
EMPIRE V49 · SALES PSYCHOLOGY MIND MAP
========================================
Structured, queryable psychology-to-strategy mapping system that connects:

  Buyer Persona → Pain Points → Persuasion Principle → Closer Persona
                                                           ↓
                                                   Script Pattern → Technique → Expected Outcome

This module serves as:
  1. A knowledge base of persuasion principles (Cialdini 7 + niche-specific)
  2. A persona-to-strategy routing engine (detect persona → route to best approach)
  3. An effectiveness tracker (which psychology-strategy combinations convert best)
  4. A mind-map query API (for the SPA visualization layer)

Integration points:
  - empire_ai_closer.py: HumanClosingEngine reads persona mappings from this library
  - empire_pain_points.py: Reads which pain points resonate with which personas
  - SPA Psychology tab: Visual mind map, persona stats, principle effectiveness
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger("empire.psychology_mind_map")


# ═════════════════════════════════════════════════════════════════════════
# PERSUASION PRINCIPLES — Cialdini 7 + Niche Extensions
# ═════════════════════════════════════════════════════════════════════════

PERSUASION_PRINCIPLES = {
    "reciprocity": {
        "id": "reciprocity",
        "name": "Reciprocity",
        "founder": "Robert Cialdini",
        "category": "universal",
        "description": (
            "People feel obligated to give back when they receive something first. "
            "In sales, giving value first (free inspection, free report, free consultation) "
            "triggers the reciprocity instinct — the lead feels compelled to engage."
        ),
        "tactics": [
            "Give something of value before asking for anything (free inspection, free thermal scan)",
            "Offer a free, no-obligation assessment — the lead feels indebted to hear you out",
            "Send a helpful guide or report before the call — primes reciprocity during the conversation",
            "Share proprietary data about their specific area — perceived high value triggers stronger reciprocation",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.85,
            "Storm Damage Restoration": 0.90,
            "Flood Damage Restoration": 0.88,
            "Legal Intake": 0.75,
            "Hail Damage Repair": 0.82,
        },
        "persona_affinity": {
            "relationship": 0.90,
            "price_sensitive": 0.80,
            "analytical": 0.70,
            "skeptical": 0.75,
            "decisive": 0.45,
        },
    },
    "scarcity": {
        "id": "scarcity",
        "name": "Scarcity",
        "founder": "Robert Cialdini",
        "category": "universal",
        "description": (
            "People want more of what there is less of. Limited windows, exclusive access, "
            "and expiring opportunities activate loss aversion — the fear of missing out "
            "is a stronger motivator than potential gain."
        ),
        "tactics": [
            "Storm window closing — limited time to file comprehensive insurance claims",
            "Limited dispatch slots — 'our crews are in your area today and tomorrow only'",
            "Exclusive contractor network — 'only 3 vetted contractors available for your area'",
            "Deadline framing — 'insurance windows close in 48 hours for full coverage'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.88,
            "Storm Damage Restoration": 0.92,
            "Flood Damage Restoration": 0.90,
            "Hail Damage Repair": 0.85,
            "Tornado Damage Repair": 0.93,
            "Hurricane Damage Restoration": 0.91,
            "Legal Intake": 0.70,
        },
        "persona_affinity": {
            "decisive": 0.88,
            "analytical": 0.65,
            "relationship": 0.50,
            "price_sensitive": 0.75,
            "skeptical": 0.35,
        },
    },
    "authority": {
        "id": "authority",
        "name": "Authority",
        "founder": "Robert Cialdini",
        "category": "universal",
        "description": (
            "People defer to experts and credible authorities. Certifications, licenses, "
            "industry accolades, and data-backed claims increase trust and compliance."
        ),
        "tactics": [
            "Lead with credentials — 'licensed, bonded, and insured in 18 states'",
            "Cite data and statistics — 'our AI has 94% accuracy on damage prediction'",
            "Mention industry certifications — 'IICRC-certified restoration specialists'",
            "Third-party endorsements — 'BBB A+ rated with 1,400+ verified reviews'",
            "Expert framing — 'our forensic engineers provide data-backed assessments'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.75,
            "Legal Intake": 0.85,
            "Storm Damage Restoration": 0.70,
            "Flood Damage Restoration": 0.72,
            "Hail Damage Repair": 0.68,
        },
        "persona_affinity": {
            "analytical": 0.90,
            "skeptical": 0.88,
            "relationship": 0.70,
            "decisive": 0.60,
            "price_sensitive": 0.65,
        },
    },
    "consistency": {
        "id": "consistency",
        "name": "Commitment & Consistency",
        "founder": "Robert Cialdini",
        "category": "universal",
        "description": (
            "People want to act consistently with their prior commitments. Small initial "
            "agreements snowball into larger commitments. Once someone says yes to a small "
            "thing, they're more likely to say yes to a bigger thing."
        ),
        "tactics": [
            "Start with small yes — 'can I send you a quick text with our details?'",
            "Build commitment ladder — agree to receive info → agree to inspection → agree to repair",
            "Foot-in-the-door — 'would you be open to a 2-minute conversation?' then escalate",
            "Label their past behavior — 'you've already taken the first step by answering — let's keep going'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.70,
            "Storm Damage Restoration": 0.72,
            "Legal Intake": 0.78,
            "Flood Damage Restoration": 0.68,
            "Hail Damage Repair": 0.65,
        },
        "persona_affinity": {
            "analytical": 0.75,
            "relationship": 0.80,
            "decisive": 0.55,
            "price_sensitive": 0.65,
            "skeptical": 0.55,
        },
    },
    "liking": {
        "id": "liking",
        "name": "Liking",
        "founder": "Robert Cialdini",
        "category": "universal",
        "description": (
            "People say yes to people they like. Similarity, compliments, familiarity, "
            "and rapport-building increase liking. Warm, conversational tones outperform "
            "scripted sales pitches."
        ),
        "tactics": [
            "Find common ground — local knowledge, shared experiences, weather you both experienced",
            "Genuine compliments — 'you've done a great job maintaining the property given the weather'",
            "Mirror and pacing — match the lead's tone, pace, and language style",
            "Friendly, conversational tone — scripted feels salesy; natural feels human",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.72,
            "Storm Damage Restoration": 0.74,
            "Legal Intake": 0.65,
            "Flood Damage Restoration": 0.70,
            "Contractor Recruitment": 0.85,
        },
        "persona_affinity": {
            "relationship": 0.95,
            "price_sensitive": 0.65,
            "skeptical": 0.70,
            "analytical": 0.45,
            "decisive": 0.40,
        },
    },
    "social_proof": {
        "id": "social_proof",
        "name": "Social Proof",
        "founder": "Robert Cialdini",
        "category": "universal",
        "description": (
            "People look to what others are doing to guide their own decisions. "
            "Testimonials, case counts, neighborhood stats, and 'people like you' "
            "references reduce uncertainty and increase trust."
        ),
        "tactics": [
            "Neighborhood stats — 'we've already helped 12 property owners in your area this week'",
            "Similar situation framing — 'businesses like yours in similar situations typically...'",
            "Case count — 'over 3,200 successful claims in 2025'",
            "Testimonials — reference specific success stories from similar clients",
            "Review highlights — 'our contractors average 4.8 stars across 1,400+ reviews'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.80,
            "Storm Damage Restoration": 0.85,
            "Legal Intake": 0.78,
            "Flood Damage Restoration": 0.80,
            "Hail Damage Repair": 0.76,
            "Tornado Damage Repair": 0.88,
        },
        "persona_affinity": {
            "relationship": 0.85,
            "price_sensitive": 0.80,
            "skeptical": 0.72,
            "analytical": 0.60,
            "decisive": 0.55,
        },
    },
    "unity": {
        "id": "unity",
        "name": "Unity",
        "founder": "Robert Cialdini",
        "category": "advanced",
        "description": (
            "People are influenced by others they perceive as part of their 'we' — "
            "shared identity, shared experience, shared geography. 'We're in this together' "
            "framing creates powerful in-group bias."
        ),
        "tactics": [
            "Shared geography — 'we're both part of this community that was hit by the storm'",
            "Shared experience — 'we all went through that storm together'",
            "Us vs. the problem — 'let's work together to get your property taken care of'",
            "Identity framing — 'we're both business owners dealing with the same challenges'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.68,
            "Storm Damage Restoration": 0.78,
            "Contractor Recruitment": 0.82,
            "Flood Damage Restoration": 0.75,
            "Legal Intake": 0.55,
        },
        "persona_affinity": {
            "relationship": 0.92,
            "skeptical": 0.60,
            "price_sensitive": 0.50,
            "analytical": 0.40,
            "decisive": 0.35,
        },
    },
    # ── Niche-specific principles ────────────────────────────────
    "loss_aversion": {
        "id": "loss_aversion",
        "name": "Loss Aversion",
        "founder": "Kahneman & Tversky (Prospect Theory)",
        "category": "behavioral_economics",
        "description": (
            "Losses loom larger than gains. The pain of losing $100 is psychologically "
            "twice as powerful as the pleasure of gaining $100. In restoration, the cost "
            "of inaction (further damage, insurance denial) is framed as a loss to prevent."
        ),
        "tactics": [
            "Frame as loss prevention — 'every day you wait, the damage gets worse'",
            "Insurance window framing — 'if you miss the window, the loss is entirely yours'",
            "Business interruption cost — 'how much revenue are you losing per day?'",
            "Deterioration framing — 'what's a $5K repair today becomes a $50K replacement next month'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.85,
            "Storm Damage Restoration": 0.88,
            "Flood Damage Restoration": 0.90,
            "Legal Intake": 0.72,
            "Hail Damage Repair": 0.80,
        },
        "persona_affinity": {
            "price_sensitive": 0.92,
            "analytical": 0.78,
            "decisive": 0.68,
            "relationship": 0.60,
            "skeptical": 0.55,
        },
    },
    "certainty_effect": {
        "id": "certainty_effect",
        "name": "Certainty Effect",
        "founder": "Kahneman & Tversky",
        "category": "behavioral_economics",
        "description": (
            "People overweight certain outcomes vs. probabilistic ones. A certain small "
            "gain is preferred over a larger uncertain gain. Free inspection (certain value) "
            "beats 'you might get a big settlement' (uncertain)."
        ),
        "tactics": [
            "Guarantee certainty — 'the inspection costs you nothing, guaranteed'",
            "Zero-risk framing — 'there's no financial risk to you, regardless of outcome'",
            "Insurance coverage certainty — 'your policy covers this — we verify before we start'",
            "Outcome guarantee — 'if we don't find damage, you haven't spent a dime'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.78,
            "Storm Damage Restoration": 0.80,
            "Legal Intake": 0.75,
            "Hail Damage Repair": 0.76,
        },
        "persona_affinity": {
            "price_sensitive": 0.90,
            "skeptical": 0.85,
            "analytical": 0.72,
            "relationship": 0.60,
            "decisive": 0.55,
        },
    },
    "anticipatory_regret": {
        "id": "anticipatory_regret",
        "name": "Anticipatory Regret",
        "founder": "Janis & Mann (1977)",
        "category": "behavioral_economics",
        "description": (
            "People make decisions to avoid future regret. Asking 'how will you feel if "
            "you miss this opportunity and the damage gets worse?' triggers anticipatory "
            "regret — a powerful motivator for action."
        ),
        "tactics": [
            "Future-self framing — 'imagine finding out in 6 months the damage was covered but you didn't act'",
            "Counterfactual questioning — 'what if the insurance window closes and you're left with the full cost?'",
            "Regret priming — 'most people who wait tell us they wish they'd called sooner'",
            "Prevention framing — 'let's make sure you don't end up in the same situation'",
        ],
        "niche_relevance": {
            "Roofing Restoration": 0.80,
            "Storm Damage Restoration": 0.85,
            "Flood Damage Restoration": 0.82,
            "Legal Intake": 0.78,
            "Hail Damage Repair": 0.75,
        },
        "persona_affinity": {
            "analytical": 0.82,
            "price_sensitive": 0.78,
            "decisive": 0.70,
            "relationship": 0.55,
            "skeptical": 0.50,
        },
    },
}


# ═════════════════════════════════════════════════════════════════════════
# BUYER PERSONA PROFILES — Psychology + Strategy Recommendations
# ═════════════════════════════════════════════════════════════════════════

BUYER_PERSONA_PROFILES = {
    "analytical": {
        "key": "analytical",
        "label": "The Analyst",
        "description": (
            "Data-driven, detail-oriented. Needs proof, statistics, and verifiable results. "
            "Compares options carefully and responds to information-rich approaches. "
            "Worst approach: pressure tactics or vague promises."
        ),
        "dominant_principles": ["authority", "consistency", "anticipatory_regret"],
        "effective_techniques": ["summary_close", "value_reversal"],
        "best_closer_persona": "consultative",
        "script_tone": "measured, precise, data-rich",
        "opening_philosophy": "Lead with data, case studies, and verifiable results",
        "keywords": ["data", "research", "statistics", "prove", "compare", "show me", "evidence", "studies"],
        "voice_tone": "measured, precise",
        "decision_style": "Requires evidence-based persuasion",
        "pain_point_priority": "Data-backed proof, case studies, statistics",
    },
    "decisive": {
        "key": "decisive",
        "label": "The Decisive Buyer",
        "description": (
            "Wants the bottom line immediately. Impatient, action-oriented, direct. "
            "Respects confidence and brevity. Worst approach: long discovery questions "
            "or slow building rapport."
        ),
        "dominant_principles": ["scarcity", "loss_aversion"],
        "effective_techniques": ["direct_ask", "sharp_angle", "assumptive_close"],
        "best_closer_persona": "direct_closer",
        "script_tone": "confident, brisk, outcome-focused",
        "opening_philosophy": "Get straight to the point. Lead with outcome, not process.",
        "keywords": ["bottom line", "get to the point", "what's this about", "fast", "quick", "just tell me"],
        "voice_tone": "confident, brisk",
        "decision_style": "Decides quickly, values efficiency",
        "pain_point_priority": "Time savings, immediate action, quick resolution",
    },
    "relationship": {
        "key": "relationship",
        "label": "The Relationship Builder",
        "description": (
            "Trust-first buyer. Wants referrals, values reputation, thinks long-term. "
            "Needs to feel the person on the other end is genuine. "
            "Worst approach: hard sell or overly transactional."
        ),
        "dominant_principles": ["liking", "reciprocity", "unity", "social_proof"],
        "effective_techniques": ["trust_building", "puppy_dog_close", "schedule_commitment"],
        "best_closer_persona": "relationship_builder",
        "script_tone": "warm, conversational, empathetic",
        "opening_philosophy": "Build rapport first. Use social proof, testimonials, third-party validation.",
        "keywords": ["who else", "referral", "reputation", "trust", "company behind", "who's involved"],
        "voice_tone": "warm, conversational",
        "decision_style": "Needs trust before buying",
        "pain_point_priority": "Reputation, community standing, long-term relationship",
    },
    "price_sensitive": {
        "key": "price_sensitive",
        "label": "The Value Seeker",
        "description": (
            "Cost-conscious, compares value, risk-averse. Needs clear ROI clarity. "
            "Is not necessarily 'cheap' — needs to see the value before spending. "
            "Worst approach: ignoring cost concerns or being dismissive."
        ),
        "dominant_principles": ["reciprocity", "certainty_effect", "loss_aversion", "social_proof"],
        "effective_techniques": ["value_reversal", "puppy_dog_close", "summary_close"],
        "best_closer_persona": "value_articulator",
        "script_tone": "reassuring, patient, value-focused",
        "opening_philosophy": "Emphasize zero-cost entry, insurance coverage, cost of inaction.",
        "keywords": ["cost", "free", "charge", "pricing", "expensive", "worth", "value", "save", "afford"],
        "voice_tone": "reassuring, patient",
        "decision_style": "Needs clear value proposition",
        "pain_point_priority": "Cost savings, ROI, insurance coverage",
    },
    "skeptical": {
        "key": "skeptical",
        "label": "The Skeptic",
        "description": (
            "Guarded, questions legitimacy, wants verification. May have had bad past "
            "experiences or been contacted by storm chasers before. "
            "Worst approach: being defensive or dismissive of their concerns."
        ),
        "dominant_principles": ["authority", "certainty_effect", "reciprocity"],
        "effective_techniques": ["trust_building", "value_reversal", "puppy_dog_close"],
        "best_closer_persona": "relationship_builder",
        "script_tone": "respectful, transparent, patient",
        "opening_philosophy": "Validate their concern. Lead with credentials, licensing, verifiable proof.",
        "keywords": ["scam", "legit", "real", "verify", "prove", "BBB", "license", "accreditation"],
        "voice_tone": "respectful, transparent",
        "decision_style": "Requires trust + verification",
        "pain_point_priority": "Trust signals, credentials, third-party verification",
    },
}


# ═════════════════════════════════════════════════════════════════════════
# NICHE PSYCHOLOGY PROFILES — Per-Niche Buyer Psychology
# ═════════════════════════════════════════════════════════════════════════

# For each niche, define:
#   - persona_distribution: what % of leads fall into each persona
#   - principle_weights: which persuasion principles work best
#   - pain_point_priorities: which pain point categories resonate most

NICHE_PSYCHOLOGY_PROFILES = {
    "Roofing Restoration": {
        "niche": "Roofing Restoration",
        "dominant_persona": "decisive",
        "persona_distribution": {
            "decisive": 0.32,
            "analytical": 0.20,
            "relationship": 0.18,
            "price_sensitive": 0.22,
            "skeptical": 0.08,
        },
        "principle_weights": {
            "scarcity": 0.92,
            "loss_aversion": 0.85,
            "reciprocity": 0.82,
            "social_proof": 0.78,
            "authority": 0.72,
            "anticipatory_regret": 0.80,
            "certainty_effect": 0.75,
            "consistency": 0.68,
            "liking": 0.65,
            "unity": 0.60,
        },
        "top_pain_point_types": ["claim_denial", "leak_urgency", "out_of_pocket", "bad_contractor"],
        "best_closer_persona": "urgency_driver",
        "emotional_triggers": ["fear_of_leak", "insurance_frustration", "property_value_concern"],
        "decision_speed": "fast",  # roof leaks create urgency
        "communication_preference": "phone_call",
        "price_sensitivity": "medium",
        "seasonal_peak_months": [3, 4, 5, 6, 7, 8],  # storm season
    },
    "Storm Damage Restoration": {
        "niche": "Storm Damage Restoration",
        "dominant_persona": "decisive",
        "persona_distribution": {
            "decisive": 0.35,
            "analytical": 0.18,
            "relationship": 0.15,
            "price_sensitive": 0.20,
            "skeptical": 0.12,
        },
        "principle_weights": {
            "scarcity": 0.95,
            "loss_aversion": 0.90,
            "social_proof": 0.85,
            "reciprocity": 0.80,
            "anticipatory_regret": 0.85,
            "unity": 0.78,
            "certainty_effect": 0.76,
            "authority": 0.70,
            "liking": 0.65,
            "consistency": 0.62,
        },
        "top_pain_point_types": ["storm_window", "compliance", "liability"],
        "best_closer_persona": "urgency_driver",
        "emotional_triggers": ["safety_concern", "deadline_pressure", "community_impact"],
        "decision_speed": "fast",
        "communication_preference": "phone_call",
        "price_sensitivity": "low",  # insurance covers most costs
        "seasonal_peak_months": [3, 4, 5, 6, 7, 8, 9],
    },
    "Flood Damage Restoration": {
        "niche": "Flood Damage Restoration",
        "dominant_persona": "price_sensitive",
        "persona_distribution": {
            "price_sensitive": 0.30,
            "analytical": 0.22,
            "decisive": 0.18,
            "relationship": 0.18,
            "skeptical": 0.12,
        },
        "principle_weights": {
            "loss_aversion": 0.92,
            "certainty_effect": 0.88,
            "reciprocity": 0.82,
            "scarcity": 0.80,
            "social_proof": 0.78,
            "authority": 0.75,
            "anticipatory_regret": 0.82,
            "unity": 0.72,
            "consistency": 0.65,
            "liking": 0.60,
        },
        "top_pain_point_types": ["flood_excluded", "contamination", "equipment_loss"],
        "best_closer_persona": "value_articulator",
        "emotional_triggers": ["mold_fear", "health_concern", "financial_devastation"],
        "decision_speed": "medium",
        "communication_preference": "phone_call",
        "price_sensitivity": "high",
        "seasonal_peak_months": [1, 2, 3, 6, 7, 8, 9],
    },
    "Hail Damage Repair": {
        "niche": "Hail Damage Repair",
        "dominant_persona": "analytical",
        "persona_distribution": {
            "analytical": 0.28,
            "price_sensitive": 0.24,
            "decisive": 0.20,
            "relationship": 0.16,
            "skeptical": 0.12,
        },
        "principle_weights": {
            "authority": 0.85,
            "loss_aversion": 0.82,
            "social_proof": 0.78,
            "certainty_effect": 0.76,
            "reciprocity": 0.74,
            "scarcity": 0.72,
            "anticipatory_regret": 0.78,
            "consistency": 0.68,
            "liking": 0.55,
            "unity": 0.50,
        },
        "top_pain_point_types": ["hidden_damage", "cosmetic_denial"],
        "best_closer_persona": "consultative",
        "emotional_triggers": ["hidden_cost_fear", "insurance_skepticism"],
        "decision_speed": "medium",
        "communication_preference": "phone_call_or_email",
        "price_sensitivity": "medium",
        "seasonal_peak_months": [3, 4, 5, 6],
    },
    "Tornado Damage Repair": {
        "niche": "Tornado Damage Repair",
        "dominant_persona": "decisive",
        "persona_distribution": {
            "decisive": 0.38,
            "price_sensitive": 0.20,
            "relationship": 0.18,
            "analytical": 0.14,
            "skeptical": 0.10,
        },
        "principle_weights": {
            "scarcity": 0.95,
            "social_proof": 0.90,
            "loss_aversion": 0.88,
            "unity": 0.82,
            "reciprocity": 0.78,
            "anticipatory_regret": 0.85,
            "certainty_effect": 0.74,
            "authority": 0.68,
            "liking": 0.62,
            "consistency": 0.58,
        },
        "top_pain_point_types": ["total_loss", "fema_delay", "debris"],
        "best_closer_persona": "urgency_driver",
        "emotional_triggers": ["trauma_response", "urgency", "community_solidarity"],
        "decision_speed": "very_fast",
        "communication_preference": "phone_call",
        "price_sensitivity": "low",
        "seasonal_peak_months": [3, 4, 5, 6],
    },
    "Hurricane Damage Restoration": {
        "niche": "Hurricane Damage Restoration",
        "dominant_persona": "analytical",
        "persona_distribution": {
            "analytical": 0.25,
            "price_sensitive": 0.24,
            "decisive": 0.22,
            "relationship": 0.18,
            "skeptical": 0.11,
        },
        "principle_weights": {
            "scarcity": 0.90,
            "loss_aversion": 0.88,
            "social_proof": 0.82,
            "certainty_effect": 0.80,
            "reciprocity": 0.76,
            "authority": 0.74,
            "anticipatory_regret": 0.82,
            "unity": 0.78,
            "consistency": 0.65,
            "liking": 0.58,
        },
        "top_pain_point_types": ["mold_flood", "multi_system", "vacant_property"],
        "best_closer_persona": "value_articulator",
        "emotional_triggers": ["devastation", "overwhelm", "safety"],
        "decision_speed": "medium",
        "communication_preference": "phone_call",
        "price_sensitivity": "medium",
        "seasonal_peak_months": [6, 7, 8, 9, 10],
    },
    "Legal Intake": {
        "niche": "Legal Intake",
        "dominant_persona": "analytical",
        "persona_distribution": {
            "analytical": 0.30,
            "price_sensitive": 0.25,
            "skeptical": 0.20,
            "decisive": 0.15,
            "relationship": 0.10,
        },
        "principle_weights": {
            "authority": 0.90,
            "certainty_effect": 0.85,
            "reciprocity": 0.78,
            "social_proof": 0.80,
            "loss_aversion": 0.72,
            "consistency": 0.70,
            "scarcity": 0.65,
            "anticipatory_regret": 0.75,
            "liking": 0.55,
            "unity": 0.45,
        },
        "top_pain_point_types": ["statute_limitations", "no_win_no_fee"],
        "best_closer_persona": "consultative",
        "emotional_triggers": ["injustice", "financial_stress", "health_concern"],
        "decision_speed": "slow",
        "communication_preference": "phone_call_or_email",
        "price_sensitivity": "high",
        "seasonal_peak_months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    },
    "Contractor Recruitment": {
        "niche": "Contractor Recruitment",
        "dominant_persona": "relationship",
        "persona_distribution": {
            "relationship": 0.35,
            "decisive": 0.25,
            "analytical": 0.20,
            "price_sensitive": 0.12,
            "skeptical": 0.08,
        },
        "principle_weights": {
            "unity": 0.90,
            "liking": 0.88,
            "reciprocity": 0.85,
            "social_proof": 0.82,
            "consistency": 0.75,
            "authority": 0.72,
            "certainty_effect": 0.68,
            "loss_aversion": 0.60,
            "scarcity": 0.58,
            "anticipatory_regret": 0.55,
        },
        "top_pain_point_types": ["lead_quality", "payment_reliability", "partnership"],
        "best_closer_persona": "relationship_builder",
        "emotional_triggers": ["partnership", "growth", "community"],
        "decision_speed": "slow",
        "communication_preference": "email_or_phone",
        "price_sensitivity": "medium",
        "seasonal_peak_months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    },
}


# ═════════════════════════════════════════════════════════════════════════
# SCRIPT PATTERN MAPPING — Principle → Technique → Pattern Name
# ═════════════════════════════════════════════════════════════════════════

PRINCIPLE_TO_TECHNIQUE_MAP = {
    "reciprocity": ["summary_close", "value_reversal", "puppy_dog_close"],
    "scarcity": ["limited_time", "sharp_angle", "assumptive_close"],
    "authority": ["trust_building", "summary_close", "direct_ask"],
    "consistency": ["schedule_commitment", "puppy_dog_close", "assumptive_close"],
    "liking": ["trust_building", "schedule_commitment"],
    "social_proof": ["summary_close", "value_reversal", "puppy_dog_close"],
    "unity": ["trust_building", "schedule_commitment"],
    "loss_aversion": ["value_reversal", "limited_time", "sharp_angle"],
    "certainty_effect": ["puppy_dog_close", "value_reversal", "summary_close"],
    "anticipatory_regret": ["value_reversal", "limited_time", "sharp_angle"],
}

TECHNIQUE_TO_PATTERN_MAP = {
    "assumptive_close": "Assume the lead is ready and act as if the next step is a given.",
    "value_reversal": "Reframe the cost of inaction as higher than the cost of action.",
    "limited_time": "Create urgency around a genuine time constraint.",
    "value_add": "Offer something extra that the competition doesn't.",
    "direct_ask": "Ask directly for the commitment or next step.",
    "schedule_commitment": "Get a small commitment now to build momentum.",
    "trust_building": "Provide third-party validation and credentials.",
    "puppy_dog_close": "Let them try it risk-free first.",
    "sharp_angle": "Turn every objection into a reason to move forward now.",
    "summary_close": "Summarize all value points and ask for the close.",
}


# ── Default niche profile ───────────────────────────────────────────
# Used as fallback when a niche has no specific psychology profile
_DEFAULT_NICHE_PROFILE = {
    "niche": "__default__",
    "dominant_persona": "analytical",
    "persona_distribution": {
        "analytical": 0.25,
        "decisive": 0.20,
        "relationship": 0.20,
        "price_sensitive": 0.20,
        "skeptical": 0.15,
    },
    "principle_weights": {
        "reciprocity": 0.75,
        "scarcity": 0.70,
        "authority": 0.75,
        "consistency": 0.65,
        "liking": 0.65,
        "social_proof": 0.75,
        "unity": 0.60,
        "loss_aversion": 0.70,
        "certainty_effect": 0.70,
        "anticipatory_regret": 0.65,
    },
    "top_pain_point_types": ["general", "cost", "trust"],
    "best_closer_persona": "consultative",
    "emotional_triggers": ["trust", "value", "urgency"],
    "decision_speed": "medium",
    "communication_preference": "phone_call",
    "price_sensitivity": "medium",
    "seasonal_peak_months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}


# ═════════════════════════════════════════════════════════════════════════
# PSYCHOLOGY MIND MAP ENGINE
# ═════════════════════════════════════════════════════════════════════════

class PsychologyMindMap:
    """
    Sales Psychology Mind Map — the central knowledge base + effectiveness tracker.

    Provides:
      - Full psychology-to-strategy mapping (persona → principle → technique → outcome)
      - Per-niche psychology profiles with persona distributions and principle weights
      - Persona detection recommendations (which principle to use for which persona)
      - Effectiveness tracking for psychology-strategy combinations
      - Mind map data structure for the SPA visualization layer
    """

    def __init__(self, get_db=None):
        self.get_db = get_db
        # Effectiveness tracking: (niche, persona_key, principle_key) -> {attempts, successes}
        self._effectiveness: Dict[tuple, Dict] = {}
        # Cached mind map graph
        self._mind_map_graph: Optional[dict] = None

    # ── PERSONA TO PRINCIPLE ROUTING ──────────────────────────────────

    def get_principles_for_persona(self, persona_key: str) -> List[dict]:
        """
        Return the best persuasion principles for a given buyer persona,
        sorted by affinity (highest first).
        """
        profile = BUYER_PERSONA_PROFILES.get(persona_key)
        if not profile:
            return []

        # Get principle affinity scores for this persona
        scored = []
        for p_key, principle in PERSUASION_PRINCIPLES.items():
            affinity = principle.get("persona_affinity", {}).get(persona_key, 0.0)
            if affinity > 0:
                scored.append({
                    "principle_key": p_key,
                    "principle_name": principle["name"],
                    "affinity": affinity,
                    "category": principle["category"],
                    "description": principle["description"],
                    "tactics": principle["tactics"],
                    "techniques": PRINCIPLE_TO_TECHNIQUE_MAP.get(p_key, []),
                })

        scored.sort(key=lambda p: p["affinity"], reverse=True)
        return scored

    def get_persona_for_lead_text(self, text: str) -> Dict[str, Any]:
        """
        Detect the likely buyer persona from free-form lead text.
        Scores each persona based on keyword matches.

        Returns the best-match persona with confidence score.
        """
        if not text or len(text.strip()) < 3:
            return {"persona": "unknown", "confidence": 0.0}

        text_lower = text.lower()
        scores = {}

        for p_key, profile in BUYER_PERSONA_PROFILES.items():
            score = 0
            hit_count = 0
            for kw in profile.get("keywords", []):
                if kw in text_lower:
                    score += 2
                    hit_count += 1
            if hit_count > 0:
                score += hit_count * 0.5  # bonus for multiple hits
            if score > 0:
                scores[p_key] = score

        if not scores:
            return {"persona": "unknown", "confidence": 0.0}

        # Normalize: best match ÷ total possible
        best_key = max(scores, key=scores.get)
        max_possible = len(BUYER_PERSONA_PROFILES.get(best_key, {}).get("keywords", [])) * 2
        confidence = min(1.0, scores[best_key] / max_possible) if max_possible > 0 else 0.0

        return {
            "persona": best_key,
            "label": BUYER_PERSONA_PROFILES[best_key]["label"],
            "confidence": round(confidence, 3),
            "all_scores": {k: round(v / max(scores.values()), 3) for k, v in scores.items()},
        }

    def get_recommended_approach(self, persona_key: str, niche: str = "") -> Dict[str, Any]:
        """
        Return a full recommended approach for a persona, optionally
        tailored to a specific niche.

        Combines: best principles → best techniques → closest persona → script tone
        """
        profile = BUYER_PERSONA_PROFILES.get(persona_key)
        if not profile:
            return {"error": f"Unknown persona: {persona_key}"}

        principles = self.get_principles_for_persona(persona_key)

        # Get niche-specific adjustments if available
        niche_profile = NICHE_PSYCHOLOGY_PROFILES.get(niche) if niche else None

        # Adjust principle weights by niche
        if niche_profile:
            niche_w = niche_profile.get("principle_weights", {})
            for p in principles:
                nw = niche_w.get(p["principle_key"])
                if nw is not None:
                    p["niche_adjusted_affinity"] = round(
                        (p["affinity"] + nw) / 2, 3
                    )

        # Gather recommended techniques
        all_techniques = []
        seen = set()
        for p in principles:
            for tech in p.get("techniques", []):
                if tech not in seen:
                    seen.add(tech)
                    pattern = TECHNIQUE_TO_PATTERN_MAP.get(tech, "")
                    all_techniques.append({
                        "technique": tech,
                        "pattern": pattern,
                        "principle_source": p["principle_key"],
                    })

        closer_key = niche_profile["best_closer_persona"] if niche_profile else profile["best_closer_persona"]

        return {
            "persona": persona_key,
            "persona_label": profile["label"],
            "best_closer_persona": closer_key,
            "script_tone": profile["script_tone"],
            "opening_philosophy": profile["opening_philosophy"],
            "decision_style": profile["decision_style"],
            "top_principles": principles[:5],
            "recommended_techniques": all_techniques[:6],
            "niche_adjusted": bool(niche_profile),
            "niche": niche or "none",
        }

    # ── NICHE PSYCHOLOGY ─────────────────────────────────────────────

    def get_niche_profile(self, niche: str) -> Optional[dict]:
        """Return the full psychology profile for a niche, falling back to defaults for unknown niches."""
        profile = NICHE_PSYCHOLOGY_PROFILES.get(niche)
        if profile is None:
            profile = dict(_DEFAULT_NICHE_PROFILE)
            profile["niche"] = niche
        return profile

    def get_all_niche_profiles(self) -> List[dict]:
        """Return psychology profiles for all tracked niches."""
        return list(NICHE_PSYCHOLOGY_PROFILES.values())

    def get_niche_persona_breakdown(self, niche: str) -> Dict[str, Any]:
        """
        Return persona distribution and recommended approaches for a niche.
        """
        profile = self.get_niche_profile(niche)
        if not profile:
            return {"niche": niche, "error": "No psychology profile for this niche"}

        distribution = profile.get("persona_distribution", {})
        breakdown = []
        for p_key, pct in sorted(distribution.items(), key=lambda x: -x[1]):
            profile_data = BUYER_PERSONA_PROFILES.get(p_key, {})
            approach = self.get_recommended_approach(p_key, niche)
            breakdown.append({
                "persona": p_key,
                "label": profile_data.get("label", p_key),
                "percentage": pct,
                "estimated_leads_per_100": round(pct * 100),
                "approach": approach,
            })

        return {
            "niche": niche,
            "dominant_persona": profile["dominant_persona"],
            "dominant_persona_label": BUYER_PERSONA_PROFILES.get(profile["dominant_persona"], {}).get("label", ""),
            "best_closer_persona": profile["best_closer_persona"],
            "decision_speed": profile["decision_speed"],
            "price_sensitivity": profile["price_sensitivity"],
            "emotional_triggers": profile.get("emotional_triggers", []),
            "breakdown": breakdown,
        }

    # ── MIND MAP GRAPH ──────────────────────────────────────────────

    def build_mind_map(self) -> dict:
        """
        Build the full mind map graph structure for the SPA visualization.

        Returns a directed graph with nodes and edges connecting:
          Niche → Persona → Principle → Technique → Expected Outcome
        """
        nodes = []
        edges = []

        # Add niche nodes
        for niche_key, profile in NICHE_PSYCHOLOGY_PROFILES.items():
            node_id = f"niche:{niche_key}"
            nodes.append({
                "id": node_id,
                "type": "niche",
                "label": niche_key,
                "subtitle": f"Best: {profile['best_closer_persona'].replace('_', ' ').title()}",
                "size": "large",
                "color": "#44E5B8",
                "metrics": {
                    "decision_speed": profile["decision_speed"],
                    "price_sensitivity": profile["price_sensitivity"],
                },
            })

            # Connect niche to dominant persona
            dom_p = profile["dominant_persona"]
            p_node_id = f"persona:{dom_p}"
            dom_pct = profile["persona_distribution"].get(dom_p, 0)
            edges.append({
                "source": node_id,
                "target": p_node_id,
                "weight": round(dom_pct, 2),
                "label": f"{round(dom_pct * 100)}% dominant",
            })

            # Connect niche to principle (top 3)
            top_principles = sorted(
                profile["principle_weights"].items(),
                key=lambda x: -x[1],
            )[:3]
            for p_key, p_weight in top_principles:
                edges.append({
                    "source": node_id,
                    "target": f"principle:{p_key}",
                    "weight": round(p_weight, 2),
                    "label": f"weight {round(p_weight * 100)}%",
                })

        # Add persona nodes
        for p_key, profile in BUYER_PERSONA_PROFILES.items():
            node_id = f"persona:{p_key}"
            nodes.append({
                "id": node_id,
                "type": "persona",
                "label": profile["label"],
                "subtitle": f"Best: {profile['best_closer_persona'].replace('_', ' ').title()}",
                "size": "large",
                "color": "#00F5FF",
                "metrics": {
                    "decision_style": profile["decision_style"],
                    "voice_tone": profile["voice_tone"],
                },
            })

            # Connect persona to top principles
            for p_key_2, principle in PERSUASION_PRINCIPLES.items():
                affinity = principle.get("persona_affinity", {}).get(p_key, 0)
                if affinity >= 0.7:  # only strong connections
                    edges.append({
                        "source": node_id,
                        "target": f"principle:{p_key_2}",
                        "weight": affinity,
                        "label": f"affinity {round(affinity * 100)}%",
                    })

        # Add principle nodes
        for p_key, principle in PERSUASION_PRINCIPLES.items():
            node_id = f"principle:{p_key}"
            nodes.append({
                "id": node_id,
                "type": "principle",
                "label": principle["name"],
                "subtitle": principle.get("category", "universal").replace("_", " ").title(),
                "size": "medium",
                "color": "#FFB800",
                "metrics": {
                    "category": principle["category"],
                    "tactic_count": len(principle.get("tactics", [])),
                },
            })

            # Connect principle to techniques
            for tech in PRINCIPLE_TO_TECHNIQUE_MAP.get(p_key, []):
                t_node_id = f"technique:{tech}"
                edges.append({
                    "source": node_id,
                    "target": t_node_id,
                    "weight": 0.8,
                    "label": "implements",
                })

        # Add technique nodes
        for tech, pattern in TECHNIQUE_TO_PATTERN_MAP.items():
            node_id = f"technique:{tech}"
            nodes.append({
                "id": node_id,
                "type": "technique",
                "label": tech.replace("_", " ").title(),
                "subtitle": pattern[:60] + "...",
                "size": "small",
                "color": "#8264FF",
                "metrics": {
                    "pattern": pattern,
                },
            })

        # Summary stats
        persona_count = sum(1 for n in nodes if n["type"] == "persona")
        principle_count = sum(1 for n in nodes if n["type"] == "principle")
        technique_count = sum(1 for n in nodes if n["type"] == "technique")
        niche_count = sum(1 for n in nodes if n["type"] == "niche")

        self._mind_map_graph = {
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "niches": niche_count,
                "personas": persona_count,
                "principles": principle_count,
                "techniques": technique_count,
            },
        }

        return self._mind_map_graph

    def get_mind_map(self) -> dict:
        """Return the cached mind map or rebuild it."""
        if self._mind_map_graph:
            return self._mind_map_graph
        return self.build_mind_map()

    # ── EFFECTIVENESS TRACKING ──────────────────────────────────────

    def record_effectiveness(
        self,
        niche: str,
        persona_key: str,
        principle_key: str,
        success: bool,
    ):
        """
        Record whether a psychology-strategy combination led to a successful outcome.
        This allows the system to learn which approaches work best per niche.
        """
        key = (niche, persona_key, principle_key)
        if key not in self._effectiveness:
            self._effectiveness[key] = {"attempts": 0, "successes": 0}

        self._effectiveness[key]["attempts"] += 1
        if success:
            self._effectiveness[key]["successes"] += 1

    def get_effectiveness(
        self,
        niche: Optional[str] = None,
        persona_key: Optional[str] = None,
        principle_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query effectiveness data with optional filters.

        Returns dicts with: niche, persona, principle, attempts, successes, conversion_rate
        """
        results = []
        for (n, p, pr), data in self._effectiveness.items():
            if niche and n != niche:
                continue
            if persona_key and p != persona_key:
                continue
            if principle_key and pr != principle_key:
                continue

            attempts = data["attempts"]
            successes = data["successes"]
            results.append({
                "niche": n,
                "persona": p,
                "persona_label": BUYER_PERSONA_PROFILES.get(p, {}).get("label", p),
                "principle": pr,
                "principle_name": PERSUASION_PRINCIPLES.get(pr, {}).get("name", pr),
                "attempts": attempts,
                "successes": successes,
                "conversion_rate": round(successes / attempts, 3) if attempts > 0 else 0,
            })

        return {
            "results": results,
            "total_records": len(results),
            "filtered": bool(niche or persona_key or principle_key),
        }

    def get_effectiveness_summary(self) -> Dict[str, Any]:
        """Return aggregate effectiveness statistics."""
        total_attempts = sum(d["attempts"] for d in self._effectiveness.values())
        total_successes = sum(d["successes"] for d in self._effectiveness.values())

        return {
            "total_attempts": total_attempts,
            "total_successes": total_successes,
            "overall_conversion_rate": round(total_successes / max(total_attempts, 1), 3),
            "total_combinations_tracked": len(self._effectiveness),
            "best_persona": self._find_best("persona"),
            "best_principle": self._find_best("principle"),
            "best_niche": self._find_best("niche"),
        }

    def _find_best(self, dim: str) -> Optional[dict]:
        """Find the best-performing dimension (niche, persona, or principle)."""
        aggregator = {}
        for (n, p, pr), data in self._effectiveness.items():
            key = {"niche": n, "persona": p, "principle": pr}[dim]
            if key not in aggregator:
                aggregator[key] = {"attempts": 0, "successes": 0}
            aggregator[key]["attempts"] += data["attempts"]
            aggregator[key]["successes"] += data["successes"]

        if not aggregator:
            return None

        best_key = max(
            aggregator,
            key=lambda k: aggregator[k]["successes"] / max(aggregator[k]["attempts"], 1),
        )
        best = aggregator[best_key]

        label_map = {
            "niche": lambda k: k,
            "persona": lambda k: BUYER_PERSONA_PROFILES.get(k, {}).get("label", k),
            "principle": lambda k: PERSUASION_PRINCIPLES.get(k, {}).get("name", k),
        }

        return {
            dim: best_key,
            "label": label_map[dim](best_key),
            "attempts": best["attempts"],
            "successes": best["successes"],
            "conversion_rate": round(best["successes"] / max(best["attempts"], 1), 3),
        }

    # ── ADAPTIVE PRINCIPLE WEIGHTS ─────────────────────────────────

    def get_adjusted_principle_weights(self, niche: str) -> Dict[str, float]:
        """
        Return persuasion principle weights for a niche, adjusted by
        actual tracked effectiveness data.

        Merges the static niche_psychology weights with live effectiveness data
        using exponential weighting (α=0.7 for static, 0.3 for live).
        """
        niche_profile = self.get_niche_profile(niche)
        if not niche_profile:
            return {}

        base_weights = dict(niche_profile.get("principle_weights", {}))

        # Adjust with live data if available
        for principle_key in base_weights:
            key = (niche, "__any__", principle_key)
            # Aggregate across all personas for this niche+principle
            aggregate = {"attempts": 0, "successes": 0}
            for (n, p, pr), data in self._effectiveness.items():
                if n == niche and pr == principle_key:
                    aggregate["attempts"] += data["attempts"]
                    aggregate["successes"] += data["successes"]

            if aggregate["attempts"] >= 5:  # minimum sample size
                live_rate = aggregate["successes"] / aggregate["attempts"]
                # Blend: 70% static weight, 30% live rate
                blended = base_weights[principle_key] * 0.7 + live_rate * 0.3
                base_weights[principle_key] = round(blended, 3)

        return base_weights

    # ── SNAPSHOT ────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return full mind map state for the SPA / analytics."""
        mind_map = self.get_mind_map()
        effectiveness = self.get_effectiveness_summary()

        return {
            "mind_map": mind_map,
            "effectiveness": effectiveness,
            "niche_profiles_count": len(NICHE_PSYCHOLOGY_PROFILES),
            "persona_count": len(BUYER_PERSONA_PROFILES),
            "principles_count": len(PERSUASION_PRINCIPLES),
            "techniques_count": len(TECHNIQUE_TO_PATTERN_MAP),
            "ts": datetime.now(timezone.utc).isoformat(),
        }


# ═════════════════════════════════════════════════════════════════════════
# FASTAPI ROUTES
# ═════════════════════════════════════════════════════════════════════════

__all__ = [
    "PsychologyMindMap",
    "PERSUASION_PRINCIPLES",
    "BUYER_PERSONA_PROFILES",
    "NICHE_PSYCHOLOGY_PROFILES",
]


def register_psychology_routes(app, require_auth=None):
    """Register Sales Psychology Mind Map API endpoints on a FastAPI app."""
    from fastapi import Depends, Request

    mind_map = PsychologyMindMap()

    if require_auth:
        @app.get("/api/psychology/mind-map")
        async def get_mind_map(auth=Depends(require_auth)):
            """Return the full mind map graph (nodes + edges)."""
            return mind_map.get_mind_map()

        @app.get("/api/psychology/personas")
        async def get_personas(auth=Depends(require_auth)):
            """Return all buyer personas with profiles."""
            return {
                "personas": {
                    k: {
                        "key": v["key"],
                        "label": v["label"],
                        "description": v["description"],
                        "dominant_principles": v["dominant_principles"],
                        "best_closer_persona": v["best_closer_persona"],
                        "script_tone": v["script_tone"],
                        "decision_style": v["decision_style"],
                    }
                    for k, v in BUYER_PERSONA_PROFILES.items()
                },
                "count": len(BUYER_PERSONA_PROFILES),
            }

        @app.get("/api/psychology/principles")
        async def get_principles(auth=Depends(require_auth)):
            """Return all persuasion principles with niche relevance and persona affinity."""
            return {
                "principles": {
                    k: {
                        "id": v["id"],
                        "name": v["name"],
                        "founder": v["founder"],
                        "category": v["category"],
                        "description": v["description"],
                        "tactics": v["tactics"],
                        "niche_relevance": v["niche_relevance"],
                        "persona_affinity": v["persona_affinity"],
                    }
                    for k, v in PERSUASION_PRINCIPLES.items()
                },
                "count": len(PERSUASION_PRINCIPLES),
            }

        @app.get("/api/psychology/niche/{niche}")
        async def get_niche_psychology(niche: str, auth=Depends(require_auth)):
            """Return full psychology profile for a niche: persona breakdown, principle weights, approach."""
            break_down = mind_map.get_niche_persona_breakdown(niche)
            adjusted = mind_map.get_adjusted_principle_weights(niche)
            return {
                "profile": break_down,
                "adjusted_principle_weights": adjusted,
            }

        @app.get("/api/psychology/detect-persona")
        async def detect_persona(
            text: str = "",
            niche: str = "",
            auth=Depends(require_auth),
        ):
            """Detect buyer persona from lead text and return recommended approach."""
            result = mind_map.get_persona_for_lead_text(text)
            if result["persona"] != "unknown":
                result["recommended_approach"] = mind_map.get_recommended_approach(
                    result["persona"], niche
                )
            return result

        @app.get("/api/psychology/recommend/{persona}")
        async def recommend_for_persona(
            persona: str,
            niche: str = "",
            auth=Depends(require_auth),
        ):
            """Return recommended approach for a persona, optionally niche-tailored."""
            return mind_map.get_recommended_approach(persona, niche)

        @app.get("/api/psychology/effectiveness")
        async def get_effectiveness(
            niche: str = "",
            persona: str = "",
            principle: str = "",
            auth=Depends(require_auth),
        ):
            """Return effectiveness tracking data with optional filters."""
            return mind_map.get_effectiveness(
                niche=niche or None,
                persona_key=persona or None,
                principle_key=principle or None,
            )

        @app.post("/api/psychology/record")
        async def record_effectiveness_route(
            request: Request,
            auth=Depends(require_auth),
        ):
            """Record a psychology-strategy outcome for effectiveness tracking."""
            try:
                body = await request.json()
                niche = body.get("niche", "")
                persona_key = body.get("persona", "")
                principle_key = body.get("principle", "")
                success = bool(body.get("success", False))
                mind_map.record_effectiveness(niche, persona_key, principle_key, success)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}

        @app.get("/api/psychology/snapshot")
        async def psychology_snapshot(auth=Depends(require_auth)):
            """Return full mind map snapshot for the SPA."""
            return mind_map.snapshot()

    else:
        # No-auth fallback routes (simplified)
        @app.get("/api/psychology/mind-map")
        async def get_mind_map():
            return mind_map.get_mind_map()

        @app.get("/api/psychology/snapshot")
        async def psychology_snapshot():
            return mind_map.snapshot()

    log.info("[psychology_mind_map] Routes registered · /api/psychology/*")
