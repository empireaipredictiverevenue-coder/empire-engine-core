"""
EMPIRE V49 · AGENT-REACH ENRICHMENT LAYER
==========================================
Wraps the Agent-Reach (v1.5.0) installed CLI tools into async Python
enrichment functions.  Provides 19 intelligence channels for the Elite
Scraper product:

  - semantic_search    — Exa web search via mcporter (free, no API key)
  - github_search      — GitHub code/repo/issue search via gh api
  - jina_read          — Read any URL as clean Markdown via Jina Reader
  - rss_fetch          — Fetch and parse RSS/Atom feeds via curl
  - youtube_transcript — Extract YouTube subtitles via yt-dlp
  - v2ex_browse        — Browse V2EX topics via public API
  - bilibili_search    — Search Bilibili videos (needs `bili` CLI)
  - twitter_search     — Search Twitter/X (needs `twitter` CLI)
  - reddit_search      — Search Reddit (needs `opencli` or `rdt` CLI)
  - hn_search          — Hacker News search via Algolia API (free, no key)
  - arxiv_search       — Academic paper search via arXiv API (free, no key)
  - wayback_fetch      — Internet Archive Wayback Machine content (free, no key)
  - wikipedia_search   — Wikipedia article search/summary (free, no key)
  - cloudscraper_fetch — Fetch Cloudflare-protected pages (cloudscraper)
  - crawl4ai           — Deep web crawling via Crawl4AI async library
  - apify_scrape       — Apify platform scraping (apify_client)
  - google_web_search  — Google Programmable Search (needs API key + CSE ID)
  - claude_analyze     — AI analysis via Anthropic Claude (needs API key)
  - dns_geo_lookup     — DNS + geolocation intelligence (dnspython + geopy)

Architecture:
    Elite Scraper → AgentReachEnricher → mcporter/curl/yt-dlp/gh → internet
                  → cache (Supabase agent_reach_cache table)
                  → output (Supabase enrichment_results)

Usage:
    enricher = AgentReachEnricher(get_db=get_db)
    results = await enricher.enrich(query="roofing contractors Dallas TX",
                                     channels=["semantic_search", "github_search"],
                                     max_results=5)
"""

import os
import sys
import re
import json
import uuid
import time
import asyncio
import logging
import hashlib
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional
from pathlib import Path

log = logging.getLogger("empire.agent_reach")

# ── Channel Configuration ───────────────────────────────────────────
CHANNELS = {
    "semantic_search": {
        "description": "Exa semantic web search via mcporter (free, no API key required)",
        "cost": "free",
        "rate_limit": "20/min",
        "installed": True,
        "test_cmd": ["mcporter", "call", 'exa.web_search_exa(query: "test", numResults: 1)'],
    },
    "github_search": {
        "description": "GitHub code/repo/issue search via gh api",
        "cost": "free (rate-limited)",
        "rate_limit": "30/min",
        "installed": True,
        "test_cmd": ["gh", "api", "search/repositories?q=test&per_page=1"],
    },
    "jina_read": {
        "description": "Read any URL as clean Markdown via Jina Reader",
        "cost": "free",
        "rate_limit": "60/min",
        "installed": True,
        "test_cmd": ["curl", "-s", "https://r.jina.ai/https://example.com"],
    },
    "rss_fetch": {
        "description": "Fetch and parse RSS/Atom feeds via curl",
        "cost": "free",
        "rate_limit": "30/min",
        "installed": True,
        "test_cmd": ["curl", "-s", "https://hnrss.org/frontpage"],
    },
    "youtube_transcript": {
        "description": "Extract YouTube video subtitles via yt-dlp",
        "cost": "free",
        "rate_limit": "10/min",
        "installed": True,
        "test_cmd": ["yt-dlp", "--version"],
    },
    "v2ex_browse": {
        "description": "Browse V2EX topics via public API",
        "cost": "free",
        "rate_limit": "30/min",
        "installed": True,
        "test_cmd": ["curl", "-s", "-H", "User-Agent: agent-reach/1.0",
                      "https://www.v2ex.com/api/topics/hot.json"],
    },
    "bilibili_search": {
        "description": "Search Bilibili videos via bili CLI",
        "cost": "free",
        "rate_limit": "20/min",
        "installed": True,
        "test_cmd": ["bili", "search", "test", "--type", "video", "-n", "1"],
    },
    "twitter_search": {
        "description": "Search Twitter/X via twitter CLI (needs browser cookie auth)",
        "cost": "free",
        "rate_limit": "15/min",
        "installed": True,
        "auth_note": "Requires Twitter browser cookies. Run: twitter auth --browser chrome",
    },
    "reddit_search": {
        "description": "Search Reddit via rdt CLI (needs OAuth setup)",
        "cost": "free",
        "rate_limit": "30/min",
        "installed": True,
        "auth_note": "Requires Reddit OAuth. Run: rdt --authenticate  or  export RDT_REFRESH_TOKEN=...",
    },

    # ── New Channel Expansion (v2) ───────────────────────────────
    "hn_search": {
        "description": "Hacker News search via Algolia public API",
        "cost": "free",
        "rate_limit": "60/min",
        "installed": True,
        "test_cmd": ["curl", "-s", "https://hn.algolia.com/api/v1/search?query=test&hitsPerPage=1"],
    },
    "arxiv_search": {
        "description": "Academic paper search via arXiv API",
        "cost": "free",
        "rate_limit": "30/min",
        "installed": True,
        "test_cmd": ["curl", "-s", "http://export.arxiv.org/api/query?search_query=all:test&max_results=1"],
    },
    "wayback_fetch": {
        "description": "Internet Archive Wayback Machine content retrieval via CDX API",
        "cost": "free",
        "rate_limit": "20/min",
        "installed": True,
    },
    "wikipedia_search": {
        "description": "Wikipedia article search and summary via public API",
        "cost": "free",
        "rate_limit": "60/min",
        "installed": True,
    },
    "cloudscraper_fetch": {
        "description": "Fetch Cloudflare-protected pages via cloudscraper Python library",
        "cost": "free",
        "rate_limit": "15/min",
        "installed": True,
        "auth_note": "No API key required — uses browser-like TLS fingerprinting to bypass Cloudflare. Some sites may still block.",
    },
    "crawl4ai": {
        "description": "Deep web crawling via Crawl4AI async library — full JS rendering, link extraction, content parsing",
        "cost": "free",
        "rate_limit": "10/min",
        "installed": True,
        "auth_note": "No API key required. Uses local headless browser for JS rendering. May be resource-intensive.",
    },
    "apify_scrape": {
        "description": "Apify platform scraping via apify_client — access Apify Actor marketplace",
        "cost": "variable (Apify usage credits)",
        "rate_limit": "20/min",
        "installed": True,
        "auth_note": "Requires Apify API token. Set APIFY_TOKEN env var. Get one at console.apify.com.",
    },
    "google_web_search": {
        "description": "Google Programmable Search via google-api-python-client",
        "cost": "free (100 queries/day via free tier)",
        "rate_limit": "10/min",
        "installed": True,
        "auth_note": "Requires GOOGLE_API_KEY and GOOGLE_CSE_ID env vars. Set up at programmablesearch.google.com.",
    },
    "claude_analyze": {
        "description": "AI-powered content analysis via Anthropic Claude SDK",
        "cost": "variable (Anthropic API usage)",
        "rate_limit": "10/min",
        "installed": True,
        "auth_note": "Requires ANTHROPIC_API_KEY env var. Get one at console.anthropic.com.",
    },
    "dns_geo_lookup": {
        "description": "DNS resolution + IP geolocation intelligence via dnspython + geopy",
        "cost": "free",
        "rate_limit": "30/min",
        "installed": True,
    },
}

