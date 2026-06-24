"""
EMPIRE V49 · SEO IDEA-TO-SHIPPED — Module 3: KEYWORD GAP TOOL
===============================================================
Keyword opportunity finder. Discovers keywords competitors rank for
that we don't, scores them by difficulty and opportunity value.

Works without Ahrefs/SEMrush:
  - Uses Groq LLM to generate long-tail keyword ideas from seed terms
  - Scores keywords by competition (heuristic + LLM), search intent, and value
  - Cross-references against existing seo_keywords table to find true gaps
  - Outputs prioritized keyword gap list with content briefs

Usage:
    tool = KeywordGapTool()
    gaps = await tool.find_gaps(niche="roofing", metro="Dallas")
    briefs = await tool.generate_content_briefs(gaps["keywords"][:5])
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx

log = logging.getLogger("empire.seo.keyword_gap")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Keyword generation prompts ──────────────────────────────────────

KEYWORD_GAP_SYSTEM = """You are an expert SEO keyword strategist. Generate long-tail keyword
opportunities that a business is NOT targeting but should be.

For each keyword, provide:
- The exact keyword phrase
- Search intent (transactional / informational / navigational)
- Why it's valuable for this business
- Estimated competition level

Output ONLY a JSON array:
[
  {
    "keyword": "exact phrase",
    "search_intent": "transactional|informational|navigational",
    "competition": "low|medium|high",
    "value_score": 0-100,
    "rationale": "Why this keyword matters"
  }
]

Rules:
- Prioritize transactional keywords (buying intent) over informational
- Long-tail (3+ words) keywords have lower competition and higher conversion
- Keywords with "near me", "emergency", "cost", "free estimate" = high value
- Keywords with "how to", "what is", "DIY" = informational (lower value for lead gen)
"""

CONTENT_BRIEF_SYSTEM = """You are an SEO content strategist. Create a concise content brief
for the target keyword and niche. Include the exact structure needed to rank.

