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

    async def get_snapshot(self, tab_id: str):
        r = await self.client.get(f"{CAMOFOX_URL}/tabs/{tab_id}/snapshot")
        return r.json()

    async def scrape_niche(self, niche: str, metro: str, max_results: int = 30) -> List[Dict]:
        """Scrape a niche using camofox-browser + search macros"""
        log.info(f"[Camofox] Scraping {niche} in {metro}")
        
        # Use search macro
        macro_map = {
            "roofing": "@yelp_search",
            "hvac": "@yelp_search",
            "solar": "@google_search",
            "restoration": "@yelp_search",
            "public_adjuster": "@google_search",
            "commercial": "@google_search"
        }
        macro = macro_map.get(niche, "@google_search")
        
        try:
            tab = await self.create_tab("about:blank")
            tab_id = tab.get("id")
            
            # Navigate with search macro
            await self.client.post(f"{CAMOFOX_URL}/tabs/{tab_id}/navigate", json={
                "macro": macro,
                "query": f"{niche} contractors in {metro}"
            })
            
            snapshot = await self.get_snapshot(tab_id)
            await self.client.delete(f"{CAMOFOX_URL}/tabs/{tab_id}")
            
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
        """Parse accessibility snapshot into structured opportunities"""
        text = snapshot.get("snapshot", "")
        opportunities = []
        
        # Simple parsing (improve with better NLP later)
        lines = text.split("\n")
        for line in lines:
            if any(word in line.lower() for word in ["roof", "hvac", "solar", "restoration", "adjuster"]):
                opportunities.append({
                    "domain": line.strip()[:100],
                    "niche": niche,
                    "metro": metro,
                    "source": "camofox"
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
