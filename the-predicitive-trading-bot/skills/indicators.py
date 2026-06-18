"""
PREDICITIVE TRADING BOT · TECHNICAL INDICATORS
================================================
Real technical indicator calculations adapted from QuantMuse FactorCalculator.    Supports:
  - RSI, MACD, SMA, EMA, Bollinger Bands, VWAP, OBV, Stochastic
  - Volatility (annualized), Sharpe ratio, Max drawdown
  - Momentum, Volume momentum, Relative strength
  - Bollinger Band pattern recognition (W-bottom, M-top)
  - RSI pattern recognition (Head-and-Shoulders)

All calculations accept plain lists and return dicts — no pandas dependency
required at the call site. Internally uses numpy for vectorized math when
available, falling back to pure-Python list operations.
"""

import math
import logging
from typing import Optional

log = logging.getLogger("trading.indicators")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    log.info("[indicators] numpy not available — using pure-Python calculations")


# ═════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═════════════════════════════════════════════════════════════════════════


def _to_array(values):
    """Convert a list to numpy array or return as-is."""
    if HAS_NUMPY:
        return np.array(values, dtype=float)
    return list(values)


def _mean(values):
    if HAS_NUMPY:
        return float(np.mean(values))
    return sum(values) / len(values) if values else 0.0


def _std(values, ddof=1):
    if HAS_NUMPY:
        return float(np.std(values, ddof=ddof))
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - ddof)) if len(values) > ddof else 0.0


def _ema(values, period: int) -> list[float]:
    """Exponential moving average."""
    if not values or period <= 0:
        return []
    result = []
    multiplier = 2.0 / (period + 1)
    for i, val in enumerate(values):
        if i == 0:
            result.append(float(val))
        else:
            result.append((float(val) - result[-1]) * multiplier + result[-1])
    return result


def _sma(values, period: int) -> list[float]:
    """Simple moving average."""
    if not values or period <= 0:
        return []
    result = []
    window = []
    for val in values:
        window.append(float(val))
        if len(window) > period:
            window.pop(0)
        result.append(_mean(window) if window else float(val))
    return result


def _rolling_max(values, period: int) -> list[float]:
    """Rolling maximum over `period` values."""
    result = []
    window = []
    for val in values:
        window.append(val)
        if len(window) > period:
            window.pop(0)
        result.append(max(window))
    return result


def _rolling_min(values, period: int) -> list[float]:
    """Rolling minimum."""
    result = []
    window = []
    for val in values:
        window.append(val)
        if len(window) > period:
            window.pop(0)
        result.append(min(window))
    return result


# ═════════════════════════════════════════════════════════════════════════
# INDICATOR CALCULATIONS
# ═════════════════════════════════════════════════════════════════════════


def calc_rsi(prices, period: int = 14) -> Optional[dict]:
    """Relative Strength Index. Returns 0-100 value.

    Adapted from QuantMuse: uses smoothed average gain/loss.
    """
    if not prices or len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = _mean(gains[:period])
    avg_loss = _mean(losses[:period])

    if avg_loss == 0:
        return {"value": 100.0, "signal": "overbought", "overbought": 70, "oversold": 30}

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Smoothed for remaining values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_latest = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_latest = 100.0 - (100.0 / (1.0 + rs))
        if i == len(gains) - 1:
            rsi = rsi_latest

    rsi = round(rsi, 2)
    signal = "overbought" if rsi >= 70 else "oversold" if rsi <= 30 else "neutral"
    return {
        "value": rsi,
        "signal": signal,
        "overbought": 70,
        "oversold": 30,
    }