Output ONLY valid JSON:
{
  "keyword": "...",
  "title_tag": "60-char SEO title",
  "meta_description": "155-char description",
  "h1": "Main heading",
  "outline": ["section1", "section2", "section3", "section4"],
  "word_count_target": 800-2000,
  "secondary_keywords": ["kw1", "kw2", "kw3"],
  "internal_links": ["/page1", "/page2"],
  "schema_type": "LocalBusiness|Service|FAQ|Article|Product",
  "content_type": "landing_page|blog_post|service_page|guide"
}"""


class KeywordGapTool:
    """Module 3: Keyword gap discovery and content brief generation.

    Finds high-value keywords we should target, scores them, and
    generates ready-to-write content briefs.
    """

    def __init__(self):
        self.model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.stats = {"gaps_found": 0, "briefs_generated": 0, "errors": 0}

    @property
    def api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    # ── FIND KEYWORD GAPS ───────────────────────────────────────────

    async def find_gaps(
        self, niche: str, metro: str = "", seed_count: int = 15
    ) -> Dict[str, Any]:
        """Find keyword gaps for a niche/metro combination.

        1. Generate keyword ideas via Groq
        2. Cross-reference against existing keywords in Supabase
        3. Score and prioritize
        4. Return gap list
        """
        api_key = self.api_key
        seed_keywords = self._get_seed_keywords(niche, metro)

        if api_key:
            keywords = await self._groq_keyword_generation(niche, metro, seed_keywords, seed_count)
        else:
            keywords = self._heuristic_keywords(niche, metro, seed_count)

        # Cross-reference against existing keywords in Supabase
        existing = await self._get_existing_keywords(niche, metro)
        existing_set = set(existing)

        # Mark true gaps (keywords we don't already track)
        gaps = []
        for kw in keywords:
            kw["is_gap"] = kw["keyword"] not in existing_set
            if kw["is_gap"]:
                gaps.append(kw)

        # Sort by value_score descending
        gaps.sort(key=lambda k: k.get("value_score", 0), reverse=True)

        self.stats["gaps_found"] += len(gaps)

        return {
            "niche": niche,
            "metro": metro,
            "keywords_found": len(keywords),
            "true_gaps": len(gaps),
            "existing_keywords": len(existing),
            "gaps": gaps[:20],  # top 20 gaps
            "all_keywords": keywords[:30],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── GENERATE CONTENT BRIEFS ──────────────────────────────────────

    async def generate_content_briefs(
        self, keywords: List[Dict], niche: str, metro: str = ""
    ) -> List[Dict]:
        """Generate content briefs for keyword gaps."""

        async def _brief_for_kw(kw):
            api_key = self.api_key
            keyword = kw.get("keyword", "")

            if not api_key:
                return self._heuristic_brief(keyword, niche, metro)

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
                                {"role": "system", "content": CONTENT_BRIEF_SYSTEM},
                                {"role": "user", "content": f"Keyword: {keyword}\nNiche: {niche}\nMetro: {metro or 'national'}\nReturn JSON only."},
                            ],
                            "max_tokens": 400,
                            "temperature": 0.4,
                        },
                    )
                    if r.status_code != 200:
                        return self._heuristic_brief(keyword, niche, metro)
                    data = r.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    clean = content.strip()
                    if "```json" in clean:
                        clean = clean.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean:
                        clean = clean.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(clean)
                    parsed["generated_by"] = f"groq/{self.model}"
                    return parsed
            except Exception as e:
                log.warning(f"[kw_gap] brief generation failed for '{keyword}': {e}")
                return self._heuristic_brief(keyword, niche, metro)

        # Process sequentially (briefs are fast, ~1-2s each)
        briefs = []
        for kw in keywords[:10]:
            brief = await _brief_for_kw(kw)
            if brief:
                briefs.append(brief)
                self.stats["briefs_generated"] += 1

        return briefs

    # ── KEYWORD GENERATION ───────────────────────────────────────────

    async def _groq_keyword_generation(
        self, niche: str, metro: str, seeds: List[str], count: int
    ) -> List[Dict]:
        api_key = self.api_key
        prompt = (
            f"Business Niche: {niche}\n"
            f"Service Area: {metro or 'national'}\n"
            f"Seed Keywords: {', '.join(seeds[:8])}\n\n"
            f"Generate {count} long-tail keyword opportunities this business should target. "
            f"Prioritize transactional keywords (people ready to hire/buy). "
            f"Include local modifiers when a metro is specified. Return JSON array only."
        )

        try:
            async with httpx.AsyncClient(timeout=45) as client:
                r = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": KEYWORD_GAP_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.7,
                    },
                )
                if r.status_code != 200:
                    return self._heuristic_keywords(niche, metro, count)

                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                clean = content.strip()
                if "```json" in clean:
                    clean = clean.split("```json")[1].split("```")[0].strip()
                elif "```" in clean:
                    clean = clean.split("```")[1].split("```")[0].strip()
                keywords = json.loads(clean)
                return keywords if isinstance(keywords, list) else []
        except Exception as e:
            log.warning(f"[kw_gap] keyword generation failed: {e}")
            self.stats["errors"] += 1
            return self._heuristic_keywords(niche, metro, count)

    def _heuristic_keywords(self, niche: str, metro: str, count: int) -> List[Dict]:
        """Rule-based keyword generation."""
        local = f" {metro}" if metro else ""
        phrases = {
            "roofing": [
                f"roof repair{local}", f"emergency roofer{local}", f"roof replacement cost{local}",
                f"hail damage roof repair{local}", f"roof inspection{local}", f"residential roofing{local}",
                f"roofing contractor near me", f"storm damage roof{local}", f"metal roofing{local}",
                f"flat roof repair{local}", f"roof estimate{local}", f"best roofing company{local}",
                f"roofing services{local}", f"roof leak repair{local}", f"shingle roof replacement{local}",
            ],
            "hvac": [
                f"ac repair{local}", f"hvac contractor near me", f"furnace repair{local}",
                f"emergency ac repair{local}", f"hvac installation{local}", f"air duct cleaning{local}",
                f"heat pump repair{local}", f"commercial hvac{local}", f"hvac maintenance{local}",
                f"heating repair{local}", f"ac tune up{local}", f"hvac replacement cost{local}",
                f"best hvac company{local}", f"24 hour ac repair{local}", f"hvac service{local}",
            ],
            "solar": [
                f"solar panel installation{local}", f"solar company near me", f"solar panel cost{local}",
                f"solar incentives{local}", f"residential solar{local}", f"best solar panels",
                f"solar battery storage{local}", f"solar panel repair{local}", f"commercial solar{local}",
                f"solar estimate{local}", f"solar installer{local}", f"solar panel cleaning{local}",
            ],
            "restoration": [
                f"water damage restoration{local}", f"flood damage repair{local}", f"fire damage restoration{local}",
                f"mold remediation{local}", f"emergency restoration{local}", f"restoration company near me",
                f"storm damage restoration{local}", f"water extraction{local}", f"smoke damage repair{local}",
                f"disaster restoration{local}", f"property restoration{local}", f"restoration services{local}",
            ],
        }

        generic = [
            f"{niche} services{local}", f"{niche} contractor near me", f"best {niche} company{local}",
            f"{niche} repair{local}", f"emergency {niche}{local}", f"{niche} estimate{local}",
            f"{niche} installation{local}", f"{niche} replacement{local}", f"affordable {niche}{local}",
            f"licensed {niche} contractor{local}", f"local {niche}{local}", f"{niche} inspection{local}",
            f"24 hour {niche}{local}", f"{niche} cost{local}", f"{niche} near me",
        ]

        source = phrases.get(niche.lower().split()[0], generic)
        result = []
        for i, kw in enumerate(source[:count]):
            words = kw.split()
            competition = "low" if len(words) >= 4 else ("medium" if len(words) >= 3 else "high")
            result.append({
                "keyword": kw,
                "search_intent": "transactional" if "near me" in kw or "cost" in kw else "informational",
                "competition": competition,
                "value_score": 85 if "near me" in kw.lower() else (75 if "emergency" in kw.lower() else (65 if "cost" in kw.lower() else 50)),
                "rationale": f"High-intent {'local' if metro else ''} {niche} keyword with moderate competition",
            })
        return result

    def _heuristic_brief(self, keyword: str, niche: str, metro: str) -> dict:
        return {
            "keyword": keyword,
            "title_tag": f"{keyword.title()} | Empire AI - {metro or 'Nationwide'} {niche.title()} Leads",
            "meta_description": f"Get verified {keyword} leads for {metro or 'your area'}. Storm-verified properties, ready-to-close. 3% fee on settled claims only.",
            "h1": f"{keyword.title()} in {metro or 'Your Area'}",
            "outline": [
                f"Why choose Empire AI for {keyword}",
                f"How our {niche} lead generation works",
                f"Active {niche} leads near {metro or 'you'}",
                "Sign up in 90 seconds",
            ],
            "word_count_target": 1200,
            "secondary_keywords": [f"{niche} leads", f"{niche} contractor near me", "storm damage leads"],
            "internal_links": [f"/for-{niche}", "/pricing", "/command"],
            "schema_type": "Service",
            "content_type": "landing_page",
            "generated_by": "heuristic",
        }

    # ── SUPABASE LOOKUP ──────────────────────────────────────────────

    async def _get_existing_keywords(self, niche: str, metro: str) -> List[str]:
        """Get keywords we already track for this niche/metro."""
        try:
            from supabase import create_client
            sb = create_client(
                os.environ.get("SUPABASE_URL", ""),
                os.environ.get("SUPABASE_SERVICE_KEY", ""),
            )
            r = sb.table("seo_keywords").select("keyword").eq("niche", niche).limit(500).execute()
            return [row.get("keyword", "") for row in (r.data or [])]
        except Exception:
            return []

    # ── SEED KEYWORDS ────────────────────────────────────────────────

    def _get_seed_keywords(self, niche: str, metro: str) -> List[str]:
        """Get seed keywords for a niche from the SEO agent or defaults."""
        NICHES = {
            "roofing": ["roof repair", "roofing contractor", "hail damage roof", "roof replacement cost",
                        "emergency roof repair", "storm damage roof", "residential roofing", "metal roofing"],
            "hvac": ["ac repair", "hvac contractor", "furnace repair", "emergency hvac",
                     "air conditioning repair", "hvac installation", "heat pump repair", "commercial hvac"],
            "solar": ["solar panel installation", "solar company", "solar panel cost", "solar incentives",
                      "residential solar", "solar battery", "solar panel repair", "commercial solar"],
            "restoration": ["water damage restoration", "flood damage", "fire damage restoration",
                            "mold remediation", "emergency restoration", "storm damage", "water extraction"],
            "plumbing": ["plumber near me", "emergency plumber", "burst pipe repair", "water heater repair",
                         "drain cleaning", "plumbing contractor", "leak repair", "pipe replacement"],
            "electrical": ["electrician near me", "emergency electrician", "panel upgrade", "generator install",
                           "electrical repair", "wiring upgrade", "circuit breaker repair", "lighting installation"],
            "general_contractor": ["general contractor near me", "home renovation", "remodeling contractor",
                                   "construction company", "build addition", "home builder", "commercial construction"],
        }
        seeds = NICHES.get(niche.lower().split()[0], [f"{niche} contractor", f"{niche} repair", f"best {niche}"])
        if metro:
            seeds = [f"{s} {metro}" for s in seeds[:4]] + seeds
        return seeds

    def snapshot(self) -> dict:
        return {
            "model": self.model,
            "api_configured": bool(self.api_key),
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
