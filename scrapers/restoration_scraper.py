from base_scraper import BaseScraper
from selectolax.parser import HTMLParser
from typing import List, Dict

class RestorationScraper(BaseScraper):
    def __init__(self):
        super().__init__("restoration", rate_limit=4.0)

    def parse(self, html: HTMLParser) -> List[Dict]:
        results = []
        for card in html.css(".listing, .result, .company"):
            name = card.css_first(".name, .title")
            phone = card.css_first(".phone, .tel")
            website = card.css_first("a[href*=http]")
            if name:
                results.append({
                    "name": name.text(strip=True) if name else None,
                    "phone": phone.text(strip=True) if phone else None,
                    "website": website.attributes.get("href") if website else None,
                    "vertical": "Restoration",
                    "source": self.source_name
                })
        return results
