import asyncio
import httpx
import random
from typing import List, Optional
from models import Lead
from selectolax.parser import HTMLParser

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

class AsyncScraper:
    def __init__(self, source_name: str, rate_limit: float = 2.0, use_browser: bool = False):
        self.source_name = source_name
        self.rate_limit = rate_limit
        self.use_browser = use_browser
        self.semaphore = asyncio.Semaphore(5)

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def fetch(self, client: httpx.AsyncClient, url: str) -> HTMLParser | None:
        async with self.semaphore:
            await asyncio.sleep(self.rate_limit + random.uniform(0.5, 2.0))
            try:
                resp = await client.get(url, headers=self._get_headers(), timeout=30)
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
        if self.use_browser:
            return await self._run_browser(urls)
        else:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                tasks = [self.fetch(client, url) for url in urls]
                htmls = await asyncio.gather(*tasks)
                results = []
                for html, url in zip(htmls, urls):
                    if html:
                        results.extend(await self.parse(html, url))
                return results

    async def _run_browser(self, urls: List[str]) -> List[Lead]:
        from playwright.async_api import async_playwright
        results = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = await context.new_page()
            for url in urls:
                await asyncio.sleep(self.rate_limit)
                try:
                    await page.goto(url, timeout=30000)
                    html = HTMLParser(await page.content())
                    results.extend(await self.parse(html, url))
                except Exception as e:
                    print(f"[{self.source_name}] Browser error on {url}: {e}")
            await browser.close()
        return results
