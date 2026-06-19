from typing import Dict
from logging_config import get_logger

logger = get_logger("scraper.self_healing")

class SelfHealingManager:
    def __init__(self):
        self.failures: Dict[str, int] = {}
        self.paused: Dict[str, bool] = {}

    def record_failure(self, source: str):
        self.failures[source] = self.failures.get(source, 0) + 1
        if self.failures[source] >= 5:
            self.paused[source] = True
            logger.warning("Source auto-paused", source=source)

    def is_paused(self, source: str) -> bool:
        return self.paused.get(source, False)

    def reset(self, source: str):
        self.failures[source] = 0
        self.paused[source] = False
