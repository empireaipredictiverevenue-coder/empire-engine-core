from logging_config import get_logger
from circuit_breaker import CircuitBreaker

logger = get_logger("scraper.errors")

class RobustErrorHandler:
    def __init__(self):
        self.source_failures = {}

    def handle_source_error(self, source: str, error: Exception):
        self.source_failures[source] = self.source_failures.get(source, 0) + 1
        logger.error("Source error", source=source, error=str(error), count=self.source_failures[source])

        if self.source_failures[source] >= 5:
            logger.warning("Source paused due to repeated failures", source=source)
            # Future: automatically pause this source in the registry

    def reset_source(self, source: str):
        self.source_failures[source] = 0
