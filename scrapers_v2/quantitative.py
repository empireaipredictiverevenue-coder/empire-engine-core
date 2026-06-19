from typing import Dict
from collections import defaultdict
from models import Lead

class QuantitativeTracker:
    def __init__(self):
        self.stats: Dict[str, Dict] = defaultdict(lambda: {
            "leads": 0,
            "converted": 0,
            "total_score": 0.0,
            "cost_seconds": 0.0
        })

    def record_lead(self, lead: Lead, duration: float = 0.0):
        s = self.stats[lead.source]
        s["leads"] += 1
        s["total_score"] += lead.meta.get("predicted_score", 50)
        s["cost_seconds"] += duration

    def record_conversion(self, source: str):
        self.stats[source]["converted"] += 1

    def get_source_score(self, source: str) -> float:
        s = self.stats[source]
        if s["leads"] == 0:
            return 50.0
        conversion_rate = s["converted"] / s["leads"]
        avg_score = s["total_score"] / s["leads"]
        cost_penalty = min(s["cost_seconds"] / max(s["leads"], 1), 10)
        return (conversion_rate * 40) + (avg_score * 0.4) - cost_penalty

    def rank_sources(self, sources: list) -> list:
        return sorted(sources, key=self.get_source_score, reverse=True)

    def summary(self) -> Dict:
        return {k: {"score": self.get_source_score(k), **v} for k, v in self.stats.items()}
