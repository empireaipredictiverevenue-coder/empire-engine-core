import asyncio
from sources import SOURCES
from public_adjuster_async import PublicAdjusterAsyncScraper
from restoration_async import RestorationAsyncScraper
from predictive_brain import PredictiveBrain
from quantitative import QuantitativeTracker
from enrichment import enrich_lead
from dedup import deduplicate
from models import Lead
from typing import List

SCRAPERS = {
    "public_adjuster_async": PublicAdjusterAsyncScraper,
    "restoration_async": RestorationAsyncScraper,
}

brain = PredictiveBrain()
quant = QuantitativeTracker()

async def run_all_sources() -> List[Lead]:
    all_leads: List[Lead] = []
    existing: set = set()

    for source in SOURCES:
        scraper_cls = SCRAPERS.get(source["scraper"])
        if not scraper_cls:
            continue

        scraper = scraper_cls()
        leads = await scraper.run(source["urls"])

        enriched = [enrich_lead(lead) for lead in leads]

        for lead in enriched:
            score = await brain.score_lead(lead)
            lead.meta["predicted_score"] = score
            quant.record_lead(lead)

        unique = deduplicate(enriched, existing)
        all_leads.extend(unique)

    return all_leads
