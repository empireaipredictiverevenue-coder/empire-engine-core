from typing import Dict, List
from collections import defaultdict
from models import Lead

class ABTestingFramework:
    def __init__(self):
        self.variants: Dict[str, List[Lead]] = defaultdict(list)
        self.metrics: Dict[str, Dict] = defaultdict(lambda: {"leads": 0, "converted": 0})

    def assign_variant(self, lead: Lead, variants: List[str]) -> str:
        # Simple round-robin assignment
        variant = variants[hash(lead.website) % len(variants)]
        self.variants[variant].append(lead)
        self.metrics[variant]["leads"] += 1
        return variant

    def record_conversion(self, variant: str):
        self.metrics[variant]["converted"] += 1

    def get_winner(self) -> str:
        best = max(self.metrics.items(), key=lambda x: x[1]["converted"] / max(x[1]["leads"], 1))
        return best[0]
