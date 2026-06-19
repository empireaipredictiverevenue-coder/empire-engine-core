from typing import Dict, List
from models import Lead
from quantitative import QuantitativeTracker
from predictive_brain import PredictiveBrain

class MultiNicheFramework:
    def __init__(self):
        self.quant = QuantitativeTracker()
        self.brain = PredictiveBrain()
        
        # Strategy per vertical
        self.strategies = {
            "Public Adjuster": {"priority": 1, "rate_limit": 2.0, "min_score": 70},
            "Restoration": {"priority": 1, "rate_limit": 2.0, "min_score": 65},
            "Commercial Roofing": {"priority": 2, "rate_limit": 3.0, "min_score": 60},
            "Commercial Solar": {"priority": 2, "rate_limit": 3.0, "min_score": 60},
            "Debt Relief": {"priority": 1, "rate_limit": 2.5, "min_score": 75},
            "Merchant Services": {"priority": 3, "rate_limit": 4.0, "min_score": 50},
            "Managed IT": {"priority": 3, "rate_limit": 4.0, "min_score": 50},
        }

    def get_strategy(self, vertical: str) -> Dict:
        return self.strategies.get(vertical, {"priority": 5, "rate_limit": 5.0, "min_score": 40})

    def should_scrape(self, vertical: str) -> bool:
        strategy = self.get_strategy(vertical)
        score = self.brain.predict_source_value(vertical)
        return score >= strategy["min_score"]

    def rank_verticals(self, verticals: List[str]) -> List[str]:
        return sorted(verticals, key=lambda v: self.get_strategy(v)["priority"])
