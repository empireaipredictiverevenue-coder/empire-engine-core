"""
EMPIRE V49 · SEO IDEA-TO-SHIPPED — Module 2: GAP SCANNER
==========================================================
Competitor content gap analyzer. Scrapes competitor content and uses
Groq LLM to identify what they cover that we don't.

Works without Ahrefs/SEMrush:
  - Scrapes top SERP results for target keywords via httpx
  - Uses Groq to analyze content coverage gaps
  - Compares Empire AI pages against competitor pages
  - Outputs actionable gap reports with priority scoring

Usage:
    scanner = GapScanner()
    gaps = await scanner.scan_gaps(niche="roofing", keyword="roof repair near me")
    report = await scanner.compare_page("/for-roofing", "https://competitor.com/roofing")
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus

import httpx

from ._camofox import camofox_health, camofox_fetch_snapshot, camofox_fetch_links

log = logging.getLogger("empire.seo.gap_scanner")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

GAP_ANALYSIS_SYSTEM = """You are an expert SEO content gap analyst. Compare the provided
pages and identify exactly what content topics, keywords, and angles the competitor
covers that we don't. Be specific and actionable.

Output ONLY valid JSON:
{
  "gaps": [
    {
      "topic": "Specific topic the competitor covers",
      "keyword_angle": "The keyword intent they target",
      "missing_from_our_page": true,
      "priority": 1-10,
      "estimated_search_volume": "low|medium|high",
      "recommended_action": "What we should create"
    }
  ],
  "competitor_strengths": ["strength1", "strength2"],
  "our_strengths": ["strength1", "strength2"],
  "overall_gap_severity": "low|medium|high|critical",
  "summary": "One sentence summary"
}"""


class GapScanner:
    """Module 2: Competitor content gap analysis.

    Two modes:
      1. scan_gaps(niche, keyword) — scrapes SERP top results, analyzes gaps
      2. compare_page(our_url, competitor_url) — direct page comparison
    """

    def __init__(self):
        self.model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.stats = {"scans": 0, "gaps_found": 0, "errors": 0}

    @property
    def api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    # ── SERP GAP SCAN ───────────────────────────────────────────────

    async def scan_gaps(
        self, niche: str, keyword: str, metro: str = "", top_n: int = 3
    ) -> Dict[str, Any]:
        """Scan top SERP results for a keyword and find content gaps.

        1. Searches Google for the keyword
        2. Scrapes top N results
        3. Analyzes content gaps vs Empire AI's existing content
        """
        api_key = self.api_key

        # Step 1: Get competitor URLs
        competitor_urls = await self._serp_search(keyword, metro, top_n)

        # Step 2: Scrape competitor content
        competitor_content = []
        for url in competitor_urls[:top_n]:
            content = await self._scrape_page(url)
            if content:
                competitor_content.append({"url": url, "content": content[:3000]})

        if not competitor_content:
            return self._empty_scan_result(keyword, niche, metro)

        # Step 3: Our existing content for comparison
        our_url = f"https://empire-ai.co.uk/for-{niche}" if niche else "https://empire-ai.co.uk"
        our_content = await self._scrape_page(our_url) or ""

        # Step 4: Groq gap analysis
        if api_key:
            result = await self._groq_gap_analysis(
                keyword, niche, metro, competitor_content, our_content
            )
        else:
            result = self._heuristic_gap_analysis(
                keyword, niche, competitor_content, our_content
            )

        result["keyword"] = keyword
        result["niche"] = niche
        result["metro"] = metro
        result["competitors_analyzed"] = len(competitor_content)
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["scans"] += 1
        self.stats["gaps_found"] += len(result.get("gaps", []))
        return result

    async def compare_page(
        self, our_url: str, competitor_url: str
    ) -> Dict[str, Any]:
        """Direct comparison of our page against a competitor page."""
        api_key = self.api_key

        our_content = await self._scrape_page(our_url) or ""
        their_content = await self._scrape_page(competitor_url) or ""

        if not their_content:
            return {"error": "Could not fetch competitor page", "our_url": our_url}

        if api_key:
            result = await self._groq_compare_pages(
                our_url, competitor_url, our_content[:3000], their_content[:3000]
            )
        else:
            result = self._heuristic_gap_analysis(
                our_url.replace("https://empire-ai.co.uk", ""), "general",
                [{"url": competitor_url, "content": their_content[:3000]}],
                our_content[:3000]
            )

        result["our_url"] = our_url
        result["competitor_url"] = competitor_url
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["scans"] += 1
        return result

    # ── SERP SEARCH (camofox-browser, falls back to httpx) ────────────

    async def _serp_search(self, keyword: str, metro: str, top_n: int) -> List[str]:
        """Google SERP search via camofox-browser (JS-rendered, anti-bot resistant).

        Uses camofox /links endpoint to extract real hrefs (not a11y snapshot text).
        Falls back to httpx + known competitors if camofox is unreachable.
        """
        query = f"{keyword} {metro}".strip()
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={top_n}"

        # Try camofox-browser first — use /links endpoint for real hrefs
        camofox_ok = await camofox_health()
        if camofox_ok:
            try:
                urls = await camofox_fetch_links(search_url, session_key=f"serp-{keyword[:20]}")
                if urls:
                    seen = set()
                    clean = []
                    for u in urls:
                        if any(d in u for d in ["google.com", "youtube.com", "gstatic.com", "googleapis.com"]):
                            continue
                        if u not in seen:
                            seen.add(u)
                            clean.append(u)
                    if clean:
                        log.info(f"[gap] camofox SERP: {len(clean)} URLs for '{keyword}'")
                        return clean[:top_n]
            except Exception as e:
                log.warning(f"[gap] camofox SERP failed: {e}")

        # Fallback: httpx direct (may fail due to Google anti-bot)
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(
                    search_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; EmpireAI/1.0; +https://empire-ai.co.uk)"},
                )
                if r.status_code == 200:
                    urls = re.findall(r'href="https?://([^"]+)"', r.text)
                    seen = set()
                    clean = []
                    for u in urls:
                        if "google.com" in u or "youtube.com" in u:
                            continue
                        if u not in seen:
                            seen.add(u)
                            clean.append(f"https://{u}")
                    if clean:
                        return clean[:top_n]
        except Exception as e:
            log.warning(f"[gap] httpx SERP search failed: {e}")

        # Final fallback: known competitor URLs
        return self._fallback_competitors(keyword)

    def _fallback_competitors(self, keyword: str) -> List[str]:
        """Known competitor URLs for common niches when scraping fails."""
        domain_map = {
            "roof": ["roofinginsights.com", "roofingcontractor.com", "iko.com/roofing"],
            "hvac": ["hvac.com", "achrnews.com", "carrier.com/residential"],
            "solar": ["energysage.com/solar", "solarreviews.com", "sunpower.com"],
            "restoration": ["servpro.com", "rainbowintl.com", "restoration1.com"],
            "plumb": ["plumbingtoday.com", "rotorooter.com", "mrrooter.com"],
            "electric": ["mrelectric.com", "generac.com", "kohlerpower.com"],
        }
        for k, urls in domain_map.items():
            if k in keyword.lower():
                return [f"https://{u}" for u in urls]
        return ["https://www.angi.com", "https://www.homeadvisor.com", "https://www.thumbtack.com"]

    # ── PAGE SCRAPING ────────────────────────────────────────────────

    async def _scrape_page(self, url: str) -> Optional[str]:
        """Scrape page content via camofox-browser (JS-rendered, anti-bot resistant).
        Falls back to httpx if camofox is unreachable."""
        # Try camofox-browser first
        camofox_ok = await camofox_health()
        if camofox_ok:
            try:
                html = await camofox_fetch_snapshot(url, session_key=f"page-{url[:30]}")
                if html:
                    # Extract title + clean text from camofox a11y snapshot
                    title_match = re.search(r'TITLE:\s*(.+)', html, re.IGNORECASE)
                    title = title_match.group(1).strip() if title_match else url
                    # camofox returns accessibility snapshot — already clean text
                    clean = re.sub(r'\s+', ' ', html).strip()
                    result = f"TITLE: {title}\nCONTENT: {clean[:3000]}"
                    return result
            except Exception as e:
                log.debug(f"[gap] camofox page scrape failed for {url}: {e}")

        # Fallback: httpx direct
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; EmpireAI/1.0; +https://empire-ai.co.uk)"},
                )
                if r.status_code != 200:
                    return None
                text = r.text
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                title_match = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE)
                title = title_match.group(1) if title_match else ""
                clean = re.sub(r'<[^>]+>', ' ', text)
                clean = re.sub(r'\s+', ' ', clean).strip()
                return f"TITLE: {title}\nCONTENT: {clean[:3000]}"
        except Exception as e:
            log.debug(f"[gap] httpx scrape failed for {url}: {e}")
            return None

    # ── GROQ ANALYSIS ────────────────────────────────────────────────

    async def _groq_gap_analysis(
        self, keyword: str, niche: str, metro: str,
        competitors: List[dict], our_content: str
    ) -> Dict[str, Any]:
        """Use Groq to analyze content gaps."""
        api_key = self.api_key
        if not api_key:
            return self._heuristic_gap_analysis(keyword, niche, competitors, our_content)

        competitor_text = "\n\n---\n\n".join(
            f"COMPETITOR: {c['url']}\n{c['content']}" for c in competitors
        )
        prompt = (
            f"Target Keyword: {keyword}\n"
            f"Niche: {niche or 'general'}\n"
            f"Metro: {metro or 'national'}\n\n"
            f"OUR PAGE CONTENT:\n{our_content or '(no content — we have no page targeting this keyword)'}\n\n"
            f"COMPETITOR CONTENT:\n{competitor_text}\n\n"
            f"Analyze the gaps. What do competitors cover that we don't? Be specific about topics, "
            f"keywords, and angles. Return JSON only."
        )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": GAP_ANALYSIS_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 800,
                        "temperature": 0.3,
                    },
                )
                if r.status_code != 200:
                    return self._heuristic_gap_analysis(keyword, niche, competitors, our_content)

                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._parse_gap_response(content, keyword, niche)

        except Exception as e:
            log.warning(f"[gap] Groq analysis failed: {e}")
            self.stats["errors"] += 1
            return self._heuristic_gap_analysis(keyword, niche, competitors, our_content)

    async def _groq_compare_pages(
        self, our_url: str, competitor_url: str, our_content: str, their_content: str
    ) -> Dict[str, Any]:
        """Direct page-to-page comparison via Groq."""
        api_key = self.api_key
        prompt = (
            f"OUR PAGE ({our_url}):\n{our_content}\n\n"
            f"COMPETITOR PAGE ({competitor_url}):\n{their_content}\n\n"
            f"Compare these two pages. What content/topics/keywords does the competitor "
            f"cover that we don't? What are we doing better? Return JSON only."
        )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": GAP_ANALYSIS_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 800,
                        "temperature": 0.3,
                    },
                )
                if r.status_code != 200:
                    return self._empty_scan_result("page comparison", "general", "")
                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._parse_gap_response(content, "page comparison", "general")
        except Exception as e:
            log.warning(f"[gap] compare failed: {e}")
            return self._empty_scan_result("page comparison", "general", "")

    # ── RESPONSE PARSING ─────────────────────────────────────────────

    def _parse_gap_response(self, content: str, keyword: str, niche: str) -> dict:
        """Parse Groq JSON response with markdown-fence handling."""
        clean = content.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            return self._heuristic_gap_analysis(keyword, niche, [], "")

        return {
            "keyword": keyword,
            "niche": niche,
            "gaps": parsed.get("gaps", []),
            "competitor_strengths": parsed.get("competitor_strengths", []),
            "our_strengths": parsed.get("our_strengths", []),
            "severity": parsed.get("overall_gap_severity", "medium"),
            "summary": parsed.get("summary", ""),
        }

    # ── HEURISTIC FALLBACK ───────────────────────────────────────────

    def _heuristic_gap_analysis(
        self, keyword: str, niche: str, competitors: List[dict], our_content: str
    ) -> dict:
        """Rule-based gap analysis when Groq is unavailable or scraping fails."""
        gaps = []

        # Default gaps based on keyword and niche
        if niche and not our_content:
            gaps.append({
                "topic": f"{niche.title()} services in your area",
                "keyword_angle": f"{keyword} with local intent",
                "missing_from_our_page": True,
                "priority": 9,
                "estimated_search_volume": "high",
                "recommended_action": f"Create a dedicated /for-{niche} landing page optimized for '{keyword}'",
            })

        # If keyword contains price/cost terms
        if any(w in keyword.lower() for w in ["cost", "price", "estimate", "quote"]):
            gaps.append({
                "topic": f"Cost breakdown for {keyword}",
                "keyword_angle": f"{keyword}: what to expect",
                "missing_from_our_page": True,
                "priority": 8,
                "estimated_search_volume": "medium",
                "recommended_action": "Add pricing estimator / calculator page with schema markup",
            })

        # Generic content gaps
        gaps.append({
            "topic": "Customer reviews and case studies",
            "keyword_angle": f"{niche or keyword} reviews and testimonials",
            "missing_from_our_page": not our_content,
            "priority": 7,
            "estimated_search_volume": "medium",
            "recommended_action": "Add verified customer reviews with Review schema markup",
        })

        return {
            "keyword": keyword,
            "niche": niche,
            "gaps": gaps,
            "competitor_strengths": ["More comprehensive service pages", "More customer reviews"],
            "our_strengths": ["Real-time storm damage data", "Live contractor network", "Instant dispatch"],
            "severity": "medium",
            "summary": f"Competitors have better content depth for '{keyword}'. We should create/optimize niche landing pages.",
        }

    def _empty_scan_result(self, keyword: str, niche: str, metro: str) -> dict:
        return {
            "keyword": keyword,
            "niche": niche,
            "metro": metro,
            "gaps": [],
            "competitors_analyzed": 0,
            "severity": "unknown",
            "summary": "Could not fetch competitor data — gap scan skipped.",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    def snapshot(self) -> dict:
        return {
            "model": self.model,
            "api_configured": bool(self.api_key),
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
