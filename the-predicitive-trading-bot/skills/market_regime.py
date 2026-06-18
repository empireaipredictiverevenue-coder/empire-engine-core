"""
PREDICITIVE TRADING BOT · MARKET REGIME DETECTOR
===================================================
Classifies current market conditions per market type to enable
adaptive strategy parameters.

Architecture:
  - MarketRegimeDetector: classifies regimes from price history
  - Regime types: trending_up, trending_down, ranging, volatile, calm, breakout
  - Market-specific detection thresholds (crypto vs forex vs gold)
  - Integrates with strategies via regime_key → parameter profiles

Uses volatility, momentum, BB width, and ADX proxy to classify.
"""

import logging
import math
from typing import Optional

from .indicators import _mean, _std

log = logging.getLogger("trading.regime")


# ═════════════════════════════════════════════════════════════════════════
# REGIME TYPES
# ═════════════════════════════════════════════════════════════════════════

REGIME_TRENDING_UP = "trending_up"
REGIME_TRENDING_DOWN = "trending_down"
REGIME_RANGING = "ranging"
REGIME_VOLATILE = "volatile"
REGIME_CALM = "calm"
REGIME_BREAKOUT = "breakout"

ALL_REGIMES = [
    REGIME_TRENDING_UP, REGIME_TRENDING_DOWN,
    REGIME_RANGING, REGIME_VOLATILE, REGIME_CALM, REGIME_BREAKOUT,
]

# Default detection thresholds — tuned per market type
_MARKET_DEFAULTS = {
    "crypto": {
        "volatility_high": 0.03,   # daily vol above this = volatile
        "volatility_low": 0.008,   # daily vol below this = calm
        "trend_strength": 0.015,    # price change over lookback needed for trending
        "momentum_period": 10,      # bars for momentum calc
        "lookback": 30,             # bars for regime detection
        "bb_width_ratio": 1.5,      # BB width above average = breakout
    },
    "forex": {
        "volatility_high": 0.008,
        "volatility_low": 0.002,
        "trend_strength": 0.005,
        "momentum_period": 14,
        "lookback": 50,
        "bb_width_ratio": 1.3,
    },
    "gold": {
        "volatility_high": 0.015,
        "volatility_low": 0.005,
        "trend_strength": 0.008,
        "momentum_period": 10,
        "lookback": 30,
        "bb_width_ratio": 1.4,
    },
    "futures": {
        "volatility_high": 0.02,
        "volatility_low": 0.005,
        "trend_strength": 0.01,
        "momentum_period": 10,
        "lookback": 30,
        "bb_width_ratio": 1.5,
    },
}


# ═════════════════════════════════════════════════════════════════════════
# REGIME DETECTOR
# ═════════════════════════════════════════════════════════════════════════


