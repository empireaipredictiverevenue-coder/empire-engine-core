"""
EMPIRE V49 · OMNICHANNEL ENGINE — Layer 2: CLASSIFIER
=======================================================
Groq-powered LLM lead classification and key message extraction.

Uses Groq's ultra-fast API (llama-3.3-70b-versatile) to classify leads
into hot/warm/cold with confidence scores, extract intent signals,
and generate personalized key messages for outreach.

Pipeline:
    Unified lead record
        → Groq LLM classification (temperature + confidence + reasoning)
        → Key message extraction (personalized hook for SMS/email/voice)
        → Intent signal detection (buying intent, urgency, objections)
        → Return enriched lead with classification metadata

Usage:
    classifier = GroqClassifier()
    result = await classifier.classify_lead(lead)
    batch = await classifier.classify_batch(leads)
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx

log = logging.getLogger("empire.omni.classifier")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Classification prompt template ───────────────────────────────────

CLASSIFY_SYSTEM = """You are an expert lead classifier for Empire AI, a storm damage lead generation platform.
Your job: analyze property-owner leads and classify them with precision.

Output ONLY valid JSON — no markdown, no commentary. Use this exact structure:
{
  "temperature": "hot|warm|cold",
  "confidence": 0.0-1.0,
  "reasoning": "1 sentence explaining the classification",
  "intent_signals": ["signal1", "signal2"],
  "key_message": "Personalized 1-sentence outreach hook for SMS/email",
  "objection_handling": "1 sentence addressing the most likely objection",
  "niche": "roofing|hvac|solar|construction|restoration|insurance|other",
  "priority": 1-10
}

