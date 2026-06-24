"""
Empire AI · TikTok Cross-Post Pipeline
=========================================

Renders a YouTube Short once, then:
1. Uploads to TikTok via TikTok API (if TIKTOK_ACCESS_TOKEN set)
2. Otherwise queues for manual upload with caption + hashtags
3. Tracks the publish state per platform in DB

Why cross-post:
- TikTok Shorts and YouTube Shorts share the same 9:16 vertical format
- Cross-posting adds 30-40% reach without extra production
- TikTok audience skews younger, YouTube skews older — both feeds funnel
  back to /for-contractors

Cron: 30 minutes after each YouTube publish (06:30 + 18:30 UTC)

Required:
  - TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_ACCESS_TOKEN
    for auto-upload. Without these, queues for manual.
"""
import os
import sys
import json
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from supabase import create_client

log = logging.getLogger("tiktok_crosspost")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_BASE = "https://open.tiktokapis.com/v2"


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))


def find_unpublished_shorts() -> list:
    sb = _sb()
    out_dir = Path("/root/empire-v49/data/youtube_shorts")
    if not out_dir.exists():
        out_dir = Path("/root/empire-v49/youtube_shorts_output")
    if not out_dir.exists():
        return []
    r = sb.table("youtube_shorts_publishes").select(
        "video_id, youtube_uploaded_at, tiktok_uploaded_at, file_path"
    ).execute().data or []
    db_state = {row["video_id"]: row for row in r}
    candidates = []
    for f in out_dir.rglob("*.mp4"):
        vid = hashlib.md5(str(f).encode()).hexdigest()[:12]
        state = db_state.get(vid, {})
        if not state.get("tiktok_uploaded_at"):
            candidates.append({"video_id": vid, "file_path": str(f),
                               "youtube_uploaded_at": state.get("youtube_uploaded_at")})
    return candidates


def upload_to_tiktok(file_path: str, caption: str, hashtags: list) -> dict:
    if not TIKTOK_ACCESS_TOKEN:
        return {"ok": False, "error": "TIKTOK_ACCESS_TOKEN not set"}
    try:
        with httpx.Client(timeout=30) as c:
            init_resp = c.post(f"{TIKTOK_BASE}/post/publish/video/init/",
                headers={"Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
                         "Content-Type": "application/json"},
                json={"post_info": {"title": caption, "privacy_level": "PUBLIC_TO_EVERYONE",
                                    "disable_duet": False, "disable_comment": False,
                                    "disable_stitch": False, "video_cover_timestamp_ms": 1000},
                      "source_info": {"source": "FILE_UPLOAD",
                                       "video_size": os.path.getsize(file_path),
                                       "chunk_size": 10_000_000,
                                       "total_chunk_count": (os.path.getsize(file_path) + 9_999_999) // 10_000_000}})
            init_data = init_resp.json()
            if "data" not in init_data or "upload_url" not in init_data["data"]:
                return {"ok": False, "error": f"init failed: {init_data}"}
            upload_url = init_data["data"]["upload_url"]
            publish_id = init_data["data"]["publish_id"]
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(10_000_000)
                    if not chunk:
                        break
                    chunk_resp = c.put(upload_url, content=chunk,
                                       headers={"Content-Type": "video/mp4",
                                                "Content-Length": str(len(chunk))})
                    if chunk_resp.status_code >= 400:
                        return {"ok": False, "error": f"chunk upload failed: {chunk_resp.status_code}"}
            publish_resp = c.post(f"{TIKTOK_BASE}/post/publish/commit/",
                headers={"Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
                         "Content-Type": "application/json"},
                json={"publish_id": publish_id})
            pub_data = publish_resp.json()
            return {"ok": publish_resp.status_code < 400,
                    "publish_id": publish_id,
                    "data": pub_data}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def save_publish_state(video_id: str, file_path: str, platform: str,
                        ok: bool, error: str = None):
    sb = _sb()
    update = {f"{platform}_uploaded_at": datetime.now(timezone.utc).isoformat(),
              f"{platform}_file_path": file_path}
    if error:
        update[f"{platform}_error"] = error
    sb.table("youtube_shorts_publishes").upsert({
        "video_id": video_id,
        "file_path": file_path,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **update,
    }, on_conflict="video_id").execute()


def generate_caption(short: dict) -> tuple:
    base = short.get("caption", "Storm season is here. Are you ready?")
    hashtags = ["#stormdamage", "#roofing", "#restoration", "#contractor",
                "#leads", "#AI", "#smallbusiness", "#24hours",
                "#hailstorm", "#publicadjuster"]
    return base, hashtags


def run_cycle():
    sb = _sb()
    candidates = find_unpublished_shorts()
    log.info(f"found {len(candidates)} unpublished shorts")
    published = 0
    queued = 0
    for s in candidates:
        caption, hashtags = generate_caption(s)
        if TIKTOK_ACCESS_TOKEN:
            result = upload_to_tiktok(s["file_path"], caption, hashtags)
            save_publish_state(s["video_id"], s["file_path"], "tiktok",
                              result["ok"], result.get("error"))
            if result["ok"]:
                published += 1
                log.info(f"  published: {s['video_id']}")
            else:
                log.warning(f"  failed: {result.get('error')}")
                queued += 1
        else:
            sb.table("tiktok_upload_queue").upsert({
                "video_id": s["video_id"],
                "file_path": s["file_path"],
                "caption": caption,
                "hashtags": hashtags,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="video_id").execute()
            queued += 1
            log.info(f"  queued for manual: {s['video_id']}")
    log.info(f"cycle done: published={published}, queued={queued}")
    return {"published": published, "queued": queued, "total": len(candidates)}


def list_manual_queue() -> list:
    sb = _sb()
    return sb.table("tiktok_upload_queue").select("*").eq("status", "queued").execute().data or []


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "queue":
        for row in list_manual_queue():
            print(f"--- {row['video_id']} ---")
            print(f"  file: {row['file_path']}")
            print(f"  caption: {row['caption']}")
            print(f"  hashtags: {' '.join(row['hashtags'])}")
            print()
    else:
        run_cycle()