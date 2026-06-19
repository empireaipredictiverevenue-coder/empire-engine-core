from async_scraper import AsyncScraper
from models import Lead
from selectolax.parser import HTMLParser
from typing import List

class RestorationAsyncScraper(AsyncScraper):
    def __init__(self):
        super().__init__("restoration_async", rate_limit=3.0)

    async def parse(self, html: HTMLParser, url: str) -> List[Lead]:
        results = []
        for card in html.css(".listing, .result, .company, .search-result"):
            name = card.css_first(".name, .title, h3, h4")
            phone = card.css_first(".phone, .tel, [href^=tel:]")
            website = card.css_first("a[href*=http]")

            lead = Lead(
                name=name.text(strip=True) if name else None,
                phone=phone.text(strip=True) if phone else None,
                website=website.attributes.get("href") if website else None,
                vertical="Restoration",
                source=self.source_name,
                meta={"source_url": url}
            )
            results.append(lead)
        return results
