"""
Empire AI · YouTube Stats API
==================================

Returns YouTube channel + recent Shorts stats via the Data API v3.
Falls back to stub data when API key not configured.

Endpoint: GET /api/v1/youtube/stats
Endpoint: GET /api/v1/youtube/status
"""
import os
import sys
import json
import time
import logging
from pathlib import Path

REPO = Path("/root/empire-v49")

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("youtube_stats")

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
YT_BASE = "https://www.googleapis.com/youtube/v3"


def _stub_response() -> dict:
    """Return a placeholder when YouTube API key not configured."""
    return {
        "configured": False,
        "channel_id": YOUTUBE_CHANNEL_ID or None,
        "missing": "YOUTUBE_API_KEY" if not YOUTUBE_API_KEY else None,
        "subscribers": None,
        "views_total": None,
        "videos_total": None,
        "top_shorts": [],
        "note": "Drop YOUTUBE_API_KEY in /root/.env to enable live data"
    }


async def _fetch_channel_stats() -> dict | None:
    if not YOUTUBE_API_KEY or not YOUTUBE_CHANNEL_ID:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{YT_BASE}/channels",
                params={"part": "statistics,snippet", "id": YOUTUBE_CHANNEL_ID, "key": YOUTUBE_API_KEY})
            data = r.json()
            items = data.get("items", [])
            if not items:
                return None
            ch = items[0]
            stats = ch.get("statistics", {})
            snippet = ch.get("snippet", {})
            r2 = await c.get(f"{YT_BASE}/search",
                params={"part": "snippet", "channelId": YOUTUBE_CHANNEL_ID,
                        "maxResults": 10, "order": "date", "type": "video", "key": YOUTUBE_API_KEY})
            videos = r2.json().get("items", [])
            return {
                "configured": True,
                "channel_id": YOUTUBE_CHANNEL_ID,
                "channel_title": snippet.get("title"),
                "subscribers": int(stats.get("subscriberCount", 0)),
                "views_total": int(stats.get("viewCount", 0)),
                "videos_total": int(stats.get("videoCount", 0)),
                "top_shorts": [{"title": v["snippet"]["title"],
                                "video_id": v["id"]["videoId"],
                                "published": v["snippet"]["publishedAt"]}
                               for v in videos[:5]],
                "fetched_at": time.time(),
            }
    except Exception as e:
        log.warning(f"[youtube] API call failed: {e}")
        return None


async def handle_youtube_stats(request: Request) -> JSONResponse:
    """GET /api/v1/youtube/stats — live channel stats from YouTube Data API."""
    live = await _fetch_channel_stats()
    if live:
        return JSONResponse(live)
    return JSONResponse(_stub_response())


def _local_agent_stats() -> dict:
    """Pull from bots/youtube_shorts_agent state if available."""
    try:
        sys.path.insert(0, str(REPO))
        from bots.youtube_shorts_agent import YouTubeShortsAgent
        agent = YouTubeShortsAgent()
        snap = agent.snapshot()
        return {
            "agent_videos_generated": snap.get("videos_generated", 0),
            "agent_videos_rendered": snap.get("videos_rendered", 0),
            "agent_videos_published": snap.get("videos_published", 0),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


async def handle_youtube_status(request: Request) -> JSONResponse:
    """GET /api/v1/youtube/status — config check + agent state."""
    return JSONResponse({
        "configured": bool(YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID),
        "api_key_present": bool(YOUTUBE_API_KEY),
        "channel_id_set": bool(YOUTUBE_CHANNEL_ID),
        "agent": _local_agent_stats(),
    })


def register_youtube_routes(app):
    @app.get("/api/v1/youtube/stats")
    async def youtube_stats(request: Request):
        return await handle_youtube_stats(request)

    @app.get("/api/v1/youtube/status")
    async def youtube_status(request: Request):
        return await handle_youtube_status(request)
    log.info("[youtube] routes registered: /api/v1/youtube/{stats,status}")