Classification rules:
- HOT: urgency ≥7, recent damage, has phone, clear buying intent → dispatch immediately
- WARM: urgency 4-6, partial info, needs nurturing → add to sequence
- COLD: urgency <4, old lead, no contact info → retarget or park
"""


class GroqClassifier:
    """Layer 2: Groq LLM lead classification + key message extraction.

    Uses Groq's OpenAI-compatible API for ultra-fast inference.
    Falls back to heuristic scoring if Groq is unavailable.
    API key is read dynamically at call time so env changes between
    restarts are picked up without re-importing the module.
    """

    def __init__(self):
        self.model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.stats = {"classified": 0, "hot": 0, "warm": 0, "cold": 0, "errors": 0}

    @property
    def api_key(self) -> str:
        """Read GROQ_API_KEY dynamically — picks up env changes at runtime."""
        return os.getenv("GROQ_API_KEY", "")

    # ── CLASSIFICATION ─────────────────────────────────────────────────

    async def classify_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Classify a single lead using Groq LLM.

        Returns the lead dict with added fields: temperature, confidence,
        intent_signals, key_message, objection_handling, classified_by, classified_at.
        """
        api_key = self.api_key
        if not api_key:
            return self._heuristic_classify(lead)

        prompt = self._build_prompt(lead)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": CLASSIFY_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 300,
                        "temperature": 0.2,
                    },
                )
                if r.status_code != 200:
                    log.warning(f"[classifier] Groq HTTP {r.status_code}: {r.text[:200]}")
                    return self._heuristic_classify(lead)

                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            parsed = self._parse_json(content)
            if parsed is None:
                return self._heuristic_classify(lead)

            # Merge classification into lead
            temp = parsed.get("temperature", "warm")
            lead["temperature"] = temp
            lead["confidence"] = parsed.get("confidence", 0.5)
            lead["intent_signals"] = parsed.get("intent_signals", [])
            lead["key_message"] = parsed.get("key_message", "")
            lead["objection_handling"] = parsed.get("objection_handling", "")
            lead["niche"] = parsed.get("niche", lead.get("niche", ""))
            lead["priority"] = parsed.get("priority", 5)
            lead["classified_by"] = f"groq/{self.model}"
            lead["classified_at"] = datetime.now(timezone.utc).isoformat()

            self.stats["classified"] += 1
            self.stats[temp] = self.stats.get(temp, 0) + 1
            return lead

        except Exception as e:
            log.warning(f"[classifier] Groq call failed: {e}")
            self.stats["errors"] += 1
            return self._heuristic_classify(lead)

    async def classify_batch(self, leads: List[Dict[str, Any]], concurrency: int = 3) -> List[Dict[str, Any]]:
        """Classify multiple leads with concurrency control.

        Uses a semaphore to avoid rate-limiting Groq's API.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _bounded(lead):
            async with sem:
                return await self.classify_lead(lead)

        tasks = [_bounded(lead) for lead in leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        classified = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.warning(f"[classifier] batch lead {i} failed: {r}")
                classified.append(self._heuristic_classify(leads[i]))
            else:
                classified.append(r)

        log.info(f"[classifier] batch complete: {len(classified)} leads, "
                 f"hot={self.stats['hot']} warm={self.stats['warm']} cold={self.stats['cold']}")
        return classified

    # ── PROMPT BUILDER ─────────────────────────────────────────────────

    def _build_prompt(self, lead: Dict[str, Any]) -> str:
        """Build a classification prompt from a unified lead record."""
        parts = [
            f"Lead: {lead.get('name', 'Unknown')}",
            f"City/State: {lead.get('city', '?')}, {lead.get('state', '?')}",
            f"Urgency Score: {lead.get('urgency_score', 0)}/10",
            f"Asset Value: ${lead.get('asset_value', 0):,.0f}",
            f"Has Phone: {bool(lead.get('phone'))}",
            f"Has Email: {bool(lead.get('email'))}",
            f"Source: {lead.get('source', 'unknown')}",
            f"Status: {lead.get('status', 'unknown')}",
        ]
        if lead.get("niche"):
            parts.append(f"Niche: {lead['niche']}")
        if lead.get("address"):
            parts.append(f"Address: {lead['address'][:80]}")
        return "\n".join(parts)

    def _parse_json(self, content: str) -> Optional[dict]:
        """Parse JSON from LLM output, handling markdown fences."""
        if not content:
            return None
        clean = content.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            parts = clean.split("```")
            if len(parts) >= 2:
                clean = parts[1].strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return None

    # ── HEURISTIC FALLBACK ─────────────────────────────────────────────

    def _heuristic_classify(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based classification when Groq is unavailable."""
        urgency = lead.get("urgency_score", 0) or 0
        has_phone = bool(lead.get("phone"))

        if urgency >= 7 and has_phone:
            temp = "hot"
            confidence = min(0.95, 0.7 + (urgency - 7) * 0.08)
        elif urgency >= 4:
            temp = "warm"
            confidence = 0.5 + (urgency - 4) * 0.1
        else:
            temp = "cold"
            confidence = max(0.2, 0.5 - (4 - urgency) * 0.1)

        city = lead.get("city", "your area")
        name = lead.get("name", "property owner")
        lead["temperature"] = temp
        lead["confidence"] = round(confidence, 2)
        lead["intent_signals"] = (
            ["high_urgency", "has_phone"] if temp == "hot" else
            ["moderate_urgency"] if temp == "warm" else ["low_urgency"]
        )
        lead["key_message"] = (
            f"Hi {name.split()[0] if name.split() else name}, storm damage detected in {city}. "
            f"Get a free inspection — we handle the insurance claim. Reply YES."
        )
        lead["objection_handling"] = "No cost to you — insurance covers everything."
        lead["priority"] = 9 if temp == "hot" else (5 if temp == "warm" else 2)
        lead["classified_by"] = "heuristic"
        lead["classified_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["classified"] += 1
        self.stats[temp] = self.stats.get(temp, 0) + 1
        return lead

    def snapshot(self) -> dict:
        return {
            "model": self.model,
            "api_configured": bool(self.api_key),
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
