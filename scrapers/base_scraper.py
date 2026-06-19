import httpx
import random
import time
from typing import List, Dict, Optional
from selectolax.parser import HTMLParser

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
