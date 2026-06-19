from typing import Dict
from collections import defaultdict
from models import Lead

class CostAnalytics:
    def __init__(self):
        self.costs: Dict[str, Dict] = defaultdict(lambda: {"time": 0.0, "leads": 0})

    def record(self, source: str, duration: float):
        self.costs[source]["time"] += duration
        self.costs[source]["leads"] += 1

    def cost_per_lead(self, source: str) -> float:
        data = self.costs[source]
        if data["leads"] == 0:
            return 0.0
        return round(data["time"] / data["leads"], 2)

    def summary(self) -> Dict:
        return {k: {"cost_per_lead": self.cost_per_lead(k), **v} for k, v in self.costs.items()}
