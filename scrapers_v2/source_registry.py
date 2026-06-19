from typing import List, Dict
import yaml
from pathlib import Path

def load_sources(path: str = "sources.yaml") -> List[Dict]:
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f)
    # Fallback to inline sources
    from sources import SOURCES
    return SOURCES

def get_sources_by_vertical(vertical: str) -> List[Dict]:
    return [s for s in load_sources() if s["vertical"] == vertical]

def get_sources_by_priority(max_priority: int = 5) -> List[Dict]:
    return [s for s in load_sources() if s.get("priority", 10) <= max_priority]
