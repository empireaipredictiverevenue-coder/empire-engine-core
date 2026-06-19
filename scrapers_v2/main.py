import asyncio
import sys
from orchestrator import run_all_sources
from logging_config import get_logger
from metrics import start_metrics_server, record_lead
from circuit_breaker import CircuitBreaker
from quantitative import QuantitativeTracker
from error_reporting import RobustErrorHandler
from alerting import alert_source_paused, alert_circuit_breaker_open
from self_healing import SelfHealingManager
from cost_analytics import CostAnalytics

logger = get_logger("scraper.main")
breaker = CircuitBreaker(failure_threshold=5, recovery_time=300)
quant = QuantitativeTracker()
error_handler = RobustErrorHandler()
healing = SelfHealingManager()
cost = CostAnalytics()

async def main():
    logger.info("Elite Scraper v2 started")
    start_metrics_server(8002)
    try:
        results = await breaker.call(run_all_sources)
        for lead in results:
            record_lead(lead.vertical, lead.source)
            quant.record_lead(lead)
            cost.record(lead.source, 0.5)
        logger.info(f"Completed. New leads: {len(results)}")
        logger.info("Cost per lead", summary=cost.summary())
    except Exception as e:
        logger.error(f"Failed: {e}")
        error_handler.handle_source_error("global", e)
        healing.record_failure("global")
        if healing.is_paused("global"):
            alert_source_paused("global")
        alert_circuit_breaker_open()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
