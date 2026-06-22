import httpx
import random
import time
from typing import List, Dict, Optional
from selectolax.parser import HTMLParser

# ── Dev Browser Integration ─────────────────────────────────────────────
_DEV_BROWSER_AVAILABLE = False
_DEV_BROWSER_ERROR = None
try:
    from skills.browser_harness import scrape_page as _dev_browser_scrape_page
    _DEV_BROWSER_AVAILABLE = True
except ImportError as e:
    _DEV_BROWSER_ERROR = str(e)


class BaseScraper:
    def __init__(self, source_name: str, rate_limit: float = 3.0):
        self.source_name = source_name
        self.rate_limit = rate_limit
        self.session = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (compatible; EmpireAI/1.0)"},
            timeout=30,
            follow_redirects=True
        )

    def get(self, url: str) -> Optional[HTMLParser]:
        try:
            time.sleep(self.rate_limit + random.uniform(0.5, 2.0))
            resp = self.session.get(url)
            if resp.status_code == 200:
                return HTMLParser(resp.text)
            print(f"[{self.source_name}] {url} -> {resp.status_code}")
            return None
        except Exception as e:
            print(f"[{self.source_name}] Error: {e}")
            return None

    def parse(self, html: HTMLParser) -> List[Dict]:
        raise NotImplementedError

    def run(self, urls: List[str]) -> List[Dict]:
        results = []
        for url in urls:
            html = self.get(url)
            if html:
                results.extend(self.parse(html))
        return results

    def scrape_with_dev_browser(self, url: str, wait_selector: Optional[str] = None) -> Optional[Dict]:
        """Fallback: scrape a JS-rendered page using dev-browser.

        Useful when static HTTP GET fails to capture dynamic content.
        Returns dict with keys: title, text_content, links, screenshot_path, error
        or None if dev-browser is unavailable.
        """
        if not _DEV_BROWSER_AVAILABLE:
            print(f"[{self.source_name}] dev-browser not available: {_DEV_BROWSER_ERROR}")
            return None
        try:
            return _dev_browser_scrape_page(url, wait_selector)
        except Exception as e:
            print(f"[{self.source_name}] dev-browser error: {e}")
            return None
