"""Run restoration scraper for Dallas + Houston"""
import sys, json
sys.path.insert(0, '/root/empire-v49/scrapers')
from restoration_scraper import RestorationScraper

scraper = RestorationScraper()
urls = [
    "https://www.bbb.org/search?term=restoration&location=Dallas%2C+TX",
    "https://www.bbb.org/search?term=restoration&location=Houston%2C+TX",
]
results = scraper.run(urls)
print(json.dumps({"count": len(results), "results": results[:100]}, indent=2))
