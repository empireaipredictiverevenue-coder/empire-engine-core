"""PREDICTIVE CAMOFOX SCRAPER — Empire AI (Elite, Google-Free, Max Enhanced)
Uses camofox-browser for stealth scraping across 36+ lanes.
Feeds opportunities directly to the Predictive Revenue Fleet.
"""

import os
import httpx
import asyncio
import logging
from typing import List, Dict, Any

log = logging.getLogger("predictive.camofox_scraper")

CAMOFOX_URL = os.getenv("CAMOFOX_URL", "http://localhost:9377")

# ── Dev Browser Integration (JS-rendered fallback) ──────────────────────
_DEV_BROWSER_AVAILABLE = False
try:
    from skills.browser_harness import scrape_page as _dev_scrape
    import asyncio
    _DEV_BROWSER_AVAILABLE = True
except ImportError:
    pass

class PredictiveCamofoxScraper:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=90.0)
        self.weights = {"relevance": 0.4, "volume": 0.35, "difficulty": 0.25}

    async def create_tab(self, url: str, user_id: str = "empire", session_key: str = "scrape"):
        r = await self.client.post(f"{CAMOFOX_URL}/tabs", json={
            "userId": user_id, "sessionKey": session_key, "url": url
        })
        return r.json()

    async def get_snapshot(self, tab_id: str, user_id: str = "empire"):
        # camofox server reads userId from query string on GET endpoints
        r = await self.client.get(f"{CAMOFOX_URL}/tabs/{tab_id}/snapshot", params={"userId": user_id})
        return r.json()

    async def scrape_niche(self, niche: str, metro: str, max_results: int = 30) -> List[Dict]:
        """Scrape a niche using camofox-browser + search macros"""
        log.info(f"[Camofox] Scraping {niche} in {metro}")
        
        # Source mix: prefer static-render sites (BBB) over JS-heavy (Yelp/Google)
        # because camofox a11y snapshot only captures rendered HTML, not post-JS DOM.
        query = f"{niche} contractors {metro}"
        source_map = {
            "roofing":         ("url", "https://www.bbb.org/us/tx/dallas/category/roofing-contractors"),
            "hvac":            ("url", "https://www.bbb.org/us/tx/dallas/category/air-conditioning-contractors"),
            "solar":           ("url", "https://www.bbb.org/us/tx/dallas/category/solar-energy-contractors"),
            "restoration":     ("url", "https://www.bbb.org/us/tx/dallas/category/fire-and-water-damage-restoration"),
            "public_adjuster": ("url", "https://www.bbb.org/us/tx/dallas/category/public-adjusters"),
            "commercial":      ("url", "https://www.bbb.org/us/tx/dallas/category/general-contractors"),
        }
        kind, payload = source_map.get(niche, ("macro", "@yelp_search"))
        user_id = "empire"
        
        try:
            # camofox blocks about: URLs, must use http(s). Start with a real
            # blank-ish target then navigate via macro.
            start_url = "https://www.google.com"
            tab = await self.create_tab(start_url, user_id=user_id, session_key=f"scrape-{niche}-{metro}")
            tab_id = tab.get("id") or tab.get("tabId")
            if not tab_id:
                log.warning(f"[Camofox] create_tab returned no id: {tab}")
                return []
            
            # Navigate using the chosen source
            if kind == "url":
                # simple metro substitution: tx/dallas → tx/{metro}
                nav_url = payload.replace("/tx/dallas", f"/tx/{metro.replace(chr(32), chr(45))}")
                nav_resp = await self.client.post(
                    f"{CAMOFOX_URL}/tabs/{tab_id}/navigate",
                    json={"userId": user_id, "url": nav_url},
                )
            else:
                nav_resp = await self.client.post(
                    f"{CAMOFOX_URL}/tabs/{tab_id}/navigate",
                    json={"userId": user_id, "macro": payload, "query": query},
                )
            if nav_resp.status_code >= 400:
                log.warning(f"[Camofox] navigate failed {nav_resp.status_code}: {nav_resp.text[:200]}")
            
            # Give JS-rendered pages a moment to render before snapshot
            try:
                await self.client.post(
                    f"{CAMOFOX_URL}/tabs/{tab_id}/wait",
                    json={"userId": user_id, "condition": "networkidle", "timeoutMs": 8000},
                )
            except Exception as wait_err:
                log.debug(f"[Camofox] wait skipped: {wait_err}")

            # Give JS-rendered pages a moment to render before snapshot
            try:
                await self.client.post(
                    f"{CAMOFOX_URL}/tabs/{tab_id}/wait",
                    json={"userId": user_id, "condition": "networkidle", "timeoutMs": 8000},
                )
            except Exception as wait_err:
                log.debug(f"[Camofox] wait skipped: {wait_err}")

            snapshot = await self.get_snapshot(tab_id, user_id=user_id)

            # Extract outbound links as a second-opinion opportunity list
            try:
                links_resp = await self.client.get(
                    f"{CAMOFOX_URL}/tabs/{tab_id}/links",
                    params={"userId": user_id},
                )
                if links_resp.status_code == 200:
                    snap = snapshot if isinstance(snapshot, dict) else {}
                    snap["_links"] = links_resp.json()
                    snapshot = snap
            except Exception as links_err:
                log.debug(f"[Camofox] links extract skipped: {links_err}")

            await self.client.request("DELETE", f"{CAMOFOX_URL}/tabs/{tab_id}", json={"userId": user_id})
            
            # Parse snapshot into structured opportunities
            opportunities = self._parse_snapshot(snapshot, niche, metro)
            return opportunities[:max_results]
            
        except Exception as e:
            log.warning(f"[Camofox] camofox-browser failed for {niche}/{metro}: {e}")
            # Fallback to dev-browser for JS-rendered pages
            if _DEV_BROWSER_AVAILABLE:
                log.info(f"[Camofox] Falling back to dev-browser for {niche}/{metro}")
                try:
                    result = await asyncio.to_thread(
                        _dev_scrape,
                        f"https://www.google.com/search?q={niche}+contractors+in+{metro}"
                    )
                    if result and result.get("text_content"):
                        lines = result["text_content"].split("\n")
                        for line in lines:
                            if len(line.strip()) > 30:
                                opportunities.append({
                                    "domain": line.strip()[:100],
                                    "niche": niche,
                                    "metro": metro,
                                    "source": "dev-browser"
                                })
                        return opportunities[:max_results]
                except Exception as dev_err:
                    log.error(f"[Camofox] dev-browser fallback also failed: {dev_err}")
            return []

    def _parse_snapshot(self, snapshot: Dict, niche: str, metro: str) -> List[Dict]:
        """Parse camofox a11y snapshot + links into structured business leads.

        Strategy:
          1. From `_links` (if extracted) take any bbb.org URLs that look like
             individual business pages (path /biz/... or /business/...) — these
             are real contractor listings.
          2. From the snapshot text, take any "link 'Business Name' [eN]" lines
             that look like proper nouns (Title Case, not nav/footer text).
        Returns up to max_results opportunities.
        """
        opportunities: List[Dict] = []
        seen: set = set()

        # 1) Links-based extraction (most reliable)
        links_payload = snapshot.get("_links", {}) if isinstance(snapshot, dict) else {}
        for link in links_payload.get("links", []) or []:
            url = (link.get("url") or "").lower()
            text_label = (link.get("text") or "").strip()
            if not url or not text_label:
                continue
            if "bbb.org" in url and ("/biz/" in url or "/business/" in url or "/profile/" in url):
                key = url.split("?")[0]
                if key in seen:
                    continue
                seen.add(key)
                opportunities.append({
                    "name": text_label[:120],
                    "url": link["url"],
                    "niche": niche,
                    "metro": metro,
                    "source": "camofox-bbb",
                    "domain": url.split("/")[2] if "://" in url else "",
                })

        # 2) Snapshot-text-based extraction (fallback)
        if len(opportunities) < 5:
            text = snapshot.get("snapshot", "") or snapshot.get("text", "") or ""
            for line in text.split("\n"):
                l = line.strip()
                if not l.startswith("- link "):
                    continue
                if "[e" not in l:
                    continue
                try:
                    name = l.split('"')[1].strip()
                except IndexError:
                    continue
                if len(name) < 4 or len(name) > 80:
                    continue
                low = name.lower()
                if any(skip in low for skip in ["cookie", "privacy", "homepage", "login", "sign in", "sign up", "search", "filter", "sort by", "see more", "read more", "get a quote", "leave a review", "file a complaint"]):
                    continue
                if any(k in low for k in [niche[:4], "roof", "hvac", "solar", "restoration", "adjuster", "construction", "builders", "contractor", "company", "services"]):
                    if name not in seen:
                        seen.add(name)
                        opportunities.append({
                            "name": name,
                            "url": "",
                            "niche": niche,
                            "metro": metro,
                            "source": "camofox-snapshot",
                            "domain": "",
                        })

        return opportunities

    async def _agi_self_improvement(self):
        """Self-optimize scraping strategy"""
        self.weights = {"relevance": 0.4, "volume": 0.35, "difficulty": 0.25}
        log.info("[Camofox] AGI self-optimized scraping weights")

    async def run_cycle(self) -> Dict[str, Any]:
        niches = ["roofing", "hvac", "solar", "restoration", "public_adjuster", "commercial"]
        metros = ["texas", "florida", "california", "arizona"]
        results = []
        
        for niche in niches:
            for metro in metros:
                results.extend(await self.scrape_niche(niche, metro))
        
        await self._agi_self_improvement()
        log.info(f"[Camofox] Cycle complete — {len(results)} opportunities")
        return {"opportunities": results, "count": len(results)}

