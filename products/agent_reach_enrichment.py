"""
EMPIRE V49 · AGENT-REACH ENRICHMENT LAYER
==========================================
Wraps the Agent-Reach (v1.5.0) installed CLI tools into async Python
enrichment functions.  Provides 9 intelligence channels for the Elite
Scraper product:

  - semantic_search  — Exa web search via mcporter (free, no API key)
  - github_search    — GitHub code/repo/issue search via gh api
  - jina_read        — Read any URL as clean Markdown via Jina Reader
  - rss_fetch        — Fetch and parse RSS/Atom feeds via curl
  - youtube_transcript — Extract YouTube subtitles via yt-dlp
  - v2ex_browse      — Browse V2EX topics via public API
  - bilibili_search  — Search Bilibili videos (needs `bili` CLI)
  - twitter_search   — Search Twitter/X (needs `twitter` CLI)
  - reddit_search    — Search Reddit (needs `opencli` or `rdt` CLI)

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
        "description": "Search Bilibili videos (needs `bili` CLI installed)",
        "cost": "free",
        "rate_limit": "20/min",
        "installed": False,
        "install_note": "Install: pip install bilibili-cli  or  brew install bili",
    },
    "twitter_search": {
        "description": "Search Twitter/X (needs `twitter` CLI installed)",
        "cost": "free",
        "rate_limit": "15/min",
        "installed": False,
        "install_note": "Install: pip install twitter-cli",
    },
    "reddit_search": {
        "description": "Search Reddit (needs `opencli` or `rdt` CLI installed)",
        "cost": "free",
        "rate_limit": "30/min",
        "installed": False,
        "install_note": "Install: pip install opencli  or  pip install rdt-cli",
    },
}

# ── Tier Channel Access ─────────────────────────────────────────────
TIER_CHANNELS = {
    "SCRAPER_STARTER":     ["jina_read"],
    "SCRAPER_PRO":         ["jina_read", "semantic_search", "rss_fetch", "github_search"],
    "SCRAPER_ENTERPRISE":  [c for c in CHANNELS],
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
        """Search Bilibili videos (needs `bili` CLI)."""
        if not self._check_rate("bilibili_search"):
            return {"ok": False, "error": "rate limited", "channel": "bilibili_search"}
        self._record_call("bilibili_search")

        return await self._run_cmd(
            "bili", "search", query,
            "--type", "video", "-n", str(max_results),
            timeout=20,
            channel="bilibili_search",
        )

    async def twitter_search(self, query: str, max_results: int = 10) -> dict:
        """Search Twitter/X (needs `twitter` CLI)."""
        if not self._check_rate("twitter_search"):
            return {"ok": False, "error": "rate limited", "channel": "twitter_search"}
        self._record_call("twitter_search")

        return await self._run_cmd(
            "twitter", "search", query, "-n", str(max_results),
            timeout=25,
            channel="twitter_search",
        )

    async def reddit_search(self, query: str, max_results: int = 10) -> dict:
        """Search Reddit (needs `opencli` or `rdt` CLI)."""
        if not self._check_rate("reddit_search"):
            return {"ok": False, "error": "rate limited", "channel": "reddit_search"}
        self._record_call("reddit_search")

        # Try opencli first, fall back to rdt
        result = await self._run_cmd(
            "opencli", "reddit", "search", query, "-f", "yaml",
            timeout=25,
            channel="reddit_search",
        )
        if not result.get("ok") and "not found" in str(result.get("error", "")).lower():
            result = await self._run_cmd(
                "rdt", "search", query, "--limit", str(max_results),
                timeout=25,
                channel="reddit_search",
            )
        return result

    # ── Unified Enrichment ───────────────────────────────────────

    async def enrich(self, query: str, channels: list[str] = None,
                     max_results: int = 10, tier: str = "SCRAPER_PRO",
                     save_to_db: bool = True,
                     metadata: dict = None) -> dict:
        """Run enrichment across multiple channels.

        Args:
            query: Search query or URL (for jina_read/rss_fetch/youtube_transcript)
            channels: List of channel names to use (default: all tier-appropriate)
            max_results: Max results per channel
            tier: SCRAPER_STARTER | SCRAPER_PRO | SCRAPER_ENTERPRISE
            save_to_db: Whether to cache results in Supabase
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
        tasks = []
        for channel in remaining:
            if channel == "semantic_search":
                tasks.append((channel, self.semantic_search(query, max_results)))
            elif channel == "github_search":
                tasks.append((channel, self.github_search(query, max_results)))
            elif channel == "jina_read":
                tasks.append((channel, self.jina_read(query)))  # query is URL
            elif channel == "rss_fetch":
                tasks.append((channel, self.rss_fetch(query, max_results)))  # query is feed URL
            elif channel == "youtube_transcript":
                tasks.append((channel, self.youtube_transcript(query)))  # query is video URL
            elif channel == "v2ex_browse":
                tasks.append((channel, self.v2ex_browse(query, max_results)))  # query is node
            elif channel == "bilibili_search":
                tasks.append((channel, self.bilibili_search(query, max_results)))
            elif channel == "twitter_search":
                tasks.append((channel, self.twitter_search(query, max_results)))
            elif channel == "reddit_search":
                tasks.append((channel, self.reddit_search(query, max_results)))

        # Gather results
        results = dict(cache_hit or {})
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
            Body: {query, channels?, max_results?, tier?, metadata?}
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
            metadata = body.get("metadata")
            save_to_db = body.get("save_to_db", True)

            result = await self.enricher.enrich(
                query=query,
                channels=channels,
                max_results=max_results,
                tier=tier,
                save_to_db=save_to_db,
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

        log.info("[agent_reach] Routes registered · /api/v1/agent-reach/*")
