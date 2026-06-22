"""
EMPIRE V49 · YOUTUBE SCRAPER (ELITE CHANNEL 2) - v2
=====================================================
Pulls YouTube video metadata (title, description, channel) for niche
search queries. Stores in strategic_content for downstream analysis.

DESIGN NOTE: We tried extracting real transcripts via the timedtext
API but YouTube requires auth cookies/tokens that aren't accessible
from a headless request. The video metadata (title + description +
channel name + view count) is in the page HTML and is reliably
extractable. Use that as the "content" signal.

VERIFIED:
  Page HTML contains title, description, channel, view count.
  /tmp/yt_debug.py confirms caption URL is in the page but timedtext
  body requires auth.
"""
import os
import sys
import re
import json
import time
import logging
import httpx
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

try:
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
except Exception as e:
    sb = None
    print(f"[youtube_scraper] Supabase init failed: {e}")

log = logging.getLogger("empire.youtube_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [youtube] %(levelname)s %(message)s")

NICHE_QUERIES = {
    "roofing": "roofing contractor business growth",
    "hvac": "hvac business lead generation",
    "solar": "solar lead generation home improvement",
    "restoration": "water damage restoration marketing",
    "public_adjuster": "public insurance adjuster business",
    "commercial": "commercial contractor lead generation",
}

VIDEO_ID_RE = re.compile(r"/watch\?v=([A-Za-z0-9_-]{11})")
# Short description meta tag
SHORT_DESC_RE = re.compile(r'<meta name="description" content="([^"]+)"')
# Channel name + view count patterns (in ytInitialData JSON)
OWNER_NAME_RE = re.compile(r'"ownerChannelName":"([^"]+)"')
VIEW_COUNT_RE = re.compile(r'"viewCount":"(\d+)"')
SHORT_DESC_JSON_RE = re.compile(r'"shortDescription":"((?:[^"\\]|\\.)*)"')


def _record_agent_activity(agent_name: str, status: str, rows: int, summary: str):
    if not sb:
        return
    try:
        # Generate a run_id (UUID) since column is NOT NULL
        import uuid as _uuid
        sb.table("agent_activity").insert({
            "run_id": str(_uuid.uuid4()),
            "agent_name": agent_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_processed": rows,
            "summary": summary[:500],
        }).execute()
    except Exception as e:
        log.warning(f"agent_activity insert failed: {e}")


def _extract_video_ids_from_search(html: str, max_n: int = 5) -> List[str]:
    seen = set()
    ids = []
    for m in VIDEO_ID_RE.finditer(html):
        vid = m.group(1)
        if vid not in seen:
            seen.add(vid)
            ids.append(vid)
        if len(ids) >= max_n:
            break
    return ids


def _extract_meta(watch_html: str) -> Dict:
    """Extract title, description, channel from a watch page."""
    out = {"title": "", "description": "", "channel": "", "views": 0}
    title_m = re.search(r'<title>([^<]+)</title>', watch_html)
    if title_m:
        out["title"] = title_m.group(1).replace(" - YouTube", "").strip()
    desc_m = SHORT_DESC_JSON_RE.search(watch_html)
    if desc_m:
        # unescape
        out["description"] = desc_m.group(1).replace("\\n", "\n")[:2000]
    if not out["description"]:
        desc_m2 = SHORT_DESC_RE.search(watch_html)
        if desc_m2:
            out["description"] = desc_m2.group(1)
    ch_m = OWNER_NAME_RE.search(watch_html)
    if ch_m:
        out["channel"] = ch_m.group(1)
    v_m = VIEW_COUNT_RE.search(watch_html)
    if v_m:
        try:
            out["views"] = int(v_m.group(1))
        except ValueError:
            pass
    return out


def _scrape_niche_sync(query: str, max_videos: int = 3) -> List[Dict]:
    out = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
        try:
            r = client.get("https://www.youtube.com/results", params={"search_query": query})
            if r.status_code != 200:
                log.warning(f"youtube search {r.status_code} for {query!r}")
                return out
            vids = _extract_video_ids_from_search(r.text, max_n=max_videos)
            log.info(f"[youtube] query={query!r} → {len(vids)} video IDs")

            for vid in vids:
                try:
                    wr = client.get(f"https://www.youtube.com/watch?v={vid}")
                    if wr.status_code != 200:
                        continue
                    meta = _extract_meta(wr.text)
                    if not meta["title"]:
                        continue
                    out.append({
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "title": meta["title"][:200],
                        "channel": meta["channel"],
                        "description": meta["description"],
                        "views": meta["views"],
                        "query": query,
                    })
                except Exception as e:
                    log.debug(f"video {vid} failed: {e}")
                time.sleep(0.4)
        except Exception as e:
            log.warning(f"search failed: {e}")
    return out


def _store_results(rows: List[Dict], niche: str) -> int:
    if not sb or not rows:
        return 0
    written = 0
    for r in rows:
        try:
            sb.table("strategic_content").insert({
                "source": "youtube",
                "niche": niche,
                "url": r["url"],
                "title": r["title"],
                "channel": r.get("channel", ""),
                "description": r.get("description", ""),
                "views": r.get("views", 0),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            written += 1
        except Exception as e:
            log.debug(f"strategic_content insert failed: {e}")
            if "does not exist" in str(e).lower() or "42P01" in str(e):
                log.warning("strategic_content table missing — skipping DB write")
                return written
    return written


def run_once() -> Dict:
    started = datetime.now(timezone.utc)
    all_results = []
    by_niche = {}

    for niche, query in NICHE_QUERIES.items():
        log.info(f"[youtube] niche={niche} query={query!r}")
        try:
            results = _scrape_niche_sync(query, max_videos=2)
            by_niche[niche] = len(results)
            for r in results:
                r["niche"] = niche
                all_results.append(r)
        except Exception as e:
            log.warning(f"niche {niche} failed: {e}")
        time.sleep(1)

    written = _store_results(all_results, niche="multi")

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    summary = json.dumps({
        "videos_found": len(all_results),
        "written_to_db": written,
        "by_niche": by_niche,
        "duration_s": round(duration, 1),
    })
    status = "ok" if all_results else "error"
    _record_agent_activity("youtube_scraper", status, len(all_results), summary)
    log.info(f"[youtube] cycle complete: {summary}")
    return {"videos": len(all_results), "written": written, "by_niche": by_niche}


def run_loop(interval_seconds: int = 86400):
    import asyncio
    async def _run():
        while True:
            try:
                run_once()
            except Exception as e:
                log.error(f"youtube loop error: {e}")
            await asyncio.sleep(max(60, interval_seconds))
    asyncio.run(_run())


if __name__ == "__main__":
    print(json.dumps(run_once(), indent=2))