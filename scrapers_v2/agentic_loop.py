import asyncio
from typing import List
from orchestrator import run_all_sources
from quantitative import QuantitativeTracker
from predictive_brain import PredictiveBrain
from logging_config import get_logger

logger = get_logger("scraper.agentic")

quant = QuantitativeTracker()
brain = PredictiveBrain()

async def reflect_and_adjust():
    """
    Agentic loop: The scraper reflects on its performance and adjusts strategy.
    """
    summary = quant.summary()
    logger.info("Agentic reflection started", summary=summary)

    # Identify underperforming sources (score < 40)
    weak_sources = [s for s, data in summary.items() if data["score"] < 40]
    if weak_sources:
        logger.warning("Weak sources detected", sources=weak_sources)
        # Future: autonomously lower priority or pause these sources

    # Identify high-performing sources (score > 80)
    strong_sources = [s for s, data in summary.items() if data["score"] > 80]
    if strong_sources:
        logger.info("Strong sources detected — consider increasing frequency", sources=strong_sources)

    # Self-proposed improvement
    if len(weak_sources) > 2:
        logger.info("Agentic suggestion: Review source quality or add new verticals")

    return {"weak": weak_sources, "strong": strong_sources}

async def agentic_cycle():
    """Full agentic loop: scrape → reflect → adjust."""
    logger.info("Agentic cycle started")
    results = await run_all_sources()
    reflection = await reflect_and_adjust()
    logger.info("Agentic cycle complete", reflection=reflection)
    return results
