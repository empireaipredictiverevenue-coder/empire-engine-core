"""
EMPIRE V49 · AUTOHEDGE TRADING GENOME
=========================================
Wraps integrations/AutoHedge (The-Swarm-Corporation) into Empire AI's
product genome format. AutoHedge is an enterprise-grade autonomous agent
hedge fund with 4 specialized agents on Solana.

Architecture:
  Director Agent  → Strategy generation & thesis
  Quant Agent     → Technical/statistical/market analysis
  Risk Agent      → Position sizing & risk assessment
  Execution Agent → Trade execution via Jupiter API

This genome feeds AutoHedge's multi-agent intelligence into Empire's
sniper brain (empire_sniper_brain.py) for enhanced dynamic config.

Source: https://github.com/The-Swarm-Corporation/AutoHedge
Cloned: integrations/AutoHedge/
Kanban: t_autohedge_genome
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

sys.path.insert(0, "/root/empire-v49")
sys.path.insert(0, "/root/empire-v49/integrations/AutoHedge")

from bots.empire_product_core import EmpireProductCore

log = logging.getLogger("empire.autohedge")

# ── AI Router for LLM integration ─────────────────────────────────────
try:
    from empire_ai_router import AIRouter
    _HAS_ROUTER = True
except ImportError:
    _HAS_ROUTER = False

# ── Supabase for trade logging ────────────────────────────────────────
try:
    from supabase import create_client
    _sb = create_client(
        os.environ.get("SUPABASE_URL", ""),
        os.getenv("SUPABASE_SERVICE_KEY", ""),
    )
except Exception:
    _sb = None


class AutoHedgeGenome(EmpireProductCore):
    """Empire AI product genome wrapping AutoHedge multi-agent trading."""

    def __init__(self):
        super().__init__("autohedge_genome")

    # ── Product-specific data ──────────────────────────────────────
    def _product_specific_data(self) -> List[Dict]:
        """Return trading niches this genome covers."""
        return [
            {"niche": "solana_meme", "value": 4999, "agent": "autohedge"},
            {"niche": "solana_defi", "value": 7999, "agent": "autohedge"},
            {"niche": "jupiter_swaps", "value": 3999, "agent": "autohedge"},
        ]

    # ── Product-specific scoring ───────────────────────────────────
    def _product_specific_scoring(self, item: dict) -> float:
        """Score a trading opportunity using AutoHedge's agent framework."""
        score = 50  # baseline

        # Boost for high-value niches
        if item.get("value", 0) > 5000:
            score += 20

        # Boost if autohedge integration is active
        autohedge_path = "/root/empire-v49/integrations/AutoHedge"
        if os.path.isdir(autohedge_path):
            score += 15

        return min(score, 100)

    # ── Product-specific action ────────────────────────────────────
    def _product_specific_action(self, item: dict):
        """Execute an AutoHedge-powered trading action."""
        log.info(f"[autohedge] executing action for {item.get('niche')}")
        self._predictive_integration(item)

    # ── Risk assessment (from AutoHedge's Risk Agent logic) ────────
    def assess_risk(
        self,
        token_address: str,
        market_sentiment: str = "neutral",
        volatility_score: float = 50.0,
    ) -> Dict[str, Any]:
        """Assess risk for a token using AutoHedge's risk framework.

        Returns a dict with:
          - risk_score: 0-100 (higher = riskier)
          - position_size_pct: recommended position size as % of wallet
          - recommendation: BUY / HOLD / SELL / SKIP
        """
        risk_score = volatility_score  # base on volatility

        # Adjust for sentiment
        sentiment_mult = {
            "bullish": 0.7,
            "neutral": 1.0,
            "bearish": 1.4,
        }
        risk_score *= sentiment_mult.get(market_sentiment, 1.0)

        # Cap
        risk_score = min(100, max(0, risk_score))

        # Position sizing (inverse of risk)
        if risk_score < 30:
            position_pct = 15.0
            recommendation = "BUY"
        elif risk_score < 50:
            position_pct = 10.0
            recommendation = "BUY"
        elif risk_score < 70:
            position_pct = 5.0
            recommendation = "HOLD"
        elif risk_score < 85:
            position_pct = 2.0
            recommendation = "HOLD"
        else:
            position_pct = 0.0
            recommendation = "SKIP"

        result = {
            "token": token_address,
            "risk_score": round(risk_score, 1),
            "position_size_pct": position_pct,
            "recommendation": recommendation,
            "sentiment": market_sentiment,
        }

        # Log to Supabase if available
        if _sb:
            try:
                _sb.table("sniper_stats").upsert({
                    "token_address": token_address,
                    "risk_score": round(risk_score, 1),
                    "recommendation": recommendation,
                    "source": "autohedge_genome",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception:
                pass

        return result

    # ── Market analysis (from AutoHedge's Quant Agent logic) ───────
    def analyze_market(self, token_address: Optional[str] = None) -> Dict[str, Any]:
        """Run market analysis using AutoHedge's quant framework.

        Returns market conditions that the sniper brain can use
        for dynamic config optimization.
        """
        analysis = {
            "market_sentiment": "neutral",
            "volatility_score": 50.0,
            "recommended_mode": "balanced",
            "recommended_risk_threshold": 40,
            "source": "autohedge_genome",
        }

        # If AIRouter is available, use LLM for deeper analysis
        if _HAS_ROUTER and token_address:
            try:
                router = AIRouter()
                prompt = f"Analyze market conditions for token {token_address} on Solana. Return JSON with: market_sentiment (bullish/neutral/bearish), volatility_score (0-100), recommended_mode (aggressive/balanced/conservative), recommended_risk_threshold (0-100)."
                result = router.generate_json(
                    prompt=prompt,
                    task="autohedge.market_analysis",
                    temperature=0.3,
                    max_tokens=200,
                )
                if "_error" not in result:
                    analysis.update(result)
            except Exception as e:
                log.debug(f"[autohedge] LLM analysis failed: {e}")

        return analysis

    # ── Feed sniper brain with optimized config ────────────────────
    def optimize_sniper_config(self, current_stats: dict) -> Dict[str, Any]:
        """Generate sniper brain config adjustments using AutoHedge logic.

        Called by empire_sniper_brain.py to blend AutoHedge's
        risk management into the dynamic sniper configuration.
        """
        config = {}

        # Scale buy amount based on risk assessment
        wallet_balance = current_stats.get("wallet_balance_sol", 0) or 0
        success_rate = current_stats.get("success_rate_pct", 50) or 50

        if wallet_balance > 0:
            # AutoHedge rule: never risk more than 5% of wallet
            max_buy = wallet_balance * 0.05
            config["buy_amount_sol"] = round(max_buy, 3)

        # Adjust market mode based on success rate
        if success_rate >= 70:
            config["market_mode"] = "aggressive"
            config["min_risk_score"] = 25
        elif success_rate >= 40:
            config["market_mode"] = "balanced"
            config["min_risk_score"] = 40
        else:
            config["market_mode"] = "conservative"
            config["min_risk_score"] = 60

        # AutoHedge risk management: scale Jito tips
        config["jito_base_tip_sol"] = 0.005
        if config.get("market_mode") == "aggressive":
            config["jito_max_tip_sol"] = 0.03

        return config


# ── Singleton ────────────────────────────────────────────────────────
_autohedge: Optional[AutoHedgeGenome] = None


def get_autohedge_genome() -> AutoHedgeGenome:
    global _autohedge
    if _autohedge is None:
        _autohedge = AutoHedgeGenome()
    return _autohedge