def calc_macd(prices, fast: int = 12, slow: int = 26, signal_period: int = 9) -> Optional[dict]:
    """MACD (Moving Average Convergence Divergence).

    Adapted from QuantMuse: EMA-based with line, signal, histogram.
    """
    if not prices or len(prices) < slow + signal_period:
        return None

    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)

    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(prices))]
    signal_line = _ema(macd_line, signal_period)
    histogram = [macd_line[i] - signal_line[i] for i in range(len(prices))]

    latest_macd = macd_line[-1]
    latest_signal = signal_line[-1]
    latest_hist = histogram[-1]

    # Determine cross signal
    if latest_macd > latest_signal and latest_hist > 0:
        signal_text = "bullish_cross" if histogram[-2] <= 0 else "bullish"
    elif latest_macd < latest_signal and latest_hist < 0:
        signal_text = "bearish_cross" if histogram[-2] >= 0 else "bearish"
    else:
        signal_text = "neutral"

    return {
        "macd": round(latest_macd, 6),
        "signal": round(latest_signal, 6),
        "histogram": round(latest_hist, 6),
        "signal_text": signal_text,
    }


def calc_moving_averages(prices, periods=None) -> Optional[dict]:
    """SMA and EMA for multiple periods. Returns per-period MA values.

    Adapted from QuantMuse: calculates SMA and distance from price.
    """
    if not prices:
        return None
    if periods is None:
        periods = [9, 21, 50, 200]

    result = {"type": "SMA/EMA", "periods": {}}
    for p in periods:
        if len(prices) >= p:
            sma_vals = _sma(prices, p)
            ema_vals = _ema(prices, p)
            latest_price = prices[-1]
            sma_val = sma_vals[-1]
            ema_val = ema_vals[-1]
            distance_pct = round((latest_price - sma_val) / sma_val * 100, 2) if sma_val else 0
            result["periods"][str(p)] = {
                "sma": round(sma_val, 6),
                "ema": round(ema_val, 6),
                "distance_pct": distance_pct,
            }
        else:
            result["periods"][str(p)] = "insufficient_data"
    return result


def calc_bollinger_bands(prices, period: int = 20, std_dev: int = 2) -> Optional[dict]:
    """Bollinger Bands: SMA ± k * stddev.

    Adapted from QuantMuse.
    """
    if not prices or len(prices) < period:
        return None

    sma_vals = _sma(prices, period)
    latest_price = prices[-1]
    middle = sma_vals[-1]

    # Rolling standard deviation
    std_vals = []
    for i in range(len(prices)):
        if i < period - 1:
            std_vals.append(0.0)
        else:
            window = prices[i - period + 1 : i + 1]
            std_vals.append(_std(window))

    std_val = std_vals[-1]
    upper = middle + std_dev * std_val
    lower = middle - std_dev * std_val

    # Position: where is price relative to bands? (0=lower, 0.5=middle, 1=upper)
    bandwidth = upper - lower
    position = round((latest_price - lower) / bandwidth, 3) if bandwidth > 0 else 0.5

    return {
        "upper": round(upper, 6),
        "middle": round(middle, 6),
        "lower": round(lower, 6),
        "bandwidth": round(bandwidth, 6),
        "position": position,
    }


def calc_vwap(prices, volumes) -> Optional[dict]:
    """Volume-Weighted Average Price.

    Adapted from QuantMuse: cumulative VWAP.
    """
    if not prices or not volumes or len(prices) != len(volumes):
        return None

    total_pv = sum(p * v for p, v in zip(prices, volumes))
    total_vol = sum(volumes)
    if total_vol == 0:
        return None

    vwap = total_pv / total_vol
    latest_price = prices[-1]
    position = "above" if latest_price > vwap else "below" if latest_price < vwap else "at"

    return {
        "value": round(vwap, 6),
        "position": position,
    }


def calc_obv(prices, volumes) -> Optional[dict]:
    """On-Balance Volume.

    Adapted from QuantMuse: cumulative volume flow.
    """
    if not prices or not volumes or len(prices) != len(volumes) or len(prices) < 2:
        return None

    obv = 0.0
    obv_values = [0.0]
    for i in range(1, len(prices)):
        if prices[i] > prices[i - 1]:
            obv += volumes[i]
        elif prices[i] < prices[i - 1]:
            obv -= volumes[i]
        obv_values.append(obv)

    # Determine trend from last few OBV values
    recent = obv_values[-5:] if len(obv_values) >= 5 else obv_values
    trend = "upward" if recent[-1] > recent[0] else "downward" if recent[-1] < recent[0] else "neutral"

    return {
        "value": round(obv, 6),
        "trend": trend,
    }


