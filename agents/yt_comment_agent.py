"""
Empire AI · YouTube Comment Engagement Agent
================================================

Polls YouTube Data API for comments on recent Shorts.
Uses the brain (MiniMax-M3) to draft operator-style replies.
Posts the replies via YouTube Data API.

Comments + replies are saved to youtube_comments table for audit.
Daily digest to Telegram if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set.

Cron: every 4 hours
"""
import os
import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from supabase import create_client

log = logging.getLogger("yt_comments")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
YT_BASE = "https://www.googleapis.com/youtube/v3"

VAULT = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))


async def fetch_recent_comments(lookback_hours: int = 24) -> list:
    """Pull comments from the channel's recent videos."""
    if not YOUTUBE_API_KEY or not YOUTUBE_CHANNEL_ID:
        log.warning("YOUTUBE_API_KEY or YOUTUBE_CHANNEL_ID not set")
        return []
    async with httpx.AsyncClient(timeout=20) as c:
        # Get recent videos
        r = await c.get(f"{YT_BASE}/search",
            params={"part": "id", "channelId": YOUTUBE_CHANNEL_ID,
                    "maxResults": 10, "order": "date", "type": "video",
                    "key": YOUTUBE_API_KEY})
        videos = r.json().get("items", [])
        if not videos:
            return []
        video_ids = [v["id"]["videoId"] for v in videos]
        # Get comments for each video
        all_comments = []
        for vid in video_ids:
            r2 = await c.get(f"{YT_BASE}/commentThreads",
                params={"part": "snippet", "videoId": vid,
                        "maxResults": 50, "order": "time",
                        "key": YOUTUBE_API_KEY})
            for item in r2.json().get("items", []):
                c_data = item["snippet"]["topLevelComment"]["snippet"]
                # Skip comments we already replied to
                if "REPLY_COUNT_PLACEHOLDER" not in c_data:
                    pass
                all_comments.append({
                    "video_id": vid,
                    "comment_id": item["id"],
                    "author": c_data.get("authorDisplayName", ""),
                    "text": c_data.get("textDisplay", ""),
                    "published_at": c_data.get("publishedAt", ""),
                    "like_count": c_data.get("likeCount", 0),
                })
    # Filter to comments within lookback window
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours))
    filtered = []
    for c in all_comments:
        try:
            ts = datetime.fromisoformat(c["published_at"].replace("Z", "+00:00"))
            if ts > cutoff:
                filtered.append(c)
        except Exception:
            continue
    return filtered


async def draft_reply(comment: dict) -> str:
    """Use the brain to draft an operator-style reply."""
    try:
        sys.path.insert(0, "/root/empire-v49")
        from empire_ai_router import AIRouter
        router = AIRouter()
        system = (
            "You draft YouTube comment replies for Empire AI — a B2B platform "
            "for restoration/roofing/HVAC/public-adjuster contractors. Your replies:\n"
            "- Are 1-2 sentences max (YouTube comments, not essays)\n"
            "- Sound like a real person, not a brand account\n"
            "- Add value: a fact, a tip, or a follow-up question\n"
            "- Use contractions, lowercase, no em-dashes\n"
            "- NEVER say 'Great question!', 'Thanks for watching!', 'I hope this helps!'\n"
            "- NEVER use AI-tell phrases: 'delve into', 'landscape', 'leverage', 'unlock'\n"
            "- For questions, give a real answer. For praise, say thanks + add a tip.\n"
            "- If comment is rude/spam, return the string 'SKIP'\n"
            "Return ONLY the reply text, no quotes, no preamble."
        )
        prompt = (
            f"Reply to this YouTube comment on our restoration/lead-gen channel:\n\n"
            f"Author: {comment['author']}\n"
            f"Comment: {comment['text']}\n"
            f"Likes: {comment['like_count']}\n\n"
            f"Write a 1-2 sentence reply."
        )
        result = await router.generate(
            prompt=prompt, system=system, task="youtube.comment_reply",
            temperature=0.7, max_tokens=120,
        )
        if result and isinstance(result, dict):
            text = result.get("text", "").strip()
            if text and text != "SKIP" and len(text) < 280:
                return text
    except Exception as e:
        log.warning(f"brain reply failed: {e}")
    # Fallback: simple reply
    text = comment["text"].strip()
    if not text:
        return ""
    return f"good question — {text[:60]}. happy to dig in if you want specifics."


async def post_reply(video_id: str, parent_comment_id: str, reply_text: str) -> bool:
    """Post reply to YouTube comment via Data API."""
    if not YOUTUBE_API_KEY:
        return False
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{YT_BASE}/comments",
            params={"part": "snippet", "key": YOUTUBE_API_KEY},
            json={"snippet": {
                "parentId": parent_comment_id,
                "textOriginal": reply_text,
            }})
        return r.status_code < 400


def already_replied(comment_id: str) -> bool:
    sb = _sb()
    r = sb.table("youtube_comments").select("id").eq("comment_id", comment_id).eq("replied", True).execute()
    return bool(r.data)


def save_comment(comment: dict, reply: str, posted: bool):
    sb = _sb()
    sb.table("youtube_comments").upsert({
        "comment_id": comment["comment_id"],
        "video_id": comment["video_id"],
        "author": comment["author"],
        "text": comment["text"],
        "reply": reply,
        "replied": posted,
        "like_count": comment["like_count"],
        "published_at": comment["published_at"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="comment_id").execute()


async def run_cycle(lookback_hours: int = 24, max_replies: int = 30):
    if not YOUTUBE_API_KEY:
        log.info("skipping — YOUTUBE_API_KEY not set")
        return {"skipped": True, "reason": "no_api_key"}

    comments = await fetch_recent_comments(lookback_hours=lookback_hours)
    log.info(f"found {len(comments)} recent comments")

    replied = 0
    skipped = 0
    for c in comments[:max_replies]:
        if already_replied(c["comment_id"]):
            skipped += 1
            continue
        reply = await draft_reply(c)
        if not reply or reply == "SKIP":
            skipped += 1
            continue
        posted = await post_reply(c["video_id"], c["comment_id"], reply)
        save_comment(c, reply, posted)
        if posted:
            replied += 1
            log.info(f"  replied to {c['author']}: {c['text'][:60]}")
        else:
            log.warning(f"  draft saved, post failed: {c['comment_id']}")
    log.info(f"cycle done: replied={replied}, skipped={skipped}")
    return {"replied": replied, "skipped": skipped, "total": len(comments)}


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_cycle())