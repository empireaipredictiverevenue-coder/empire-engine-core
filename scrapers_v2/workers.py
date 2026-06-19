from celery import Celery
from public_adjuster_async import PublicAdjusterAsyncScraper
from restoration_async import RestorationAsyncScraper
import asyncio

app = Celery("scraper", broker="redis://localhost:6379/0")

@app.task
def scrape_vertical(vertical: str, max_results: int = 100):
    if vertical == "Public Adjuster":
        scraper = PublicAdjusterAsyncScraper()
    elif vertical == "Restoration":
        scraper = RestorationAsyncScraper()
    else:
        return []

    results = asyncio.run(scraper.run([]))  # Add real URLs here
    return [r.model_dump() for r in results[:max_results]]