# ── Tier Channel Access ─────────────────────────────────────────────
TIER_CHANNELS = {
    "SCRAPER_STARTER":     ["jina_read"],
    "SCRAPER_PRO":         [
        "jina_read", "semantic_search", "rss_fetch", "github_search",
        "hn_search", "wikipedia_search", "wayback_fetch",
        "youtube_transcript", "twitter_search", "reddit_search",
        "arxiv_search",
    ],
    "SCRAPER_ENTERPRISE":  [c for c in CHANNELS],
}

# ── SI Genome Archetypes ─────────────────────────────────────────────
GENOME_ARCHETYPES = {
    "AGGRESSIVE_STRIKE": {
        "description": "Wide-net aggressive — maximum channel coverage, high volume, paid channels enabled",
        "genome": {"aggressiveness": 0.9, "narrow_focus": 0.3, "risk_tolerance": 0.7, "price_premium": 0.8, "outreach_intensity": 0.9},
    },
    "RECALL_SNIPER": {
        "description": "Precision-targeted — ultra-focused on high-intent signals, social + paid channels",
        "genome": {"aggressiveness": 0.7, "narrow_focus": 0.8, "risk_tolerance": 0.5, "price_premium": 0.5, "outreach_intensity": 0.8},
    },
    "UGLY_BANNER": {
        "description": "Conservative — no paid channels, no experimental, moderate volume",
        "genome": {"aggressiveness": 0.4, "narrow_focus": 0.5, "risk_tolerance": 0.3, "price_premium": 0.2, "outreach_intensity": 0.6},
    },
    "FINANCIAL_STRIKE": {
        "description": "Balanced-aggressive — wide coverage with paid channels and high volume",
        "genome": {"aggressiveness": 0.8, "narrow_focus": 0.4, "risk_tolerance": 0.6, "price_premium": 0.7, "outreach_intensity": 0.7},
    },
    "STANDARD": {
        "description": "Balanced — moderate coverage with paid channels at baseline volume",
        "genome": {"aggressiveness": 0.5, "narrow_focus": 0.5, "risk_tolerance": 0.5, "price_premium": 0.5, "outreach_intensity": 0.5},
    },
}


