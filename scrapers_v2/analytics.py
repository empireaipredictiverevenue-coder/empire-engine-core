from typing import List, Dict
from collections import Counter
from models import Lead

def daily_summary(leads: List[Lead]) -> Dict:
    """Generate a simple daily analytics summary."""
    by_vertical = Counter(l.vertical for l in leads)
    by_source = Counter(l.source for l in leads)
    total = len(leads)

    return {
        "total_leads": total,
        "by_vertical": dict(by_vertical),
        "by_source": dict(by_source),
        "unique_cities": len(set(l.city for l in leads if l.city)),
    }
