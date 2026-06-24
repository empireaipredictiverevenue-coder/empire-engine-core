"""
EMPIRE V49 · SEO IDEA-TO-SHIPPED — Module 4: VIDEO GAP ANALYZER
=================================================================
YouTube/video content gap detection. Finds topics with high search
volume but low video coverage — opportunities for Shorts/long-form.

Works without YouTube API:
  - Scrapes YouTube search results via httpx
  - Uses Groq to analyze video content gaps
  - Identifies topics with high demand, low supply
  - Generates video content briefs (title, thumbnail concept, script outline)

Usage:
    analyzer = VideoGapAnalyzer()
    gaps = await analyzer.scan_video_gaps(niche="roofing")
    brief = await analyzer.generate_video_brief(gaps[0])
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

import httpx

log = logging.getLogger("empire.seo.video_gap")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

VIDEO_GAP_SYSTEM = """You are a YouTube content strategist. Analyze a niche for video content
gaps — topics people search for but have few or low-quality videos covering them.

Output ONLY valid JSON:
{
  "gaps": [
    {
      "topic": "Specific video topic",
      "search_volume": "low|medium|high|viral",
      "competition": "low|medium|high",
      "existing_video_count_estimate": 0-1000,
      "opportunity_score": 0-100,
      "recommended_format": "shorts|long_form|both",
      "title_ideas": ["title1", "title2"],
      "thumbnail_concept": "Brief thumbnail idea"
    }
  ],
  "total_gaps_found": 0,
  "niche_summary": "One sentence about video landscape for this niche"
}

Rules:
- High opportunity = high search volume + low competition
- "how to", "before and after", "cost breakdown" = high engagement formats
- Shorts (vertical, <60s) should target trending hooks and quick tips
- Long-form (>5 min) should target educational/deep-dive content
"""


class VideoGapAnalyzer:
    """Module 4: YouTube/video content gap analyzer.

    Finds video topics competitors aren't covering well.
    Uses Groq for analysis, YouTube search scraping for ground-truth data.
    """

    def __init__(self):
        self.model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.stats = {"scans": 0, "gaps_found": 0, "briefs_generated": 0, "errors": 0}

    @property
    def api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    # ── VIDEO GAP SCAN ──────────────────────────────────────────────

    async def scan_video_gaps(
        self, niche: str, sub_topic: str = "", max_gaps: int = 10
    ) -> Dict[str, Any]:
        """Scan for video content gaps in a niche.

        1. Searches YouTube for the niche topic
        2. Counts existing videos
        3. Uses Groq to identify underserved topics
        4. Returns prioritized gap list
        """
        api_key = self.api_key

        # Search YouTube to get ground-truth video count
        query = f"{niche} {sub_topic}".strip()
        existing_count = await self._youtube_search_count(query)

        if api_key:
            result = await self._groq_video_gap_analysis(niche, sub_topic, existing_count, max_gaps)
        else:
            result = self._heuristic_video_gaps(niche, sub_topic, max_gaps)

        result["niche"] = niche
        result["sub_topic"] = sub_topic
        result["existing_videos_in_search"] = existing_count
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["scans"] += 1
        self.stats["gaps_found"] += len(result.get("gaps", []))
        return result

    async def generate_video_brief(self, gap: Dict) -> Dict:
        """Generate a video content brief from a gap."""
        api_key = self.api_key
        topic = gap.get("topic", "")
        niche = gap.get("niche", "")

        if api_key:
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
                                {"role": "system", "content": """You are a YouTube script writer. Generate a video content brief.
