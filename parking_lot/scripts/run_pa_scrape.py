"""Run public adjuster scraper for Texas"""
import sys, json
sys.path.insert(0, '/root/empire-v49/scrapers')
from public_adjuster_scraper import PublicAdjusterScraper

scraper = PublicAdjusterScraper()
urls = [
    "https://www.bbb.org/search?term=public+adjuster&location=Texas",
    "https://www.bbb.org/search?term=public+adjuster&location=Dallas%2C+TX",
    "https://www.bbb.org/search?term=public+adjuster&location=Houston%2C+TX",
]
results = scraper.run(urls)
print(json.dumps({"count": len(results), "results": results[:100]}, indent=2))
