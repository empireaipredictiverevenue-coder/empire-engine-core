import asyncio
import httpx
import random
from typing import List
from models import Lead
from selectolax.parser import HTMLParser

class AsyncScraper:
    def __init__(self, source_name: str, rate_limit: float = 2.0):
        self.source_name = source_name
        self.rate_limit = rate_limit
        self.semaphore = asyncio.Semaphore(5)

    async def fetch(self, client: httpx.AsyncClient, url: str) -> HTMLParser | None:
        async with self.semaphore:
            await asyncio.sleep(self.rate_limit + random.uniform(0.3, 1.2))
            try:
                resp = await client.get(url, timeout=30)
                if resp.status_code == 200:
                    return HTMLParser(resp.text)
                print(f"[{self.source_name}] {url} -> {resp.status_code}")
                return None
            except Exception as e:
                print(f"[{self.source_name}] Error: {e}")
                return None

    async def parse(self, html: HTMLParser, url: str) -> List[Lead]:
        raise NotImplementedError

    async def run(self, urls: List[str]) -> List[Lead]:
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
            tasks = [self.fetch(client, url) for url in urls]
            htmls = await asyncio.gather(*tasks)
            results = []
            for html, url in zip(htmls, urls):
                if html:
                    results.extend(await self.parse(html, url))
            return results