def calc_stochastic(prices, highs=None, lows=None, k_period: int = 14, d_period: int = 3) -> Optional[dict]:
    """Stochastic Oscillator (%K, %D).

    Uses price as proxy for both high and low if highs/lows not provided.
    """
    if not prices or len(prices) < k_period:
        return None

    if highs is None:
        highs = prices
    if lows is None:
        lows = prices

    # %K = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
    k_values = []
    for i in range(len(prices)):
        if i < k_period - 1:
            k_values.append(50.0)
        else:
            highest = max(highs[i - k_period + 1 : i + 1])
            lowest = min(lows[i - k_period + 1 : i + 1])
            if highest == lowest:
                k_values.append(50.0)
            else:
                k_values.append((prices[i] - lowest) / (highest - lowest) * 100)

    k = k_values[-1]
    d_vals = _sma(k_values, d_period)
    d = d_vals[-1] if d_vals else k

    signal = "overbought" if k >= 80 else "oversold" if k <= 20 else "neutral"

    return {
        "k": round(k, 2),
        "d": round(d, 2),
        "signal": signal,
    }


def calc_volatility(prices, annualize: bool = True) -> Optional[dict]:
    """Price volatility (annualized if annualize=True, assuming daily data).

    Adapted from QuantMuse: stddev of daily returns.
    """
    if not prices or len(prices) < 2:
        return None

    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    daily_vol = _std(returns, ddof=1)
    annual_vol = daily_vol * math.sqrt(252) if annualize else daily_vol

    return {
        "daily": round(daily_vol, 6),
        "annualized": round(annual_vol, 6),
    }


def calc_sharpe(prices, risk_free_rate: float = 0.02) -> Optional[dict]:
    """Sharpe ratio (annualized, assuming daily data).

    Adapted from QuantMuse.
    """
    if not prices or len(prices) < 2:
        return None

    returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
    mean_return = _mean(returns)
    vol = _std(returns, ddof=1)

    if vol == 0:
        return {"sharpe": 0.0, "note": "zero volatility"}

    # Annualize
    annual_return = mean_return * 252
    annual_vol = vol * math.sqrt(252)
    daily_rfr = risk_free_rate / 252

    sharpe = (mean_return - daily_rfr) / vol * math.sqrt(252)

    return {
        "sharpe": round(sharpe, 4),
        "annualized_return": round(annual_return, 4),
        "annualized_volatility": round(annual_vol, 4),
    }


def calc_max_drawdown(prices) -> Optional[dict]:
    """Maximum drawdown from peak.

    Adapted from QuantMuse: rolling max approach.
    """
    if not prices or len(prices) < 2:
        return None

    peak = prices[0]
    max_dd = 0.0
    max_dd_start = 0
    max_dd_end = 0
    current_dd_start = 0

    for i, p in enumerate(prices):
        if p > peak:
            peak = p
            current_dd_start = i
        dd = (peak - p) / peak
        if dd > max_dd:
            max_dd = dd
            max_dd_start = current_dd_start
            max_dd_end = i

    return {
        "max_drawdown_pct": round(max_dd * 100, 2),
        "peak_index": max_dd_start,
        "trough_index": max_dd_end,
    }