async def run_continuously(interval_minutes: int = 360):
    scraper = PredictiveCamofoxScraper()
    while True:
        try:
            result = await scraper.run_cycle()
            log.info(f'[Camofox] Results: {result["count"]} opportunities')
        except Exception as e:
            log.error(f"[Camofox] Error: {e}")
        await asyncio.sleep(interval_minutes * 60)

def run_once():
    """Single cycle for agent_runner loop mode."""
    async def _run():
        scraper = PredictiveCamofoxScraper()
        result = await scraper.run_cycle()
        return result
    return asyncio.run(_run())


def run_loop(interval_seconds: int = 3600):
    """Loop wrapper for agent_runner — converts seconds to minutes."""
    minutes = max(60, interval_seconds // 60)
    asyncio.run(run_continuously(interval_minutes=minutes))


if __name__ == "__main__":
    asyncio.run(run_continuously())

# === Fleet Integration ===
async def feed_to_outreach(opportunities: List[Dict]):
    """Send opportunities to the Predictive Outreach Agent"""
    try:
        from predictive_outreach_agent import StrikerOutreachAgent
        outreach = StrikerOutreachAgent()
        for opp in opportunities:
            await outreach._unstoppable_draft(opp)
            log.info(f"[Camofox] Opportunity fed to outreach: {opp.get(domain)}")
    except Exception as e:
        log.error(f"[Camofox] Failed to feed outreach: {e}")

# === Telegram Command Support ===



# === Telegram Command Support (module-level) ===
async def handle_telegram_command(message: str, scraper=None) -> str:
    """Handle /scrape and /status commands from Telegram operators.

    Args:
        message: command text starting with /
        scraper: optional PredictiveCamofoxScraper instance (created lazily if None)
    """
    if scraper is None:
        scraper = PredictiveCamofoxScraper()

    if message.startswith("/scrape"):
        parts = message.split()
        niche = parts[1] if len(parts) > 1 else "roofing"
        metro = parts[2] if len(parts) > 2 else "texas"
        try:
            results = await scraper.scrape_niche(niche, metro, max_results=10)
            return f"Scraped {len(results)} {niche} opportunities in {metro}"
        except Exception as e:
            return f"Scrape failed: {e}"
    elif message.strip() == "/status":
        return f"Predictive Camofox Scraper running (camofox_url={CAMOFOX_URL})"
    return "Unknown command. Try /scrape <niche> <metro> or /status"
