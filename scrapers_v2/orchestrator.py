import asyncio
from sources import SOURCES
from public_adjuster_async import PublicAdjusterAsyncScraper
from restoration_async import RestorationAsyncScraper
from predictive_brain import PredictiveBrain
from quantitative import QuantitativeTracker
from multiniche import MultiNicheFramework
from dedup import deduplicate
from models import Lead
from typing import List

SCRAPERS = {
    "public_adjuster_async": PublicAdjusterAsyncScraper,
    "restoration_async": RestorationAsyncScraper,
}

brain = PredictiveBrain()
quant = QuantitativeTracker()
multiniche = MultiNicheFramework()

async def run_all_sources() -> List[Lead]:
    all_leads: List[Lead] = []
    existing: set = set()

    # Get all verticals and rank them using multi-niche framework
    verticals = list(set(s["vertical"] for s in SOURCES))
    ranked_verticals = multiniche.rank_verticals(verticals)

    for vertical in ranked_verticals:
        if not multiniche.should_scrape(vertical):
            continue

        source = next((s for s in SOURCES if s["vertical"] == vertical), None)
        if not source:
            continue

        scraper_cls = SCRAPERS.get(source["scraper"])
        if not scraper_cls:
            continue

        scraper = scraper_cls()
        leads = await scraper.run(source["urls"])

        for lead in leads:
            score = await brain.score_lead(lead)
            lead.meta["predicted_score"] = score
            quant.record_lead(lead)

        unique = deduplicate(leads, existing)
        all_leads.extend(unique)

    return all_leads