class AgentReachEnricher:
    """Async wrapper around Agent-Reach installed CLI tools.

    Call pattern:
        enricher = AgentReachEnricher(get_db=get_db)
        results = await enricher.enrich(
            query="roofing contractors Dallas TX",
            channels=["semantic_search", "github_search"],
            max_results=5,
        )
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._rate_limits: dict[str, list[float]] = {}  # channel → [timestamps]
        self._rate_window = 60  # seconds

    # ── Rate Limiting ────────────────────────────────────────────
    def _check_rate(self, channel: str) -> bool:
        """True if we can make another call for this channel right now."""
        now = time.time()
        timestamps = self._rate_limits.setdefault(channel, [])
        timestamps[:] = [t for t in timestamps if now - t < self._rate_window]
        cfg = CHANNELS.get(channel, {})
        limit_str = cfg.get("rate_limit", "30/min")
        limit = int(limit_str.split("/")[0])
        return len(timestamps) < limit

    def _record_call(self, channel: str):
        now = time.time()
        self._rate_limits.setdefault(channel, []).append(now)

    # ── Generic Subprocess Runner ────────────────────────────────
    async def _run_cmd(self, *args, timeout: int = 30, channel: str = "unknown") -> dict:
        """Run any CLI tool and return parsed output.

        Attempts JSON parse first; falls back to raw text.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return {
                    "ok": False,
                    "error": stderr_str or f"exit code {proc.returncode}",
                    "channel": channel,
                }

            # Try JSON; fall back to raw text
            try:
                data = json.loads(stdout_str)
                return {"ok": True, "data": data, "channel": channel, "format": "json"}
            except json.JSONDecodeError:
                return {"ok": True, "data": {"text": stdout_str}, "channel": channel, "format": "text"}

        except asyncio.TimeoutError:
            return {"ok": False, "error": f"timeout after {timeout}s", "channel": channel}
        except FileNotFoundError:
            return {"ok": False, "error": f"Command not found: {args[0]}. Check Agent-Reach installation.", "channel": channel}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "channel": channel}

    # ── Channel Methods ──────────────────────────────────────────

    async def semantic_search(self, query: str, max_results: int = 10) -> dict:
        """Exa semantic web search via mcporter (free, no API key)."""
        if not self._check_rate("semantic_search"):
            return {"ok": False, "error": "rate limited", "channel": "semantic_search"}
        self._record_call("semantic_search")

        return await self._run_cmd(
            "mcporter", "call",
            f'exa.web_search_exa(query: "{query}", numResults: {max_results})',
            timeout=30,
            channel="semantic_search",
        )

    async def github_search(self, query: str, max_results: int = 10,
                            search_type: str = "repositories") -> dict:
        """Search GitHub via gh api.

        search_type: repositories | code | issues | commits
        """
        if not self._check_rate("github_search"):
            return {"ok": False, "error": "rate limited", "channel": "github_search"}
        self._record_call("github_search")

        # Quick auth check first — fail fast if gh isn't set up
        try:
            auth_check = await self._run_cmd("gh", "auth", "status", timeout=8, channel="github_search")
            if not auth_check.get("ok"):
                return {"ok": False, "error": "gh not authenticated. Run: gh auth login", "channel": "github_search"}
        except Exception:
            pass  # proceed anyway, the actual call will surface the error

        # Map search_type to GitHub API endpoint
        endpoints = {
            "repositories": "/search/repositories",
            "code": "/search/code",
            "issues": "/search/issues",
            "commits": "/search/commits",
        }
        endpoint = endpoints.get(search_type, "/search/repositories")

        return await self._run_cmd(
            "gh", "api",
            f"{endpoint}?q={query}&per_page={max_results}&sort=stars&order=desc",
            "--jq", ".items",  # Extract items array as JSON
            timeout=20,  # should be fast after auth check
            channel="github_search",
        )

    async def jina_read(self, url: str) -> dict:
        """Read any URL as clean Markdown via Jina Reader."""
        if not self._check_rate("jina_read"):
            return {"ok": False, "error": "rate limited", "channel": "jina_read"}
        self._record_call("jina_read")

        jina_url = f"https://r.jina.ai/{url}"
        return await self._run_cmd(
            "curl", "-s", jina_url,
            timeout=25,
            channel="jina_read",
        )

    async def rss_fetch(self, feed_url: str, max_items: int = 10) -> dict:
        """Fetch an RSS/Atom feed via curl."""
        if not self._check_rate("rss_fetch"):
            return {"ok": False, "error": "rate limited", "channel": "rss_fetch"}
        self._record_call("rss_fetch")

        result = await self._run_cmd(
            "curl", "-s", "-L", "--max-time", "20", feed_url,
            timeout=25,
            channel="rss_fetch",
        )

        # Try to parse as XML/JSON feed; return raw if not
        if result.get("ok") and result.get("format") == "text":
            raw = result.get("data", {}).get("text", "")
            # Simple RSS item extraction via regex
            items = re.findall(r'<item>(.*?)</item>', raw, re.DOTALL)
            if not items:
                items = re.findall(r'<entry>(.*?)</entry>', raw, re.DOTALL)  # Atom
            if items:
                parsed = []
                for item in items[:max_items]:
                    title = re.search(r'<title[^>]*>(.*?)</title>', item, re.DOTALL)
                    link = re.search(r'<link[^>]*href="(.*?)"', item)
                    if not link:
                        link = re.search(r'<link[^>]*>(.*?)</link>', item)
                    desc = re.search(r'<description[^>]*>(.*?)</description>', item, re.DOTALL)
                    parsed.append({
                        "title": (title.group(1) if title else "")[:200],
                        "url": (link.group(1) if link else ""),
                        "description": (desc.group(1) if desc else "")[:500],
                    })
                result["data"] = {"items": parsed}
                result["format"] = "json"
        return result

    async def youtube_transcript(self, video_url: str) -> dict:
        """Extract YouTube video subtitles via yt-dlp."""
        if not self._check_rate("youtube_transcript"):
            return {"ok": False, "error": "rate limited", "channel": "youtube_transcript"}
        self._record_call("youtube_transcript")

        # We use a deterministic output template so we can read the file after
        import tempfile
        video_id = re.search(r'(?:v=|/)([a-zA-Z0-9_-]{11})', video_url)
        v_id = video_id.group(1) if video_id else uuid.uuid4().hex[:11]
        out_template = f"/tmp/agent_reach_{v_id}"

        result = await self._run_cmd(
            "yt-dlp",
            "--write-sub", "--skip-download",
            "--sub-lang", "en",
            "--convert-subs", "srt",
            "-o", out_template,
            video_url,
            timeout=40,
            channel="youtube_transcript",
        )

        # Read the subtitle file if it exists
        sub_file = f"{out_template}.en.srt"
        if os.path.exists(sub_file):
            try:
                with open(sub_file, "r", encoding="utf-8", errors="replace") as f:
                    subtitle_text = f.read()
                # Clean up temp file
                os.remove(sub_file)
                # Parse SRT into usable format
                result["data"] = {"transcript": subtitle_text[:10000], "format": "srt"}
                result["format"] = "json"
            except Exception as e:
                log.debug(f"[agent_reach] subtitle read error: {e}")
        elif os.path.exists(f"{out_template}.en.vtt"):
            sub_file = f"{out_template}.en.vtt"
            try:
                with open(sub_file, "r", encoding="utf-8", errors="replace") as f:
                    subtitle_text = f.read()
                os.remove(sub_file)
                result["data"] = {"transcript": subtitle_text[:10000], "format": "vtt"}
                result["format"] = "json"
            except Exception as e:
                log.debug(f"[agent_reach] subtitle read error: {e}")

        return result

    async def v2ex_browse(self, node: str = "", max_results: int = 10) -> dict:
        """Browse V2EX topics via public API."""
        if not self._check_rate("v2ex_browse"):
            return {"ok": False, "error": "rate limited", "channel": "v2ex_browse"}
        self._record_call("v2ex_browse")

        if node:
            url = f"https://www.v2ex.com/api/topics/show.json?node_name={node}"
        else:
            url = "https://www.v2ex.com/api/topics/hot.json"

        return await self._run_cmd(
            "curl", "-s", url,
            "-H", "User-Agent: agent-reach/1.0",
            timeout=20,
            channel="v2ex_browse",
        )

    # ── Channels Requiring Extra CLI Installation ────────────────

    async def bilibili_search(self, query: str, max_results: int = 10) -> dict:
        """Search Bilibili videos via bili CLI."""
        if not self._check_rate("bilibili_search"):
            return {"ok": False, "error": "rate limited", "channel": "bilibili_search"}
        self._record_call("bilibili_search")

        return await self._run_cmd(
            "bili", "search", query,
            "--type", "video", "-n", str(max_results),
            timeout=25,
            channel="bilibili_search",
        )

    async def twitter_search(self, query: str, max_results: int = 10) -> dict:
        """Search Twitter/X via twitter CLI."""
        if not self._check_rate("twitter_search"):
            return {"ok": False, "error": "rate limited", "channel": "twitter_search"}
        self._record_call("twitter_search")

        return await self._run_cmd(
            "twitter", "search", query, "-n", str(max_results),
            timeout=30,
            channel="twitter_search",
        )

    async def reddit_search(self, query: str, max_results: int = 10) -> dict:
        """Search Reddit via rdt CLI."""
        if not self._check_rate("reddit_search"):
            return {"ok": False, "error": "rate limited", "channel": "reddit_search"}
        self._record_call("reddit_search")

        return await self._run_cmd(
            "rdt", "search", query, "--limit", str(max_results),
            timeout=30,
            channel="reddit_search",
        )

    # ── New Channels (v2) ────────────────────────────────────────

    async def hn_search(self, query: str, max_results: int = 10) -> dict:
        """Search Hacker News via Algolia API."""
        if not self._check_rate("hn_search"):
            return {"ok": False, "error": "rate limited", "channel": "hn_search"}
        self._record_call("hn_search")

        import urllib.parse
        params = urllib.parse.urlencode({"query": query, "hitsPerPage": max_results})
        url = f"https://hn.algolia.com/api/v1/search?{params}"

        return await self._run_cmd(
            "curl", "-s", url,
            "-H", "User-Agent: agent-reach/1.0",
            timeout=15,
            channel="hn_search",
        )

    async def arxiv_search(self, query: str, max_results: int = 10) -> dict:
        """Search academic papers via arXiv API."""
        if not self._check_rate("arxiv_search"):
            return {"ok": False, "error": "rate limited", "channel": "arxiv_search"}
        self._record_call("arxiv_search")

        import urllib.parse
        safe_q = urllib.parse.quote(f'all:"{query}"')
        url = f"http://export.arxiv.org/api/query?search_query={safe_q}&max_results={max_results}&sortBy=relevance&sortOrder=descending"

        result = await self._run_cmd(
            "curl", "-s", "-L", url,
            "-H", "User-Agent: agent-reach/1.0",
            timeout=20,
            channel="arxiv_search",
        )

        # Parse Atom XML into structured entries
        if result.get("ok") and result.get("format") == "text":
            raw = result.get("data", {}).get("text", "")
            entries = re.findall(r'<entry>(.*?)</entry>', raw, re.DOTALL)
            if entries:
                parsed = []
                for entry in entries[:max_results]:
                    title = re.search(r'<title[^>]*>(.*?)</title>', entry, re.DOTALL)
                    summary = re.search(r'<summary[^>]*>(.*?)</summary>', entry, re.DOTALL)
                    link = re.search(r'<link[^>]*href="(.*?)"', entry)
                    authors = re.findall(r'<name>(.*?)</name>', entry)
                    parsed.append({
                        "title": (title.group(1).strip() if title else "")[:300],
                        "summary": (summary.group(1).strip() if summary else "")[:800],
                        "url": (link.group(1) if link else ""),
                        "authors": [a.strip() for a in authors[:5]],
                    })
                result["data"] = {"papers": parsed}
                result["format"] = "json"
        return result

    async def wayback_fetch(self, url: str, max_results: int = 5) -> dict:
        """Fetch archived versions of a URL from Wayback Machine."""
        if not self._check_rate("wayback_fetch"):
            return {"ok": False, "error": "rate limited", "channel": "wayback_fetch"}
        self._record_call("wayback_fetch")

        import urllib.parse
        safe_url = urllib.parse.quote(url)
        cdx_url = f"https://web.archive.org/cdx/search/cdx?url={safe_url}&output=json&limit={max_results}&fl=timestamp,original,statuscode"

        result = await self._run_cmd(
            "curl", "-s", cdx_url,
            "-H", "User-Agent: agent-reach/1.0",
            timeout=20,
            channel="wayback_fetch",
        )

        # Parse CDX JSON: first row is header, rest are entries
        if result.get("ok") and result.get("format") == "json":
            data = result.get("data", [])
            if isinstance(data, list) and len(data) > 1:
                entries = []
                for row in data[1:1 + max_results]:
                    if len(row) >= 3:
                        ts, original, status = row[0], row[1], row[2]
                        wayback_url = f"https://web.archive.org/web/{ts}/{original}"
                        entries.append({
                            "timestamp": ts,
                            "original_url": original,
                            "status_code": status,
                            "wayback_url": wayback_url,
                        })
                result["data"] = {"snapshots": entries}
        return result

    async def wikipedia_search(self, query: str, max_results: int = 5) -> dict:
        """Search Wikipedia and retrieve article summaries."""
        if not self._check_rate("wikipedia_search"):
            return {"ok": False, "error": "rate limited", "channel": "wikipedia_search"}
        self._record_call("wikipedia_search")

        import urllib.parse
        safe_q = urllib.parse.quote(query)

        # Step 1: search
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={safe_q}&format=json&srlimit={max_results}"
        search_result = await self._run_cmd(
            "curl", "-s", search_url,
            "-H", "User-Agent: agent-reach/1.0",
            timeout=15,
            channel="wikipedia_search",
        )

        if not search_result.get("ok"):
            return search_result

        # Step 2: extract page IDs and get summaries
        data = search_result.get("data", {})
        if isinstance(data, dict):
            query_data = data.get("query", {})
            search_results = query_data.get("search", [])
            if search_results:
                page_ids = [str(r["pageid"]) for r in search_results if "pageid" in r]
                if page_ids:
                    ids = "|".join(page_ids[:max_results])
                    summary_url = f"https://en.wikipedia.org/w/api.php?action=query&pageids={ids}&prop=extracts&exintro=true&exlimit={max_results}&explaintext=true&format=json"
                    summary_result = await self._run_cmd(
                        "curl", "-s", summary_url,
                        "-H", "User-Agent: agent-reach/1.0",
                        timeout=15,
                        channel="wikipedia_search",
                    )
                    if summary_result.get("ok"):
                        pages_data = summary_result.get("data", {})
                        if isinstance(pages_data, dict):
                            pages = pages_data.get("query", {}).get("pages", {})
                            entries = []
                            for pid, page in pages.items():
                                entries.append({
                                    "title": page.get("title", ""),
                                    "summary": (page.get("extract", "") or "")[:1500],
                                    "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page.get('title', '').replace(' ', '_'))}",
                                })
                            search_result["data"] = {"articles": entries}
                            search_result["format"] = "json"

        return search_result

    async def cloudscraper_fetch(self, url: str, max_results: int = 1) -> dict:
        """Fetch a Cloudflare-protected page using cloudscraper."""
        if not self._check_rate("cloudscraper_fetch"):
            return {"ok": False, "error": "rate limited", "channel": "cloudscraper_fetch"}
        self._record_call("cloudscraper_fetch")

        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                interpreter="node",  # Use Node.js challenge solver if available
                delay=5,
            )
            resp = scraper.get(url, timeout=25, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            })
            if resp.status_code == 200:
                text = resp.text[:50000]
                return {
                    "ok": True,
                    "data": {"text": text, "url": url, "status_code": resp.status_code},
                    "channel": "cloudscraper_fetch",
                    "format": "text",
                }
            else:
                return {
                    "ok": False,
                    "error": f"HTTP {resp.status_code}",
                    "channel": "cloudscraper_fetch",
                }
        except ImportError:
            return {"ok": False, "error": "cloudscraper not installed", "channel": "cloudscraper_fetch"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "channel": "cloudscraper_fetch"}

    async def crawl4ai(self, url: str, max_results: int = 10) -> dict:
        """Deep crawl a URL using Crawl4AI async library.

        Returns extracted content, links, and metadata.
        Uses CrawlerRunConfig with cache_mode for newer Crawl4AI API compatibility.
        """
        if not self._check_rate("crawl4ai"):
            return {"ok": False, "error": "rate limited", "channel": "crawl4ai"}
        self._record_call("crawl4ai")

        try:
            from crawl4ai import AsyncWebCrawler, CacheMode
            from crawl4ai.async_configs import CrawlerRunConfig

            config = CrawlerRunConfig(
                word_count_threshold=10,
                cache_mode=CacheMode.BYPASS,
                verbose=False,
            )
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url, config=config)
                if result.success:
                    return {
                        "ok": True,
                        "data": {
                            "title": result.metadata.get("title", "") if result.metadata else "",
                            "content": (result.markdown or result.html or "")[:30000],
                            "links": list(result.links.get("internal", []) + result.links.get("external", []))[:50] if result.links else [],
                            "url": url,
                        },
                        "channel": "crawl4ai",
                        "format": "json",
                    }
                else:
                    return {"ok": False, "error": result.error_message or "crawl failed", "channel": "crawl4ai"}
        except ImportError:
            return {"ok": False, "error": "crawl4ai not installed", "channel": "crawl4ai"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "channel": "crawl4ai"}

    async def apify_scrape(self, query: str, max_results: int = 10,
                           actor_id: str = "apify/web-scraper") -> dict:
        """Scrape via Apify platform using apify_client.

        Args:
            query: Search query or URL to scrape
            max_results: Max results
            actor_id: Apify Actor ID (default: web-scraper)
        """
        if not self._check_rate("apify_scrape"):
            return {"ok": False, "error": "rate limited", "channel": "apify_scrape"}
        self._record_call("apify_scrape")

        api_token = os.environ.get("APIFY_TOKEN", "")
        if not api_token:
            return {"ok": False, "error": "APIFY_TOKEN not set", "channel": "apify_scrape"}

        try:
            from apify_client import ApifyClient
            client = ApifyClient(api_token)

            # Determine if query is a URL or a search term
            is_url = query.startswith("http://") or query.startswith("https://")

            if is_url:
                run_input = {
                    "startUrls": [{"url": query}],
                    "maxPagesPerCrawl": max_results,
                    "pageFunction": """async function pageFunction(context) {
                        const $ = context.jQuery;
                        return {
                            url: context.request.url,
                            title: $('title').text(),
                            text: $('body').text().substring(0, 5000),
                        };
                    }""",
                }
            else:
                # Search via Google Search Results Scraper
                run_input = {
                    "queries": query,
                    "maxPagesPerQuery": min(max_results, 5),
                    "resultsPerPage": min(max_results, 10),
                }
                actor_id = "apify/google-search-results-scraper"

            call_result = client.actor(actor_id).call(run_input=run_input)
            dataset = client.dataset(call_result["defaultDatasetId"])
            items = dataset.list_items().items

            return {
                "ok": True,
                "data": {"items": items[:max_results]},
                "channel": "apify_scrape",
                "format": "json",
            }
        except ImportError:
            return {"ok": False, "error": "apify_client not installed", "channel": "apify_scrape"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "channel": "apify_scrape"}

    async def google_web_search(self, query: str, max_results: int = 10) -> dict:
        """Google Programmable Search via google-api-python-client."""
        if not self._check_rate("google_web_search"):
            return {"ok": False, "error": "rate limited", "channel": "google_web_search"}
        self._record_call("google_web_search")

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        cse_id = os.environ.get("GOOGLE_CSE_ID", "")
        if not api_key or not cse_id:
            return {
                "ok": False,
                "error": "GOOGLE_API_KEY and GOOGLE_CSE_ID must be set",
                "channel": "google_web_search",
            }

        try:
            from googleapiclient.discovery import build
            service = build("customsearch", "v1", developerKey=api_key, cache_discovery=False)
            result = service.cse().list(q=query, cx=cse_id, num=min(max_results, 10)).execute()

            items = result.get("items", [])
            parsed = []
            for item in items[:max_results]:
                parsed.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            return {
                "ok": True,
                "data": {"results": parsed, "total_estimated": result.get("searchInformation", {}).get("totalResults", 0)},
                "channel": "google_web_search",
                "format": "json",
            }
        except ImportError:
            return {"ok": False, "error": "google-api-python-client not installed", "channel": "google_web_search"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "channel": "google_web_search"}

    async def claude_analyze(self, prompt: str, max_results: int = 1) -> dict:
        """Analyze content using Anthropic Claude via the SDK.

        Args:
            prompt: The text or question to analyze
            max_results: Not used (Claude returns one response per call)
        """
        if not self._check_rate("claude_analyze"):
            return {"ok": False, "error": "rate limited", "channel": "claude_analyze"}
        self._record_call("claude_analyze")

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return {
                "ok": False,
                "error": "ANTHROPIC_API_KEY not set. Get one at console.anthropic.com.",
                "channel": "claude_analyze",
            }

        try:
            from anthropic import AsyncAnthropic
            from httpx import AsyncClient
            http_client = AsyncClient()
            client = AsyncAnthropic(api_key=api_key, http_client=http_client)

            # Truncate prompt to stay within token limits
            truncated = prompt[:25000]
            msg = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": truncated}],
            )

            response_text = ""
            for block in msg.content:
                if hasattr(block, "text"):
                    response_text += block.text

            await http_client.aclose()

            return {
                "ok": True,
                "data": {
                    "analysis": response_text[:10000],
                    "model": msg.model,
                    "usage": {
                        "input_tokens": msg.usage.input_tokens,
                        "output_tokens": msg.usage.output_tokens,
                    } if hasattr(msg, "usage") else {},
                },
                "channel": "claude_analyze",
                "format": "json",
            }
        except ImportError:
            return {"ok": False, "error": "anthropic SDK not installed", "channel": "claude_analyze"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "channel": "claude_analyze"}

    async def dns_geo_lookup(self, domain: str, max_results: int = 5) -> dict:
        """Perform DNS resolution + IP geolocation intelligence.

        Returns A/AAAA records, nameservers, mail servers, and geo data.
        """
        if not self._check_rate("dns_geo_lookup"):
            return {"ok": False, "error": "rate limited", "channel": "dns_geo_lookup"}
        self._record_call("dns_geo_lookup")

        result = {"ok": True, "data": {}, "channel": "dns_geo_lookup", "format": "json"}

        try:
            import dns.resolver
            from dns.exception import DNSException

            records = {}

            # A records
            try:
                a_records = dns.resolver.resolve(domain, "A")
                records["a"] = [str(r) for r in a_records]
            except DNSException:
                records["a"] = []

            # AAAA records
            try:
                aaaa_records = dns.resolver.resolve(domain, "AAAA")
                records["aaaa"] = [str(r) for r in aaaa_records]
            except DNSException:
                records["aaaa"] = []

            # NS records
            try:
                ns_records = dns.resolver.resolve(domain, "NS")
                records["ns"] = [str(r) for r in ns_records]
            except DNSException:
                records["ns"] = []

            # MX records
            try:
                mx_records = dns.resolver.resolve(domain, "MX")
                records["mx"] = [{"priority": r.preference, "server": str(r.exchange)} for r in mx_records]
            except DNSException:
                records["mx"] = []

            # TXT records
            try:
                txt_records = dns.resolver.resolve(domain, "TXT")
                records["txt"] = [" ".join([s.decode() if isinstance(s, bytes) else s for s in r.strings]) for r in txt_records[:5]]
            except DNSException:
                records["txt"] = []

            result["data"]["dns"] = records

            # Geo lookup on first A record IP
            if records["a"]:
                try:
                    from geopy.geocoders import Nominatim
                    geolocator = Nominatim(user_agent="agent-reach/1.0")
                    location = geolocator.geocode(records["a"][0], timeout=10)
                    if location:
                        result["data"]["geo"] = {
                            "ip": records["a"][0],
                            "address": location.address,
                            "latitude": location.latitude,
                            "longitude": location.longitude,
                        }
                    else:
                        result["data"]["geo"] = {"ip": records["a"][0], "address": None}
                except Exception:
                    result["data"]["geo"] = {"ip": records["a"][0], "geo_lookup_failed": True}

            result["data"]["domain"] = domain

        except ImportError as e:
            missing = "dnspython" if "dns" not in sys.modules else "geopy"
            return {"ok": False, "error": f"{missing} not installed", "channel": "dns_geo_lookup"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "channel": "dns_geo_lookup"}

        return result

    # ── SI Genome → Channel Selection ──────────────────────────────
    @staticmethod
    def _si_select_channels(genome: dict, tier_channels: list[str]) -> list[str]:
        """Select Agent-Reach channels based on SI genome traits.

        Maps each genome trait (0.0-1.0) to channel selection decisions:

          narrow_focus:     0=wide net (RSS, HN, Wikipedia, arXiv, V2EX)
                            1=ultra-targeted (GitHub, Google, semantic, DNS)

          aggressiveness:   controls how many channels to use in parallel
                            low → only essential; high → full suite

          risk_tolerance:   enables experimental/unreliable channels
                            (cloudscraper, apify, crawl4ai)

          outreach_intensity: scales result volume
                              multiplies max_results per channel

          price_premium:    enables paid/API-key channels
                            (Google, Apify, Claude)

        Args:
            genome: SI genome dict with trait keys, or empty dict for fallback
            tier_channels: full list of channels allowed by the customer's tier

        Returns:
            Filtered list of channels appropriate for this strategy genome.
        """
        if not genome:
            return list(tier_channels) if tier_channels else ["jina_read"]

        a = genome.get("aggressiveness", 0.5)       # 0.0-1.0
        r = genome.get("risk_tolerance", 0.5)        # 0.0-1.0
        o = genome.get("outreach_intensity", 0.5)    # 0.0-1.0
        p = genome.get("price_premium", 0.5)         # 0.0-1.0
        n = genome.get("narrow_focus", 0.5)          # 0.0-1.0

        tier_set = set(tier_channels)
        selected = set()

        # ── Universal: always include if available ──
        for ch in ["jina_read", "semantic_search"]:
            if ch in tier_set:
                selected.add(ch)

        # ── Narrow Focus: broad vs targeted ──
        if n < 0.35:
            # Wide net: cast broadly across many discovery sources
            for ch in ["rss_fetch", "hn_search", "wikipedia_search",
                       "arxiv_search", "v2ex_browse", "bilibili_search"]:
                if ch in tier_set:
                    selected.add(ch)
        elif n < 0.65:
            # Balanced: mix of discovery and targeted
            for ch in ["rss_fetch", "hn_search", "semantic_search",
                       "github_search", "wayback_fetch"]:
                if ch in tier_set:
                    selected.add(ch)
        else:
            # Ultra-targeted: precision channels only
            for ch in ["semantic_search", "github_search", "google_web_search",
                       "dns_geo_lookup", "wayback_fetch"]:
                if ch in tier_set:
                    selected.add(ch)

        # ── Aggressiveness: channel quantity ──
        if a >= 0.7:
            # High aggressiveness: enable most channels
            for ch in ["crawl4ai", "cloudscraper_fetch", "youtube_transcript",
                       "twitter_search", "reddit_search", "wayback_fetch"]:
                if ch in tier_set:
                    selected.add(ch)
            # Also enable paid channels if price_premium allows
            if p >= 0.5:
                for ch in ["google_web_search", "apify_scrape", "claude_analyze"]:
                    if ch in tier_set:
                        selected.add(ch)
        elif a >= 0.4:
            # Medium: add social and media channels
            for ch in ["youtube_transcript", "reddit_search", "twitter_search"]:
                if ch in tier_set:
                    selected.add(ch)

        # ── Risk Tolerance: experimental channels ──
        if r >= 0.6:
            for ch in ["cloudscraper_fetch", "apify_scrape"]:
                if ch in tier_set:
                    selected.add(ch)

        # ── Price Premium: paid/API-key channels ──
        if p >= 0.5:
            for ch in ["google_web_search", "claude_analyze"]:
                if ch in tier_set:
                    selected.add(ch)
        if p >= 0.7 and a >= 0.5:
            if "apify_scrape" in tier_set:
                selected.add("apify_scrape")

        # ── Outreach Intensity: media volume channels ──
        if o >= 0.6:
            for ch in ["youtube_transcript", "bilibili_search", "rss_fetch"]:
                if ch in tier_set:
                    selected.add(ch)

        result = list(selected)

        # Fallback: if SI selected nothing usable, use tier defaults
        if not result:
            return list(tier_channels) if tier_channels else ["jina_read"]

        return result

    @staticmethod
    def _si_volume_multiplier(genome: dict) -> float:
        """Derive a volume multiplier from the outreach_intensity genome trait.

        Maps outreach_intensity (0.0-1.0) → multiplier (0.3x-2.0x)
        with 0.5 → 1.0x (baseline).
        """
        if not genome:
            return 1.0
        o = genome.get("outreach_intensity", 0.5)
        return max(0.3, min(2.0, 0.3 + (1.7 * o)))

    # ── Unified Enrichment ───────────────────────────────────────

    async def enrich(self, query: str, channels: list[str] = None,
                     max_results: int = 10, tier: str = "SCRAPER_PRO",
                     save_to_db: bool = True,
                     genome: dict = None,
                     metadata: dict = None) -> dict:
        """Run enrichment across multiple channels.

        Supports SI-genome-driven channel selection: when a `genome` dict
        is provided, the channel list is automatically selected/filtered
        based on the genome traits (aggressiveness, narrow_focus, etc.)
        and `max_results` is scaled by outreach_intensity.

        Args:
            query: Search query or URL (for jina_read/rss_fetch/youtube_transcript)
            channels: List of channel names to use (default: all tier-appropriate)
            max_results: Max results per channel (scaled by SI genome if provided)
            tier: SCRAPER_STARTER | SCRAPER_PRO | SCRAPER_ENTERPRISE
            save_to_db: Whether to cache results in Supabase
            genome: Optional SI genome dict for SI-driven channel selection
            metadata: Extra metadata to store with results

        Returns:
            {ok, results: {channel_name: channel_result}, total_hits, channels_used}
        """
        # Resolve channels based on tier
        allowed = TIER_CHANNELS.get(tier, TIER_CHANNELS["SCRAPER_PRO"])
        if channels:
            channels = [c for c in channels if c in allowed and c in CHANNELS]
        else:
            channels = [c for c in allowed]

        # ── SI Genome: override channel selection + scale max_results ──
        if genome is not None:
            # SI selects which channels to use from the tier-allowed set
            channels = self._si_select_channels(genome, channels)
            # Scale max_results by outreach_intensity
            multiplier = self._si_volume_multiplier(genome)
            max_results = max(5, int(max_results * multiplier))

        if not channels:
            return {"ok": False, "error": f"No channels available for tier {tier}"}

        # Check cache first
        cache_hit = None
        if save_to_db:
            cache_hit = self._check_cache(query, channels)
        if cache_hit and len(cache_hit) == len(channels):
            return {
                "ok": True,
                "results": cache_hit,
                "total_hits": sum(len(v.get("data", [])) if isinstance(v, dict) else 0
                                  for v in cache_hit.values()),
                "channels_used": channels,
                "source": "cache",
            }

        # Run channels in parallel (skip cached ones)
        remaining = [c for c in channels if c not in (cache_hit or {})]
        results = dict(cache_hit or {})  # Start with cached results, fill the rest

        # Pre-flight: determine if query looks like a URL
        is_url = query.startswith("http://") or query.startswith("https://")
        is_youtube = is_url and ("youtube.com" in query or "youtu.be" in query)

        tasks = []
        for channel in remaining:
            if channel == "semantic_search":
                tasks.append((channel, self.semantic_search(query, max_results)))
            elif channel == "github_search":
                tasks.append((channel, self.github_search(query, max_results)))
            elif channel == "jina_read":
                if is_url:
                    tasks.append((channel, self.jina_read(query)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a URL"}
            elif channel == "rss_fetch":
                if is_url:
                    tasks.append((channel, self.rss_fetch(query, max_results)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a feed URL"}
            elif channel == "youtube_transcript":
                if is_youtube:
                    tasks.append((channel, self.youtube_transcript(query)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a YouTube URL"}
            elif channel == "v2ex_browse":
                # V2EX nodes don't have spaces; empty means hot topics
                if " " not in query:
                    tasks.append((channel, self.v2ex_browse(query, max_results)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a valid V2EX node name"}
            elif channel == "bilibili_search":
                tasks.append((channel, self.bilibili_search(query, max_results)))
            elif channel == "twitter_search":
                tasks.append((channel, self.twitter_search(query, max_results)))
            elif channel == "reddit_search":
                tasks.append((channel, self.reddit_search(query, max_results)))
            # ── New Channels (v2) ──
            elif channel == "hn_search":
                tasks.append((channel, self.hn_search(query, max_results)))
            elif channel == "arxiv_search":
                tasks.append((channel, self.arxiv_search(query, max_results)))
            elif channel == "wayback_fetch":
                if is_url:
                    tasks.append((channel, self.wayback_fetch(query, max_results)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a URL"}
            elif channel == "wikipedia_search":
                tasks.append((channel, self.wikipedia_search(query, max_results)))
            elif channel == "cloudscraper_fetch":
                if is_url:
                    tasks.append((channel, self.cloudscraper_fetch(query, max_results)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a URL"}
            elif channel == "crawl4ai":
                if is_url:
                    tasks.append((channel, self.crawl4ai(query, max_results)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a URL"}
            elif channel == "apify_scrape":
                tasks.append((channel, self.apify_scrape(query, max_results)))
            elif channel == "google_web_search":
                tasks.append((channel, self.google_web_search(query, max_results)))
            elif channel == "claude_analyze":
                tasks.append((channel, self.claude_analyze(query, max_results)))
            elif channel == "dns_geo_lookup":
                # DNS lookups work on domain names, not free-form queries
                if " " not in query and "." in query:
                    tasks.append((channel, self.dns_geo_lookup(query, max_results)))
                else:
                    results[channel] = {"ok": True, "skipped": True, "reason": "query is not a domain name"}

        # Gather results (skipped channels are already in results from pre-flight)
        for channel, coro in tasks:
            try:
                result = await coro
                results[channel] = result
            except Exception as e:
                results[channel] = {"ok": False, "error": f"{type(e).__name__}: {e}", "channel": channel}
                log.warning(f"[agent_reach] {channel} failed: {e}")

        total_hits = sum(
            len(r.get("data", [])) if isinstance(r.get("data"), (list, dict)) and r.get("ok") else
            (1 if r.get("ok") and r.get("data") else 0)
            for r in results.values() if isinstance(r, dict)
        )

        # Save to DB
        if save_to_db:
            try:
                self._save_enrichment(query, channels, results, total_hits, metadata)
            except Exception as e:
                log.warning(f"[agent_reach] cache save failed: {e}")

        return {
            "ok": True,
            "results": results,
            "total_hits": total_hits,
            "channels_used": channels,
            "source": "live",
        }

    # ── Cache Layer ──────────────────────────────────────────────

    def _check_cache(self, query: str, channels: list[str], ttl_hours: int = 24) -> dict:
        """Check if we have cached results for this query+channel combo."""
        try:
            db = self.get_db()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
            cached = {}
            for channel in channels:
                r = db.table("agent_reach_cache").select("result_data") \
                    .eq("query_hash", self._hash_query(query)) \
                    .eq("channel", channel) \
                    .gte("created_at", cutoff) \
                    .limit(1).execute()
                if r.data:
                    cached[channel] = r.data[0].get("result_data", {})
            return cached if cached else None
        except Exception:
            return None

    def _save_enrichment(self, query: str, channels: list[str],
                         results: dict, total_hits: int,
                         metadata: dict = None):
        """Cache enrichment results in Supabase."""
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc).isoformat()
            query_hash = self._hash_query(query)
            rows = []
            for channel in channels:
                result = results.get(channel, {})
                rows.append({
                    "query_hash": query_hash,
                    "query": query[:500],
                    "channel": channel,
                    "result_data": result,
                    "total_hits": total_hits,
                    "metadata": metadata or {},
                    "created_at": now,
                })
            if rows:
                db.table("agent_reach_cache").insert(rows).execute()
        except Exception as e:
            log.debug(f"[agent_reach] cache write skipped: {e}")

    @staticmethod
    def _hash_query(query: str) -> str:
        """Simple hash for cache key."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]

    # ── Health Check ─────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Check Agent-Reach channel health using `agent-reach doctor`."""
        result = await self._run_cmd("agent-reach", "doctor", "--json", "--force", timeout=15)
        if result.get("ok"):
            return {
                "ok": True,
                "raw": result.get("data", {}),
                "channels": {
                    name: {
                        "description": cfg["description"],
                        "installed": cfg["installed"],
                        "available_in": [t for t, chs in TIER_CHANNELS.items() if name in chs],
                    }
                    for name, cfg in CHANNELS.items()
                },
                "installed_count": sum(1 for c in CHANNELS.values() if c["installed"]),
                "total_channels": len(CHANNELS),
            }
        # Fallback: report what we know
        return {
            "ok": True,
            "channels": {
                name: {
                    "description": cfg["description"],
                    "installed": cfg["installed"],
                    "available_in": [t for t, chs in TIER_CHANNELS.items() if name in chs],
                }
                for name, cfg in CHANNELS.items()
            },
            "installed_count": sum(1 for c in CHANNELS.values() if c["installed"]),
            "total_channels": len(CHANNELS),
            "note": "agent-reach doctor not available, reporting cached channel status",
        }

    def get_channel_info(self) -> dict:
        """Return all channel metadata."""
        return {
            name: {
                "description": cfg["description"],
                "cost": cfg["cost"],
                "rate_limit": cfg["rate_limit"],
                "installed": cfg["installed"],
                "install_note": cfg.get("install_note", ""),
                "auth_note": cfg.get("auth_note", ""),
                "available_in": [tier for tier, channels in TIER_CHANNELS.items()
                                 if name in channels],
            }
            for name, cfg in CHANNELS.items()
        }


# ── FastAPI Routes ──────────────────────────────────────────────────

class AgentReachRoutes:
    """Wire Agent-Reach enrichment endpoints into FastAPI."""

    def __init__(self, enricher: AgentReachEnricher, *,
                 require_auth: Optional[Callable] = None):
        self.enricher = enricher
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v1/agent-reach/enrich")
        async def reach_enrich(request: Request,
                               auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Run Agent-Reach enrichment across multiple channels.

            Supports SI-genome-driven channel selection when `genome` is provided.

            Body:
                query (str): Search query (required)
                channels (list[str], optional): Channel names to use
                max_results (int, optional): Max results per channel (default: 10)
                tier (str, optional): SCRAPER_STARTER | SCRAPER_PRO | SCRAPER_ENTERPRISE
                genome (dict, optional): SI genome traits {aggressiveness, narrow_focus,
                    outreach_intensity, risk_tolerance, price_premium} — each 0.0-1.0
                metadata (dict, optional): Extra metadata for result storage
                save_to_db (bool, optional): Whether to cache results (default: true)
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query is required")

            channels = body.get("channels")
            max_results = int(body.get("max_results", 10))
            tier = (body.get("tier") or "SCRAPER_PRO").strip()
            genome = body.get("genome")
            metadata = body.get("metadata")
            save_to_db = body.get("save_to_db", True)

            result = await self.enricher.enrich(
                query=query,
                channels=channels,
                max_results=max_results,
                tier=tier,
                save_to_db=save_to_db,
                genome=genome,
                metadata=metadata,
            )
            status = 200 if result.get("ok") else 500
            return JSONResponse(result, status_code=status)

        @app.get("/api/v1/agent-reach/channels")
        async def reach_channels(
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """List all Agent-Reach channels with tier availability."""
            return JSONResponse({
                "channels": self.enricher.get_channel_info(),
                "total_channels": len(CHANNELS),
                "installed_count": sum(1 for c in CHANNELS.values() if c["installed"]),
            })

        @app.get("/api/v1/agent-reach/genomes")
        async def reach_genomes(
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """List all SI genome archetypes with descriptions and traits.

            Returns named archetypes that can be used as the `genome` field
            in POST /api/v1/agent-reach/enrich requests.
            """
            return JSONResponse({
                "archetypes": {
                    name: {
                        "description": entry["description"],
                        "genome": entry["genome"],
                        "tier_preview": {
                            tier: {
                                "channel_count": len(AgentReachEnricher._si_select_channels(entry["genome"], channels)),
                            }
                            for tier, channels in TIER_CHANNELS.items()
                        },
                    }
                    for name, entry in GENOME_ARCHETYPES.items()
                },
                "count": len(GENOME_ARCHETYPES),
            })

        @app.get("/api/v1/agent-reach/health")
        async def reach_health(
            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Agent-Reach health check — tests all active channels."""
            return JSONResponse(await self.enricher.health_check())

        @app.post("/api/v1/agent-reach/search")
        async def reach_search(request: Request,
                               auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Semantic search via Exa.
            Body: {query, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            result = await self.enricher.semantic_search(
                query=query,
                max_results=int(body.get("max_results", 10)),
            )
            return JSONResponse(result)

        @app.post("/api/v1/agent-reach/github-search")
        async def reach_github(request: Request,
                               auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """GitHub search via gh api.
            Body: {query, search_type?, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            result = await self.enricher.github_search(
                query=query,
                search_type=body.get("search_type", "repositories"),
                max_results=int(body.get("max_results", 10)),
            )
            return JSONResponse(result)

        @app.post("/api/v1/agent-reach/jina-read")
        async def reach_jina(request: Request,
                             auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Read a URL via Jina Reader.
            Body: {url}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            url = (body.get("url") or "").strip()
            if not url:
                raise HTTPException(400, "url required")
            return JSONResponse(await self.enricher.jina_read(url))

        @app.post("/api/v1/agent-reach/transcript")
        async def reach_transcript(request: Request,
                                   auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Extract YouTube transcript.
            Body: {video_url}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            video_url = (body.get("video_url") or "").strip()
            if not video_url:
                raise HTTPException(400, "video_url required")
            return JSONResponse(await self.enricher.youtube_transcript(video_url))

        @app.post("/api/v1/agent-reach/rss")
        async def reach_rss(request: Request,
                            auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Fetch RSS feed.
            Body: {feed_url, max_items?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            feed_url = (body.get("feed_url") or "").strip()
            if not feed_url:
                raise HTTPException(400, "feed_url required")
            result = await self.enricher.rss_fetch(
                feed_url=feed_url,
                max_items=int(body.get("max_items", 10)),
            )
            return JSONResponse(result)

        # ── New Channel Routes (v2) ──────────────────────────────

        @app.post("/api/v1/agent-reach/hn-search")
        async def reach_hn(request: Request,
                           auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Search Hacker News.
            Body: {query, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            return JSONResponse(await self.enricher.hn_search(
                query=query,
                max_results=int(body.get("max_results", 10)),
            ))

        @app.post("/api/v1/agent-reach/arxiv-search")
        async def reach_arxiv(request: Request,
                              auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Search academic papers on arXiv.
            Body: {query, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            return JSONResponse(await self.enricher.arxiv_search(
                query=query,
                max_results=int(body.get("max_results", 10)),
            ))

        @app.post("/api/v1/agent-reach/wayback")
        async def reach_wayback(request: Request,
                                auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Fetch archived page from Wayback Machine.
            Body: {url, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            url = (body.get("url") or "").strip()
            if not url:
                raise HTTPException(400, "url required")
            return JSONResponse(await self.enricher.wayback_fetch(
                url=url,
                max_results=int(body.get("max_results", 5)),
            ))

        @app.post("/api/v1/agent-reach/wikipedia")
        async def reach_wikipedia(request: Request,
                                  auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Search Wikipedia articles.
            Body: {query, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            return JSONResponse(await self.enricher.wikipedia_search(
                query=query,
                max_results=int(body.get("max_results", 5)),
            ))

        @app.post("/api/v1/agent-reach/cloudscraper")
        async def reach_cloudscraper(request: Request,
                                     auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Fetch a Cloudflare-protected page.
            Body: {url}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            url = (body.get("url") or "").strip()
            if not url:
                raise HTTPException(400, "url required")
            return JSONResponse(await self.enricher.cloudscraper_fetch(url=url))

        @app.post("/api/v1/agent-reach/crawl4ai")
        async def reach_crawl4ai(request: Request,
                                 auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Deep crawl a URL via Crawl4AI.
            Body: {url, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            url = (body.get("url") or "").strip()
            if not url:
                raise HTTPException(400, "url required")
            return JSONResponse(await self.enricher.crawl4ai(
                url=url,
                max_results=int(body.get("max_results", 10)),
            ))

        @app.post("/api/v1/agent-reach/apify")
        async def reach_apify(request: Request,
                              auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Scrape via Apify platform.
            Body: {query, max_results?, actor_id?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            return JSONResponse(await self.enricher.apify_scrape(
                query=query,
                max_results=int(body.get("max_results", 10)),
                actor_id=body.get("actor_id", "apify/web-scraper"),
            ))

        @app.post("/api/v1/agent-reach/google-search")
        async def reach_google(request: Request,
                               auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Google Programmable Search.
            Body: {query, max_results?}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            query = (body.get("query") or "").strip()
            if not query:
                raise HTTPException(400, "query required")
            return JSONResponse(await self.enricher.google_web_search(
                query=query,
                max_results=int(body.get("max_results", 10)),
            ))

        @app.post("/api/v1/agent-reach/claude-analyze")
        async def reach_claude(request: Request,
                               auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Analyze content via Claude AI.
            Body: {prompt}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                raise HTTPException(400, "prompt required")
            return JSONResponse(await self.enricher.claude_analyze(prompt=prompt))

        @app.post("/api/v1/agent-reach/dns-geo")
        async def reach_dns_geo(request: Request,
                                auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """DNS resolution + IP geolocation.
            Body: {domain}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            domain = (body.get("domain") or "").strip()
            if not domain:
                raise HTTPException(400, "domain required")
            return JSONResponse(await self.enricher.dns_geo_lookup(domain=domain))

        log.info("[agent_reach] Routes registered · /api/v1/agent-reach/*")
