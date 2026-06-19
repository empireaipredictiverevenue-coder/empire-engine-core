from typing import List, Dict
from models import Lead
from collections import defaultdict
import asyncio
from synthetic_brain import llm_score_lead

class PredictiveBrain:
    def __init__(self):
        self.source_stats: Dict[str, Dict] = defaultdict(lambda: {"leads": 0, "converted": 0})

    async def score_lead(self, lead: Lead) -> float:
        """Hybrid scoring: LLM first, fallback to rules."""
        try:
            return await llm_score_lead(lead)
        except:
            score = 50.0
            if lead.vertical in ["Public Adjuster", "Restoration"]:
                score += 20
            if lead.phone:
                score += 15
            if lead.email:
                score += 10
            if lead.website:
                score += 5
            return min(score, 100.0)

    def predict_source_value(self, source: str) -> float:
        stats = self.source_stats.get(source, {"leads": 0, "converted": 0})
        if stats["leads"] == 0:
            return 50.0
        return (stats["converted"] / stats["leads"]) * 100

    def update_stats(self, source: str, converted: bool):
        self.source_stats[source]["leads"] += 1
        if converted:
            self.source_stats[source]["converted"] += 1

    def rank_sources(self, sources: List[str]) -> List[str]:
        return sorted(sources, key=self.predict_source_value, reverse=True)
