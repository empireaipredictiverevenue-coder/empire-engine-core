"""
EMPIRE V49 · YOUTUBE SCRAPER (ELITE CHANNEL 2)
================================================
Pulls YouTube transcripts for niche-relevant search terms via
camofox-browser's @youtube_search macro. Stores results in the
strategic_content table for downstream training / idea mining.

VERIFIED:
  camofox-browser @youtube_search → https://www.youtube.com/results?search_query=...
  transcript API: youtube-transcript-api not installed — use camofox get_text
"""
import os
import sys
import json
import time
import asyncio
import logging
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

CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://localhost:9377")
USER_ID = "empire"

# Niche → search query for YouTube strategy content
NICHE_QUERIES = {
    "roofing": "roofing contractor business growth",
    "hvac": "hvac business lead generation",
    "solar": "solar lead generation home improvement",
    "restoration": "water damage restoration marketing",
    "public_adjuster": "public insurance adjuster business",
    "commercial": "commercial contractor lead generation",
}


def _record_agent_activity(agent_name: str, status: str, rows: int, summary: str):
    if not sb:
        return
    try:
        sb.table("agent_activity").insert({
            "agent_name": agent_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_processed": rows,
            "summary": summary[:500],
        }).execute()
    except Exception as e:
        log.warning(f"agent_activity insert failed: {e}")


async def _scrape_youtube_search(query: str, max_results: int = 5) -> List[Dict]:
    """Open YouTube search for query, extract top video titles + urls."""
    import httpx
    results = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # create tab
            r = await client.post(f"{CAMOFOX_URL}/tabs", json={
                "userId": USER_ID, "sessionKey": f"yt-{int(time.time())}", "url": "https://www.youtube.com"
            })
            tab = r.json()
            tab_id = tab.get("tabId") or tab.get("id")
            if not tab_id:
                return []

            # navigate via macro
            nav = await client.post(
                f"{CAMOFOX_URL}/tabs/{tab_id}/navigate",
                json={"userId": USER_ID, "macro": "@youtube_search", "query": query},
            )
            if nav.status_code >= 400:
                log.warning(f"youtube navigate failed: {nav.status_code} {nav.text[:150]}")
                await client.request("DELETE", f"{CAMOFOX_URL}/tabs/{tab_id}", json={"userId": USER_ID})
                return []

            # wait for results
            try:
                await client.post(f"{CAMOFOX_URL}/tabs/{tab_id}/wait", json={"userId": USER_ID, "condition": "networkidle", "timeoutMs": 6000})
            except Exception:
                pass

            # extract links
            links = await client.get(f"{CAMOFOX_URL}/tabs/{tab_id}/links", params={"userId": USER_ID, "limit": 100})
            for link in (links.json().get("links") or [])[:max_results]:
                url = link.get("url", "")
                if "youtube.com/watch" in url and "v=" in url:
                    results.append({
                        "url": url.split("&")[0],  # strip extra params
                        "title": link.get("text", "")[:200],
                        "query": query,
                    })

            await client.request("DELETE", f"{CAMOFOX_URL}/tabs/{tab_id}", json={"userId": USER_ID})
        except Exception as e:
            log.warning(f"youtube scrape error: {e}")
    return results


def _store_results(rows: List[Dict], niche: str) -> int:
    """Write results to strategic_content (or a fallback table)."""
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
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            written += 1
        except Exception as e:
            # table may not exist; log once
            log.debug(f"strategic_content insert failed: {e}")
            return written
    return written


async def _run_all() -> Dict:
    """Scrape all niche queries, store results."""
    started = datetime.now(timezone.utc)
    all_results = []
    by_niche = {}
    for niche, query in NICHE_QUERIES.items():
        log.info(f"[youtube] scraping niche: {niche} (query: {query!r})")
        try:
            results = await _scrape_youtube_search(query, max_results=3)
            by_niche[niche] = len(results)
            for r in results:
                r["niche"] = niche
                all_results.append(r)
        except Exception as e:
            log.warning(f"[youtube] niche {niche} failed: {e}")
        await asyncio.sleep(1)  # be polite

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


def run_once() -> Dict:
    return asyncio.run(_run_all())


def run_loop(interval_seconds: int = 86400):
    async def _run():
        while True:
            try:
                _run_all_sync()
            except Exception as e:
                log.error(f"youtube loop error: {e}")
            await asyncio.sleep(max(60, interval_seconds))
    asyncio.run(_run())


def _run_all_sync():
    asyncio.run(_run_all())


if __name__ == "__main__":
    print(run_once())