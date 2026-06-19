"""
EMPIRE V49 · VIBE-TRADING GENOME
===================================
Wraps integrations/Vibe-Trading (HKUDS) into Empire AI's product genome.
Vibe-Trading is an agent-native framework that translates natural language
finance queries into automated research and trading workflows.

Architecture:
  Investment Committee Agent → Strategy formulation
  Quant Desk Agent          → Statistical analysis + backtesting
  Execution Agent            → Paper/live trading at brokers
  Alpha Research Factors     → Pre-built market factors

Supports: US, HK, A-share markets via LangChain/LangGraph + FastMCP.

Source: https://github.com/HKUDS/Vibe-Trading
Cloned: integrations/Vibe-Trading/
Kanban: t_vibetrading_genome
"""

import os
import sys
import logging
from typing import Dict, Any, Optional, List

sys.path.insert(0, "/root/empire-v49")

from bots.empire_product_core import EmpireProductCore

log = logging.getLogger("empire.vibetrading")


class VibeTradingGenome(EmpireProductCore):
    """Empire AI product genome wrapping Vibe-Trading agent."""

    def __init__(self):
        super().__init__("vibetrading_genome")

    def _product_specific_data(self) -> List[Dict]:
        return [
            {"niche": "market_research", "value": 5999, "agent": "vibetrading"},
            {"niche": "sentiment_analysis", "value": 3999, "agent": "vibetrading"},
            {"niche": "strategy_backtest", "value": 7999, "agent": "vibetrading"},
        ]

    def _product_specific_scoring(self, item: dict) -> float:
        score = 50
        if item.get("value", 0) > 6000:
            score += 25
        vibe_path = "/root/empire-v49/integrations/Vibe-Trading"
        if os.path.isdir(vibe_path):
            score += 10
        return min(score, 100)

    def _product_specific_action(self, item: dict):
        log.info(f"[vibetrading] executing action for {item.get('niche')}")
        self._predictive_integration(item)

    def research_thesis(self, query: str) -> Dict[str, Any]:
        """Generate a trading thesis from a natural language query.

        Uses Vibe-Trading's Investment Committee agent pattern
        via the AI Router for LLM-powered research synthesis.
        """
        try:
            from empire_ai_router import AIRouter
            router = AIRouter()
            result = router.generate_json(
                prompt=f"Act as an Investment Committee agent. Given the query: '{query}', return a trading thesis with: thesis (1-2 sentences), conviction (0-100), time_horizon (short/medium/long), key_risks (list of 2-4 strings).",
                task="vibetrading.thesis",
                temperature=0.4,
                max_tokens=300,
            )
            if "_error" not in result:
                return result
        except Exception as e:
            log.debug(f"[vibetrading] thesis generation failed: {e}")
        return {"thesis": "Analysis unavailable", "conviction": 0}


_vibetrading: Optional[VibeTradingGenome] = None


def get_vibetrading_genome() -> VibeTradingGenome:
    global _vibetrading
    if _vibetrading is None:
        _vibetrading = VibeTradingGenome()
    return _vibetrading