Return ONLY valid JSON:
{
  "title": "YouTube title (60 chars max)",
  "hook": "First 3 seconds hook line",
  "format": "shorts|long_form",
  "duration_seconds": 30-300,
  "script_outline": ["beat1", "beat2", "beat3", "beat4", "beat5"],
  "cta": "Call to action",
  "tags": ["tag1", "tag2", "tag3", "tag4"],
  "thumbnail_text": "Short text for thumbnail overlay"
}"""},
                                {"role": "user", "content": f"Topic: {topic}\nNiche: {niche}\nReturn JSON only."},
                            ],
                            "max_tokens": 400,
                            "temperature": 0.5,
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
                        parsed = json.loads(clean)
                        self.stats["briefs_generated"] += 1
                        return parsed
            except Exception as e:
                log.warning(f"[video_gap] brief generation failed: {e}")

        self.stats["briefs_generated"] += 1
        return self._heuristic_video_brief(topic, niche)

    # ── YOUTUBE SEARCH ───────────────────────────────────────────────

    async def _youtube_search_count(self, query: str) -> int:
        """Count YouTube search results for a query (very rough estimate)."""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(
                    "https://www.youtube.com/results",
                    params={"search_query": query},
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; EmpireAI/1.0)",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                if r.status_code == 200:
                    # Count video result items
                    video_count = len(re.findall(r'"videoId":"[^"]+?"', r.text))
                    return video_count or 1
        except Exception as e:
            log.debug(f"[video_gap] YouTube search failed: {e}")
        return 0

    # ── GROQ ANALYSIS ────────────────────────────────────────────────

    async def _groq_video_gap_analysis(
        self, niche: str, sub_topic: str, existing_count: int, max_gaps: int
    ) -> Dict:
        api_key = self.api_key
        prompt = (
            f"Niche: {niche}\n"
            f"Sub-topic: {sub_topic or 'general'}\n"
            f"Existing YouTube videos for main search: ~{existing_count}\n\n"
            f"Find {max_gaps} specific video topics within this niche that have high search demand "
            f"but are underserved by existing YouTube content. Focus on topics that would drive "
            f"real business leads (not just views). Return JSON only."
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
                            {"role": "system", "content": VIDEO_GAP_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 1500,
                        "temperature": 0.6,
                    },
                )
                if r.status_code != 200:
                    return self._heuristic_video_gaps(niche, sub_topic, max_gaps)

                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                clean = content.strip()
                if "```json" in clean:
                    clean = clean.split("```json")[1].split("```")[0].strip()
                elif "```" in clean:
                    clean = clean.split("```")[1].split("```")[0].strip()
                return json.loads(clean)
        except Exception as e:
            log.warning(f"[video_gap] analysis failed: {e}")
            self.stats["errors"] += 1
            return self._heuristic_video_gaps(niche, sub_topic, max_gaps)

    # ── HEURISTIC FALLBACK ───────────────────────────────────────────

    def _heuristic_video_gaps(self, niche: str, sub_topic: str, max_gaps: int) -> dict:
        patterns = [
            {
                "topic": f"How much does {niche} {sub_topic or 'repair'} really cost in 2026?",
                "search_volume": "high",
                "competition": "medium",
                "existing_video_count_estimate": 50,
                "opportunity_score": 85,
                "recommended_format": "shorts",
                "title_ideas": [
                    f"The TRUTH about {niche} pricing (no one tells you this)",
                    f"{niche.title()} cost breakdown 2026 — don't get ripped off",
                ],
                "thumbnail_concept": "Split screen: cheap repair vs expensive repair with price tags",
            },
            {
                "topic": f"{niche.title()} before and after — real storm damage",
                "search_volume": "high",
                "competition": "low",
                "existing_video_count_estimate": 30,
                "opportunity_score": 90,
                "recommended_format": "both",
                "title_ideas": [
                    f"INSANE {niche.title()} transformation after storm damage",
                    f"Before & After: {niche.title()} — you won't believe #3",
                ],
                "thumbnail_concept": "Arrow pointing from damaged to perfect condition",
            },
            {
                "topic": f"Emergency {niche} — what to do in the first 24 hours",
                "search_volume": "medium",
                "competition": "low",
                "existing_video_count_estimate": 15,
                "opportunity_score": 80,
                "recommended_format": "long_form",
                "title_ideas": [
                    f"EMERGENCY {niche.upper()}: First 24 Hours Guide",
                    f"What to do when {niche} fails — step by step",
                ],
                "thumbnail_concept": "Red emergency text on dark background with clock",
            },
            {
                "topic": f"Top 5 {niche} companies near me — how to choose",
                "search_volume": "medium",
                "competition": "medium",
                "existing_video_count_estimate": 40,
                "opportunity_score": 75,
                "recommended_format": "shorts",
                "title_ideas": [
                    f"5 RED FLAGS when hiring a {niche} contractor",
                    f"How to spot a BAD {niche} company in 30 seconds",
                ],
                "thumbnail_concept": "5 red flags with checkmarks/X marks",
            },
        ]
        return {
            "gaps": patterns[:max_gaps],
            "total_gaps_found": len(patterns[:max_gaps]),
            "niche_summary": f"The {niche} niche has moderate video coverage. Underserved topics include cost breakdowns, before/after transformations, and emergency guides — all high-engagement formats.",
        }

    def _heuristic_video_brief(self, topic: str, niche: str) -> dict:
        return {
            "title": topic[:60],
            "hook": f"Most {niche} companies don't want you to know this...",
            "format": "shorts" if len(topic.split()) < 10 else "long_form",
            "duration_seconds": 45 if len(topic.split()) < 10 else 180,
            "script_outline": [
                "Hook: shocking stat or question",
                "Problem: pain point establishment",
                "Solution: Empire AI's unique approach",
                "Proof: real results or data",
                "CTA: visit empire-ai.co.uk",
            ],
            "cta": "Get free inspection → empire-ai.co.uk",
            "tags": [niche, f"{niche} repair", f"{niche} cost", "storm damage", "contractor tips"],
            "thumbnail_text": f"{niche.upper()} TRUTH",
        }

    def snapshot(self) -> dict:
        return {
            "model": self.model,
            "api_configured": bool(self.api_key),
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