def calc_momentum(prices, periods=None) -> Optional[dict]:
    """Price momentum over multiple lookback periods.

    Adapted from QuantMuse: returns percentage change.
    """
    if not prices or len(prices) < 2:
        return None
    if periods is None:
        periods = [5, 10, 20, 60]

    result = {}
    latest = prices[-1]
    for period in periods:
        if len(prices) > period:
            past = prices[-period - 1]
            if past > 0:
                pct = (latest - past) / past * 100
                result[f"momentum_{period}d"] = round(pct, 2)
            else:
                result[f"momentum_{period}d"] = None
        else:
            result[f"momentum_{period}d"] = "insufficient_data"

    # Acceleration: difference between short and longer momentum
    if "momentum_5d" in result and "momentum_20d" in result:
        m5 = result["momentum_5d"]
        m20 = result["momentum_20d"]
        if isinstance(m5, (int, float)) and isinstance(m20, (int, float)):
            result["momentum_acceleration"] = round(m5 - m20, 2)

    return result


def calc_relative_strength(prices, market_prices, period: int = 20) -> Optional[float]:
    """Stock return vs market return over a period.

    Adapted from QuantMuse.
    """
    if not prices or not market_prices or len(prices) <= period or len(market_prices) <= period:
        return None

    stock_return = (prices[-1] - prices[-period - 1]) / prices[-period - 1] * 100
    market_return = (market_prices[-1] - market_prices[-period - 1]) / market_prices[-period - 1] * 100

    return round(stock_return - market_return, 2)




# ═════════════════════════════════════════════════════════════════════════
# PATTERN RECOGNITION
# ═════════════════════════════════════════════════════════════════════════
# Adapted from je-suis-tm/quant-trading Bollinger Bands + RSI pattern
# recognition backtests. Reimplemented without pandas.


def _bb_series(prices, period: int = 20, std_dev: int = 2):
    """Compute full Bollinger Band time series (not just latest values).

    Returns tuple of (upper, mid, lower, std) lists, each same length as prices.
    First `period - 1` values are None (insufficient data).
    """
    n = len(prices)
    upper = [None] * n
    mid = [None] * n
    lower = [None] * n
    stds = [None] * n

    for i in range(period - 1, n):
        window = prices[i - period + 1 : i + 1]
        mean_val = _mean(window)
        std_val = _std(window, ddof=1)
        mid[i] = mean_val
        upper[i] = mean_val + std_dev * std_val
        lower[i] = mean_val - std_dev * std_val
        stds[i] = std_val

    return upper, mid, lower, stds


