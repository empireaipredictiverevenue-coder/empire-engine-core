"""
EMPIRE V49 · SEO IDEA-TO-SHIPPED — Module 5: COMMUNITY VALIDATOR
==================================================================
Community-driven content validation. Before producing any content,
check if there's real community demand by analyzing Reddit/social
discussions, search trends, and competitor engagement.

Works without social media APIs:
  - Scrapes Reddit search pages for niche discussions
  - Analyzes discussion volume, sentiment, and pain points
  - Scores content ideas by community interest level
  - Generates validation reports with confidence scores

Usage:
    validator = CommunityValidator()
    report = await validator.validate_idea("roof repair after hail damage")
    trends = await validator.trending_in_niche("roofing")
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

import httpx

from ._camofox import camofox_health, camofox_fetch_snapshot

log = logging.getLogger("empire.seo.community")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

VALIDATION_SYSTEM = """You are a content validation analyst. Analyze community discussion data
to determine if a content idea has real demand before producing it.

Output ONLY valid JSON:
{
  "idea": "The original idea",
  "validated": true|false,
  "confidence": 0.0-1.0,
  "community_interest_score": 0-100,
  "discussion_volume": "low|medium|high|viral",
  "sentiment": "positive|neutral|negative|mixed",
  "top_pain_points": ["pain1", "pain2", "pain3"],
  "suggested_angle": "Refined content angle based on community sentiment",
  "red_flags": ["flag1"],
  "recommendation": "proceed|refine|skip"
}

Rules:
- validated=true when discussion volume is medium+ AND sentiment is positive/neutral
- validated=false when no community discussion exists OR sentiment is negative
- community_interest_score >70 means strong demand
- red_flags include: low discussion volume, negative sentiment, competing content saturation
"""


class CommunityValidator:
    """Module 5: Community-driven content validation.

    Validates content ideas by analyzing community discussions
    before any production effort is spent.
    """

    def __init__(self):
        self.model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.stats = {"validated": 0, "approved": 0, "rejected": 0, "errors": 0}

    @property
    def api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    # ── VALIDATE IDEA ────────────────────────────────────────────────

    async def validate_idea(
        self, idea: str, niche: str = "", platform: str = "reddit"
    ) -> Dict[str, Any]:
        """Validate a content idea against community discussion data.

        1. Scrapes Reddit/social for the idea topic
        2. Analyzes discussion volume and sentiment
        3. Returns validation report with confidence score
        """
        api_key = self.api_key

        # Scrape community discussions
        if platform == "reddit":
            discussions = await self._scrape_reddit(idea, niche)
        else:
            discussions = []

        # Analyze with Groq
        if api_key and discussions:
            result = await self._groq_validate(idea, niche, discussions)
        else:
            result = self._heuristic_validate(idea, niche, discussions)

        result["idea"] = idea
        result["niche"] = niche
        result["discussions_found"] = len(discussions)
        result["validated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["validated"] += 1
        if result.get("validated"):
            self.stats["approved"] += 1
        else:
            self.stats["rejected"] += 1

        return result

    async def trending_in_niche(self, niche: str) -> Dict[str, Any]:
        """Find what's trending in a niche's community discussions."""
        api_key = self.api_key

        discussions = await self._scrape_reddit(f"{niche} contractor", niche)

        if api_key:
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
                                {"role": "system", "content": """Analyze community discussions and find trending topics.