class MarketRegimeDetector:
    """Classifies current market regime from price history.

    Usage:
        detector = MarketRegimeDetector()
        regime = detector.detect(prices, market="crypto")
        # → {"regime": "volatile", "confidence": 0.85, "metrics": {...}}
    """

    def __init__(self, overrides: Optional[dict] = None):
        self._thresholds = dict(_MARKET_DEFAULTS)
        if overrides:
            for market, vals in overrides.items():
                if market in self._thresholds:
                    self._thresholds[market].update(vals)
                else:
                    self._thresholds[market] = vals

    def detect(
        self,
        prices: list[float],
        market: str = "crypto",
    ) -> Optional[dict]:
        """Detect the current market regime.

        Args:
            prices: Historical price list (most recent last)
            market: Market type — "crypto", "forex", "gold", "futures"

        Returns:
            dict with: regime, confidence, metrics, market, regime_key
            or None if insufficient data
        """
        cfg = self._thresholds.get(market, self._thresholds["crypto"])
        lookback = cfg["lookback"]

        if not prices or len(prices) < lookback + 5:
            return None

        recent = prices[-lookback:]
        n = len(recent)

        # ── Daily returns + volatility ──────────────────────────────
        returns = [
            (recent[i] - recent[i - 1]) / recent[i - 1]
            for i in range(1, n)
            if recent[i - 1] > 0
        ]
        if len(returns) < 5:
            return None

        daily_vol = _std(returns, ddof=1)
        mean_ret = _mean(returns)

        # ── Trend detection ─────────────────────────────────────────
        first_price = recent[0]
        last_price = recent[-1]
        if first_price > 0:
            trend_pct = (last_price - first_price) / first_price
        else:
            trend_pct = 0.0

        # ── Momentum ────────────────────────────────────────────────
        mom_period = cfg["momentum_period"]
        if n > mom_period:
            mom_start = recent[-mom_period - 1]
            if mom_start > 0:
                momentum = (last_price - mom_start) / mom_start
            else:
                momentum = 0.0
        else:
            momentum = 0.0

        # ── Bollinger Band width (proxy for contraction/expansion) ──
        bb_width = _compute_bb_width(recent)
        avg_bb_width = _compute_avg_bb_width(prices, cfg["lookback"], 20)

        # ── Classify ────────────────────────────────────────────────
        regime = REGIME_RANGING
        confidence = 0.5
        reasons = []
        metrics = {
            "volatility_daily": round(daily_vol, 6),
            "trend_pct": round(trend_pct * 100, 3),
            "momentum_pct": round(momentum * 100, 3),
            "bb_width": round(bb_width, 6) if bb_width else None,
            "mean_return": round(mean_ret, 6),
        }

        # Volatile vs calm
        if daily_vol > cfg["volatility_high"]:
            regime = REGIME_VOLATILE
            confidence = min(1.0, daily_vol / cfg["volatility_high"] / 2)
            reasons.append(f"High volatility: {daily_vol:.4f}")
        elif daily_vol < cfg["volatility_low"]:
            regime = REGIME_CALM
            confidence = 1.0 - daily_vol / cfg["volatility_low"]
            reasons.append(f"Low volatility: {daily_vol:.4f}")

        # Trending (overrides calm if strong enough)
        if abs(trend_pct) > cfg["trend_strength"]:
            if trend_pct > 0:
                regime = REGIME_TRENDING_UP
            else:
                regime = REGIME_TRENDING_DOWN
            confidence = min(1.0, abs(trend_pct) / cfg["trend_strength"])
            reasons.append(f"Trend: {trend_pct*100:.2f}% over {lookback} bars")

        # Breakout (BB expansion)
        if (bb_width is not None and avg_bb_width is not None and
                avg_bb_width > 0 and
                bb_width / avg_bb_width > cfg["bb_width_ratio"]):
            regime = REGIME_BREAKOUT
            confidence = min(1.0, (bb_width / avg_bb_width - 1.0))
            reasons.append(f"BB expansion: {bb_width/avg_bb_width:.2f}x avg")

        # Ranging (default if nothing strong detected)
        if regime in (REGIME_CALM, REGIME_RANGING) and abs(trend_pct) < cfg["trend_strength"] * 0.5:
            regime = REGIME_RANGING
            confidence = 1.0 - abs(trend_pct) / cfg["trend_strength"]
            reasons.append("Sideways price action")

        regime_key = f"{market}_{regime}"

        return {
            "regime": regime,
            "confidence": round(confidence, 3),
            "regime_key": regime_key,
            "market": market,
            "metrics": metrics,
            "reasons": reasons,
            "thresholds_used": {
                "volatility_high": cfg["volatility_high"],
                "volatility_low": cfg["volatility_low"],
                "trend_strength": cfg["trend_strength"],
            },
        }

    def get_regime_key(self, market: str, prices: list[float]) -> str:
        """Shortcut: return just the regime_key string."""
        result = self.detect(prices, market)
        return result["regime_key"] if result else f"{market}_unknown"


# ═════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════


def _compute_bb_width(prices, period: int = 20, std_dev: int = 2) -> Optional[float]:
    """Compute current BB width (upper - lower) / middle."""
    if len(prices) < period:
        return None
    window = prices[-period:]
    mean_val = _mean(window)
    std_val = _std(window, ddof=1)
    if mean_val == 0:
        return None
    return (std_dev * std_val * 2) / mean_val


def _compute_avg_bb_width(
    prices, lookback: int, period: int = 20, std_dev: int = 2
) -> Optional[float]:
    """Compute average BB width over the lookback period."""
    if len(prices) < lookback + period:
        return None
    widths = []
    # Slide a period-sized window across the last `lookback` bars
    for i in range(len(prices) - lookback + period, len(prices) + 1):
        w = _compute_bb_width(prices[i - period : i], period, std_dev)
        if w is not None:
            widths.append(w)
    return _mean(widths) if widths else None