def detect_bollinger_band_patterns(
    prices,
    period: int = 20,
    std_dev: int = 2,
    lookback: int = 75,
    alpha: float = 0.0001,
    beta: float = 0.0001,
) -> Optional[dict]:
    """Detect Bollinger Band W-bottom (double bottom) patterns.

    Adapted from je-suis-tm/quant-trading signal_generation function.

    Identifies the 5-node W-bottom pattern:
      l → k → j → m → i  (left to right)
      - l: far-left helper node (mid band < price, for visualization)
      - k: first bottom near lower band
      - j: middle node near mid band, mid band near upper_band[i]
      - m: second bottom between j and i, near lower band, higher than k
      - i: current bar, price above upper band

    The M-top is the reverse (price below lower band at i).

    Args:
        prices: list of price values (most recent last)
        period: BB period (default 20)
        std_dev: BB standard deviation multiplier (default 2)
        lookback: max bars to look back for pattern (default 75)
        alpha: price-to-band proximity threshold (default 0.0001)
        beta: bandwidth contraction threshold for exits (default 0.0001)

    Returns:
        dict with:
          - patterns: list of detected pattern dicts, each with:
              - type: "w_bottom" or "m_top"
              - signal: "buy" or "sell"
              - nodes: {l, k, j, m, i} with indices
              - bar_index: detection bar (i)
              - price_at_detection: price at bar i
          - latest_signal: "buy", "sell", or None
          - confidence: 0.0-1.0 (based on pattern quality)
    """
    if not prices or len(prices) < period + lookback:
        return None

    n = len(prices)
    upper, mid, lower, stds = _bb_series(prices, period, std_dev)

    patterns = []
    in_position = False
    confidence = 0.0

    for i in range(lookback, n):
        if upper[i] is None:
            continue

        moveon = False
        threshold = 0.0

        # ── W-Bottom (price above upper band) ──────────────────────
        if prices[i] > upper[i] and not in_position:

            # Find node j: price near mid band, mid band near upper_band[i]
            node_j = -1
            for j in range(i, max(i - lookback, -1), -1):
                if mid[j] is None:
                    continue
                if (abs(mid[j] - prices[j]) < alpha and
                        abs(mid[j] - upper[i]) < alpha):
                    node_j = j
                    moveon = True
                    break

            if moveon:
                moveon = False
                node_k = -1
                for k in range(node_j, max(node_j - lookback, -1), -1):
                    if lower[k] is None:
                        continue
                    if abs(lower[k] - prices[k]) < alpha:
                        threshold = prices[k]
                        node_k = k
                        moveon = True
                        break

            if moveon:
                moveon = False
                node_l = -1
                for l in range(node_k, max(node_k - lookback, -1), -1):
                    if mid[l] is None:
                        continue
                    if mid[l] < prices[l]:
                        node_l = l
                        moveon = True
                        break

            if moveon:
                moveon = False
                node_m = -1
                for m in range(i - 1, node_j, -1):
                    if lower[m] is None:
                        continue
                    if (prices[m] - lower[m] < alpha and
                            prices[m] > lower[m] and
                            prices[m] < threshold):
                        node_m = m
                        patterns.append({
                            "type": "w_bottom",
                            "signal": "buy",
                            "nodes": {"l": node_l, "k": node_k, "j": node_j,
                                      "m": node_m, "i": i},
                            "bar_index": i,
                            "price_at_detection": round(prices[i], 6),
                        })
                        in_position = True
                        if threshold > 0:
                            confidence = round(
                                min(1.0, (prices[m] - threshold) / threshold / alpha),
                                3,
                            )
                        moveon = True
                        break

        # ── M-Top (price below lower band) ─────────────────────────
        elif prices[i] < lower[i] and not in_position:

            # Find node j: price near mid band, mid band near lower_band[i]
            node_j = -1
            for j in range(i, max(i - lookback, -1), -1):
                if mid[j] is None:
                    continue
                if (abs(mid[j] - prices[j]) < alpha and
                        abs(mid[j] - lower[i]) < alpha):
                    node_j = j
                    moveon = True
                    break

            if moveon:
                moveon = False
                node_k = -1
                for k in range(node_j, max(node_j - lookback, -1), -1):
                    if upper[k] is None:
                        continue
                    if abs(upper[k] - prices[k]) < alpha:
                        threshold = prices[k]
                        node_k = k
                        moveon = True
                        break

            if moveon:
                moveon = False
                node_l = -1
                for l in range(node_k, max(node_k - lookback, -1), -1):
                    if mid[l] is None:
                        continue
                    if mid[l] > prices[l]:
                        node_l = l
                        moveon = True
                        break

            if moveon:
                moveon = False
                node_m = -1
                for m in range(i - 1, node_j, -1):
                    if upper[m] is None:
                        continue
                    if (upper[m] - prices[m] < alpha and
                            prices[m] < upper[m] and
                            prices[m] > threshold):
                        node_m = m
                        patterns.append({
                            "type": "m_top",
                            "signal": "sell",
                            "nodes": {"l": node_l, "k": node_k, "j": node_j,
                                      "m": node_m, "i": i},
                            "bar_index": i,
                            "price_at_detection": round(prices[i], 6),
                        })
                        in_position = True
                        if threshold > 0:
                            confidence = round(
                                min(1.0, (threshold - prices[m]) / threshold / alpha),
                                3,
                            )
                        moveon = True
                        break

        # Exit on band contraction (std falls below beta) while in position
        if in_position and stds[i] is not None and stds[i] < beta and not moveon:
            patterns.append({
                "type": "exit_contraction",
                "signal": "sell" if patterns and patterns[-1]["signal"] == "buy" else "buy",
                "nodes": {},
                "bar_index": i,
                "price_at_detection": round(prices[i], 6),
            })
            in_position = False
            confidence = 0.0

    # Latest signal
    latest_signal = None
    if patterns:
        latest = patterns[-1]
        latest_signal = latest["signal"]

    return {
        "patterns": patterns,
        "patterns_count": len(patterns),
        "latest_signal": latest_signal,
        "confidence": confidence,
        "last_detection_bar": patterns[-1]["bar_index"] if patterns else None,
    }