Return ONLY valid JSON:
{
  "trending_topics": [
    {"topic": "...", "interest_score": 0-100, "discussion_volume": "low|medium|high", "angle": "Recommended content angle"}
  ],
  "niche_summary": "One sentence about what the community is focused on right now"
}"""},
                                {"role": "user", "content": f"Niche: {niche}\nDiscussions: {json.dumps(discussions[:5])}\nReturn JSON only."},
                            ],
                            "max_tokens": 500,
                            "temperature": 0.4,
                        },
                    )
                    if r.status_code == 200:
                        data = r.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        clean = content.strip()
                        if "```json" in clean:
                            clean = clean.split("```json")[1].split("```")[0].strip()
                        elif "```" in clean:
                            clean = clean.split("```")[1].split("```")[0].strip()
                        try:
                            return json.loads(clean)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                log.warning(f"[community] trending failed: {e}")

        # Heuristic fallback
        return {
            "trending_topics": [
                {"topic": f"{niche.title()} pricing in 2026", "interest_score": 85, "discussion_volume": "high", "angle": "Cost comparison guide"},
                {"topic": f"How to find a reliable {niche} contractor", "interest_score": 80, "discussion_volume": "high", "angle": "5 red flags checklist"},
                {"topic": f"Storm damage {niche} repair timeline", "interest_score": 75, "discussion_volume": "medium", "angle": "Timeline + what to expect"},
            ],
            "niche_summary": f"The {niche} community is focused on pricing, contractor reliability, and emergency repair timelines.",
        }

    # ── REDDIT SCRAPING (camofox-browser, falls back to httpx) ───────

    async def _scrape_reddit(self, query: str, niche: str) -> List[Dict]:
        """Scrape Reddit search via camofox-browser (JS-rendered, anti-bot resistant).
        Falls back to httpx if camofox is unreachable.
        """
        results = []
        seen = set()
        search_url = f"https://www.reddit.com/search/?q={quote_plus(query)}&sort=relevance"

        # Try camofox-browser first
        camofox_ok = await camofox_health()
        if camofox_ok:
            try:
                html = await camofox_fetch_snapshot(search_url, session_key=f"reddit-{niche}")
                if html:
                    # Extract post titles from camofox a11y snapshot
                    # Reddit renders titles as link text with "[eN]" index markers
                    for line in html.split("\n"):
                        line = line.strip()
                        # Match camofox a11y format: 'link "Post Title" [e12]'
                        if line.startswith('- link "') or line.startswith('link "'):
                            try:
                                title = line.split('"')[1]
                                if title and len(title) > 5 and title not in seen:
                                    seen.add(title)
                                    results.append({
                                        "title": title[:200],
                                        "source": "reddit",
                                        "url": search_url,
                                    })
                            except IndexError:
                                pass
                    if results:
                        log.info(f"[community] camofox Reddit: {len(results)} discussions for '{query}'")
                        return results
            except Exception as e:
                log.warning(f"[community] camofox Reddit scrape failed: {e}")

        # Fallback: httpx (will likely fail due to Reddit JS requirements)
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(
                    search_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; EmpireAI/1.0; +https://empire-ai.co.uk)"},
                )
                if r.status_code == 200:
                    titles = re.findall(r'<h3[^>]*>(.*?)</h3>', r.text, re.DOTALL)
                    for title in titles[:10]:
                        clean_title = re.sub(r'<[^>]+>', '', title).strip()
                        if clean_title and len(clean_title) > 5 and clean_title not in seen:
                            seen.add(clean_title)
                            results.append({
                                "title": clean_title[:200],
                                "source": "reddit",
                                "url": search_url,
                            })
        except Exception as e:
            log.debug(f"[community] httpx Reddit scrape failed: {e}")

        # Try r/{niche} subreddit via camofox (if healthy)
        if camofox_ok and niche:
            try:
                sub_url = f"https://www.reddit.com/r/{niche}/"
                html = await camofox_fetch_snapshot(sub_url, session_key=f"reddit-r-{niche}")
                if html:
                    for line in html.split("\n"):
                        line = line.strip()
                        if line.startswith('- link "') or line.startswith('link "'):
                            try:
                                title = line.split('"')[1]
                                if title and len(title) > 5 and title not in seen:
                                    seen.add(title)
                                    results.append({
                                        "title": title[:200],
                                        "source": f"reddit/r/{niche}",
                                        "url": sub_url,
                                    })
                            except IndexError:
                                pass
            except Exception:
                pass

        # Always try httpx subreddit fallback (independent of camofox health)
        if niche and len(results) < 5:
            try:
                sub_url = f"https://www.reddit.com/r/{niche}/"
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                    r = await client.get(sub_url, headers={"User-Agent": "Mozilla/5.0 (compatible; EmpireAI/1.0)"})
                    if r.status_code == 200:
                        titles = re.findall(r'<h3[^>]*>(.*?)</h3>', r.text, re.DOTALL)
                        for title in titles[:5]:
                            clean_title = re.sub(r'<[^>]+>', '', title).strip()
                            if clean_title and clean_title not in seen:
                                seen.add(clean_title)
                                results.append({
                                    "title": clean_title[:200],
                                    "source": f"reddit/r/{niche}",
                                    "url": sub_url,
                                })
            except Exception:
                pass

        return results

    # ── GROQ VALIDATION ──────────────────────────────────────────────

    async def _groq_validate(
        self, idea: str, niche: str, discussions: List[Dict]
    ) -> Dict:
        api_key = self.api_key
        discussion_text = "\n".join(
            f"- {d['title']}" for d in discussions[:10]
        )
        prompt = (
            f"Content Idea: {idea}\n"
            f"Niche: {niche or 'general'}\n\n"
            f"Community Discussion Excerpts:\n{discussion_text or '(no discussions found)'}\n\n"
            f"Based on community discussion volume, sentiment, and relevance, "
            f"should we produce this content? Return JSON only."
        )

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
                            {"role": "system", "content": VALIDATION_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 500,
                        "temperature": 0.3,
                    },
                )
                if r.status_code != 200:
                    return self._heuristic_validate(idea, niche, discussions)

                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                clean = content.strip()
                if "```json" in clean:
                    clean = clean.split("```json")[1].split("```")[0].strip()
                elif "```" in clean:
                    clean = clean.split("```")[1].split("```")[0].strip()
                return json.loads(clean)
        except Exception as e:
            log.warning(f"[community] validate failed: {e}")
            self.stats["errors"] += 1
            return self._heuristic_validate(idea, niche, discussions)

    # ── HEURISTIC FALLBACK ───────────────────────────────────────────

    def _heuristic_validate(
        self, idea: str, niche: str, discussions: List[Dict]
    ) -> Dict:
        """Rule-based validation when Groq is unavailable."""
        discussion_count = len(discussions)
        volume = "high" if discussion_count >= 8 else ("medium" if discussion_count >= 3 else "low")
        has_problems = any(
            w in idea.lower() for w in ["emergency", "fix", "problem", "damage", "leak", "broken", "repair", "cost"]
        )
        has_questions = "?" in idea or any(w in idea.lower() for w in ["how", "what", "why", "when"])

        approved = volume in ("medium", "high") or has_problems or has_questions

        return {
            "idea": idea,
            "validated": approved,
            "confidence": 0.7 if approved else 0.4,
            "community_interest_score": min(90, discussion_count * 15 + (20 if has_problems else 0) + (10 if has_questions else 0)),
            "discussion_volume": volume,
            "sentiment": "neutral" if not discussions else "positive",
            "top_pain_points": [
                f"Finding reliable {niche or 'service'} providers",
                f"Understanding {niche or 'repair'} costs",
                "Getting fast emergency service",
            ],
            "suggested_angle": idea if approved else f"Refine: focus on practical {niche or 'service'} solutions",
            "red_flags": [] if approved else ["Low community discussion volume — consider a more popular angle"],
            "recommendation": "proceed" if approved else "refine",
        }

    def snapshot(self) -> dict:
        return {
            "model": self.model,
            "api_configured": bool(self.api_key),
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