def detect_rsi_head_shoulders(
    prices,
    rsi_period: int = 14,
    lookback: int = 25,
    delta: float = 3.0,
    head_mult: float = 1.1,
    shoulder_mult: float = 1.1,
) -> Optional[dict]:
    """Detect Head-and-Shoulders pattern on RSI values.

    Adapted from je-suis-tm/quant-trading RSI Pattern Recognition.

    Identifies the 7-node H&S pattern on RSI:
      m → n → l → j → k → o → i  (left to right)
      - m: left shoulder base (near RSI bottom)
      - n: left shoulder peak (between m and l)
      - l: center split (near RSI bottom, between shoulders and head)
      - j: head peak (maximum RSI, significantly above i)
      - k: right shoulder base (near RSI bottom)
      - o: right shoulder peak (near n's RSI level)
      - i: current bar (right shoulder completes)

    Detected pattern signals a short (bearish reversal).

    Args:
        prices: list of price values (most recent last)
        rsi_period: RSI calculation period (default 14)
        lookback: max bars to look back for pattern (default 25)
        delta: significance threshold (default 0.2)
        head_mult: head significance multiplier (default 1.1)
        shoulder_mult: shoulder significance multiplier (default 1.1)

    Returns:
        dict with:
          - patterns: list of detected pattern dicts, each with:
              - type: "head_and_shoulders"
              - signal: "sell" (short)
              - nodes: {m, n, l, j, k, o, i} with indices + RSI values
              - bar_index: detection bar (i)
              - rsi_at_detection: RSI value at bar i
          - latest_signal: "sell" or None
          - confidence: 0.0-1.0
    """
    if not prices or len(prices) < rsi_period + lookback + 5:
        return None

    n = len(prices)

    # Compute RSI series (all values, not just latest)
    rsi_values = _rsi_series(prices, rsi_period)
    if rsi_values is None or len(rsi_values) < lookback + 5:
        return None

    patterns = []

    for i in range(lookback, n):
        if rsi_values[i] is None:
            continue

        # Find head node j: max RSI in [i-lookback, i], must be significantly
        # above RSI at i
        lo = max(0, i - lookback)
        hi = i
        head_idx = lo
        for t in range(lo + 1, hi + 1):
            if rsi_values[t] is not None and rsi_values[head_idx] is not None:
                if rsi_values[t] > rsi_values[head_idx]:
                    head_idx = t

        if rsi_values[head_idx] is None or rsi_values[i] is None:
            continue
        if abs(rsi_values[head_idx] - rsi_values[i]) <= head_mult * delta:
            continue

        node_j = head_idx

        # Bottom reference: RSI at i (rightmost point)
        bottom_rsi = rsi_values[i]

        # Find node k: right shoulder base, between j and i, near bottom
        node_k = -1
        for k in range(i - 1, node_j, -1):
            if rsi_values[k] is None:
                continue
            if abs(rsi_values[k] - bottom_rsi) < delta:
                node_k = k
                break
        if node_k < 0:
            continue

        # Find node l: center split, left of j, near bottom
        node_l = -1
        for l in range(node_j - 1, lo, -1):
            if rsi_values[l] is None:
                continue
            if abs(rsi_values[l] - bottom_rsi) < delta:
                node_l = l
                break
        if node_l < 0:
            continue

        # Find node m: left shoulder base, left of l, near bottom
        node_m = -1
        lo2 = max(0, i - lookback)
        for m in range(node_l - 1, lo2, -1):
            if rsi_values[m] is None:
                continue
            if abs(rsi_values[m] - bottom_rsi) < delta:
                node_m = m
                break
        if node_m < 0:
            continue

        # Find node n: left shoulder peak between m and l
        node_n = node_m
        for t in range(node_m + 1, node_l + 1):
            if rsi_values[t] is not None and rsi_values[node_n] is not None:
                if rsi_values[t] > rsi_values[node_n]:
                    node_n = t

        if rsi_values[node_n] is None or rsi_values[node_m] is None or rsi_values[node_j] is None:
            continue
        if (abs(rsi_values[node_n] - bottom_rsi) <= shoulder_mult * delta):
            continue
        if (abs(rsi_values[node_n] - rsi_values[node_j]) <= shoulder_mult * delta):
            continue

        # Find node o: right shoulder peak between k and i, near n's level
        node_o = -1
        for o in range(i - 1, node_k, -1):
            if rsi_values[o] is None or rsi_values[node_n] is None:
                continue
            if abs(rsi_values[o] - rsi_values[node_n]) < delta:
                node_o = o
                break
        if node_o < 0:
            continue

        # Pattern confirmed
        patterns.append({
            "type": "head_and_shoulders",
            "signal": "sell",
            "nodes": {
                "m": {"index": node_m, "rsi": round(rsi_values[node_m], 2)},
                "n": {"index": node_n, "rsi": round(rsi_values[node_n], 2)},
                "l": {"index": node_l, "rsi": round(rsi_values[node_l], 2)},
                "j": {"index": node_j, "rsi": round(rsi_values[node_j], 2)},
                "k": {"index": node_k, "rsi": round(rsi_values[node_k], 2)},
                "o": {"index": node_o, "rsi": round(rsi_values[node_o], 2)},
                "i": {"index": i, "rsi": round(rsi_values[i], 2)},
            },
            "bar_index": i,
            "rsi_at_detection": round(rsi_values[i], 2),
            "price_at_detection": round(prices[i], 6) if i < len(prices) else None,
        })

    # Confidence: based on RSI distance from overbought/oversold at detection
    confidence = 0.0
    if patterns and rsi_values[patterns[-1]["bar_index"]] is not None:
        rsi = rsi_values[patterns[-1]["bar_index"]]
        # Higher confidence when RSI is further from center (50)
        confidence = round(min(1.0, abs(rsi - 50) / 30), 3)

    latest_signal = patterns[-1]["signal"] if patterns else None

    return {
        "patterns": patterns,
        "patterns_count": len(patterns),
        "latest_signal": latest_signal,
        "confidence": confidence,
        "last_detection_bar": patterns[-1]["bar_index"] if patterns else None,
    }


def _rsi_series(prices, period: int = 14) -> Optional[list]:
    """Compute RSI for each bar (returns list of floats/None).

    First `period` values are None (insufficient data).
    """
    if not prices or len(prices) < period + 1:
        return None

    n = len(prices)
    rsi_vals = [None] * n

    deltas = [prices[i] - prices[i - 1] for i in range(1, n)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = _mean(gains[:period])
    avg_loss = _mean(losses[:period])

    if avg_loss == 0:
        rsi_val = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_val = 100.0 - (100.0 / (1.0 + rs))
    rsi_vals[period] = rsi_val

    # Smoothed RSI for remaining bars (matches calc_rsi indexing)
    for i in range(period, n - 1):
        idx = i + 1  # rsi_vals index
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_vals[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_vals[idx] = 100.0 - (100.0 / (1.0 + rs))

    return rsi_vals


# ═════════════════════════════════════════════════════════════════════════
# BULK CALCULATION
# ═════════════════════════════════════════════════════════════════════════


# ── No-data stubs (backward-compatible fallbacks when prices not provided) ──

_NO_DATA_RSI = {"value": 50, "signal": "neutral", "overbought": 70, "oversold": 30}
_NO_DATA_MACD = {"macd": 0, "signal": 0, "histogram": 0, "signal_text": "neutral"}
_NO_DATA_MA = {"type": "SMA/EMA", "periods": {}}
_NO_DATA_BB = {"upper": 0, "middle": 0, "lower": 0, "bandwidth": 0, "position": 0}
_NO_DATA_VWAP = {"value": 0, "position": "no_data"}
_NO_DATA_OBV = {"value": 0, "trend": "neutral"}
_NO_DATA_STOCHASTIC = {"k": 50, "d": 50, "signal": "neutral"}


def calculate_indicators(
    prices,
    volumes=None,
    indicators=None,
    market_prices=None,
) -> dict:
    """Calculate multiple indicators at once.

    Args:
        prices: list of float prices (most recent last). If None/empty, returns
                stub dicts with consistent shapes for backward compatibility.
        volumes: optional list of float volumes (same length as prices)
        indicators: list of indicator names, e.g. ["RSI", "MACD", "MA", "BB",
                    "VWAP", "OBV", "STOCHASTIC", "BB_PATTERN", "RSI_PATTERN"]
        market_prices: optional list of market/index prices for relative strength

    Returns:
        dict mapping indicator name → result dict (stub if no data, None if calc failed)
    """
    if indicators is None:
        indicators = ["RSI", "MACD", "MA"]

    has_prices = bool(prices) and len(prices) > 0
    has_volumes = bool(volumes) and len(volumes) > 0

    results = {}

    for ind in indicators:
        ind_upper = ind.upper()

        if ind_upper == "RSI":
            results["RSI"] = calc_rsi(prices) if has_prices else _NO_DATA_RSI

        elif ind_upper == "MACD":
            results["MACD"] = calc_macd(prices) if has_prices else _NO_DATA_MACD

        elif ind_upper == "MA":
            results["MA"] = calc_moving_averages(prices) if has_prices else _NO_DATA_MA

        elif ind_upper == "BB":
            results["BB"] = calc_bollinger_bands(prices) if has_prices else _NO_DATA_BB

        elif ind_upper == "VWAP":
            if has_prices and has_volumes:
                results["VWAP"] = calc_vwap(prices, volumes)
            else:
                results["VWAP"] = _NO_DATA_VWAP

        elif ind_upper == "OBV":
            if has_prices and has_volumes:
                results["OBV"] = calc_obv(prices, volumes)
            else:
                results["OBV"] = _NO_DATA_OBV

        elif ind_upper == "STOCHASTIC":
            results["STOCHASTIC"] = calc_stochastic(prices) if has_prices else _NO_DATA_STOCHASTIC

        elif ind_upper == "VOLATILITY":
            results["volatility"] = calc_volatility(prices) if has_prices else {"daily": None, "annualized": None}

        elif ind_upper == "SHARPE":
            results["sharpe"] = calc_sharpe(prices) if has_prices else {"sharpe": None}

        elif ind_upper == "MAX_DRAWDOWN":
            results["max_drawdown"] = calc_max_drawdown(prices) if has_prices else {"max_drawdown_pct": None}

        elif ind_upper == "MOMENTUM":
            results["momentum"] = calc_momentum(prices) if has_prices else {}

        elif ind_upper == "RELATIVE_STRENGTH":
            if has_prices and market_prices:
                results["relative_strength"] = calc_relative_strength(prices, market_prices)
            else:
                results["relative_strength"] = None

        elif ind_upper in ("BB_PATTERN", "BB_PATTERNS"):
            results["bb_pattern"] = detect_bollinger_band_patterns(prices) if has_prices else None

        elif ind_upper in ("RSI_PATTERN", "RSI_PATTERNS"):
            results["rsi_pattern"] = detect_rsi_head_shoulders(prices) if has_prices else None

        else:
            results[ind] = {"error": f"unknown indicator: {ind}"}

    return results
