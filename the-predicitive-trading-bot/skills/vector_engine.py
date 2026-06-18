"""
PREDICITIVE TRADING BOT · VECTOR ENGINE
========================================
Batch/vectorized trading signal engine for high-throughput scanning.

Accepts a 2D price matrix [N_symbols x T_timepoints] and computes all
indicators + strategy signals in one synchronous numpy pass — no async,
no Python for-loops in the hot path.

Architecture:
  - calc_*_2d() functions: pure numpy vectorized indicator calculations
  - VectorEngine: orchestrator that runs all strategies across all symbols
    in batch, returning dicts of numpy arrays for zero-allocation downstream
    consumption.

Adapted from QuantMuse for batch execution.

Performance target: 10,000+ symbols in < 5 ms (warm numpy).
"""

import logging
import time
from typing import Any, Optional

log = logging.getLogger("trading.vector_engine")

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    log.warning("[vector_engine] numpy not available — batch engine disabled")


# ═════════════════════════════════════════════════════════════════════════
# VECTORIZED INDICATOR CALCULATIONS (2D)
# ═════════════════════════════════════════════════════════════════════════


def _ema_2d(prices: "np.ndarray", period: int) -> "np.ndarray":
    """2D exponential moving average along axis=1.

    Args:
        prices: shape [N, T] — N symbols, T timepoints
        period: EMA smoothing period

    Returns:
        shape [N, T] EMA values. First `period-1` columns are NaN.
    """
    alpha = 2.0 / (period + 1)
    n, t = prices.shape
    result = np.full((n, t), np.nan, dtype=np.float64)

    # Seed: SMA of first `period` values
    if t >= period:
        result[:, period - 1] = np.mean(prices[:, :period], axis=1)

    # Recursive EMA sweep (vectorized across symbols)
    for i in range(period, t):
        result[:, i] = alpha * prices[:, i] + (1 - alpha) * result[:, i - 1]

    return result


def _rolling_std_2d(prices: "np.ndarray", period: int) -> "np.ndarray":
    """2D rolling standard deviation along axis=1.

    Args:
        prices: shape [N, T]
        period: window size

    Returns:
        shape [N, T] rolling std. First `period-1` columns are NaN.
    """
    n, t = prices.shape
    result = np.full((n, t), np.nan, dtype=np.float64)
    if t < period:
        return result

    # Ensure C-contiguous before stride tricks (safety guard)
    prices = np.ascontiguousarray(prices)

    # Use sliding window via stride tricks for speed
    # shape = [N, T-period+1, period]
    shape = (n, t - period + 1, period)
    strides = (prices.strides[0], prices.strides[1], prices.strides[1])
    windows = np.lib.stride_tricks.as_strided(prices, shape=shape, strides=strides)

    stds = np.std(windows, ddof=1, axis=2)  # [N, T-period+1]
    result[:, period - 1:] = stds
    return result


def _rolling_mean_2d(prices: "np.ndarray", period: int) -> "np.ndarray":
    """2D rolling mean along axis=1."""
    n, t = prices.shape
    result = np.full((n, t), np.nan, dtype=np.float64)
    if t < period:
        return result

    # Ensure C-contiguous before stride tricks (safety guard)
    prices = np.ascontiguousarray(prices)

    shape = (n, t - period + 1, period)
    strides = (prices.strides[0], prices.strides[1], prices.strides[1])
    windows = np.lib.stride_tricks.as_strided(prices, shape=shape, strides=strides)

    means = np.mean(windows, axis=2)  # [N, T-period+1]
    result[:, period - 1:] = means
    return result


def calc_rsi_2d(prices: "np.ndarray", period: int = 14) -> "np.ndarray":
    """2D vectorized RSI for N symbols.

    Args:
        prices: shape [N, T]
        period: RSI period (default 14)

    Returns:
        shape [N] — latest RSI value per symbol (0-100).
        NaN for symbols with insufficient data.
    """
    n, t = prices.shape
    if t < period + 1:
        return np.full(n, np.nan, dtype=np.float64)

    deltas = np.diff(prices, axis=1)  # [N, T-1]
    gains = np.where(deltas > 0, deltas, 0.0)  # [N, T-1]
    losses = np.where(deltas < 0, -deltas, 0.0)  # [N, T-1]

    # Initial average gain/loss over first `period` deltas
    avg_gain = np.mean(gains[:, :period], axis=1)  # [N]
    avg_loss = np.mean(losses[:, :period], axis=1)  # [N]

    # Smoothed RSI via Wilder's method (vectorized sweep)
    for i in range(period, t - 1):
        avg_gain = (avg_gain * (period - 1) + gains[:, i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[:, i]) / period

    # Final RSI
    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.inf),
                   where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Clamp
    rsi = np.clip(rsi, 0.0, 100.0)
    # Where avg_loss was 0, RSI = 100
    rsi[avg_loss == 0] = 100.0
    return rsi


def calc_macd_2d(
    prices: "np.ndarray",
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, "np.ndarray"]:
    """2D vectorized MACD for N symbols.

    Args:
        prices: shape [N, T]

    Returns:
        dict with keys 'macd', 'signal', 'histogram', 'signal_text' —
        each value is shape [N] (latest value per symbol).
    """
    n, t = prices.shape
    empty = np.full(n, np.nan, dtype=np.float64)
    empty_str = np.full(n, "no_data", dtype=object)

    if t < slow + signal_period:
        return {
            "macd": empty.copy(),
            "signal": empty.copy(),
            "histogram": empty.copy(),
            "signal_text": empty_str.copy(),
        }

    ema_fast = _ema_2d(prices, fast)  # [N, T]
    ema_slow = _ema_2d(prices, slow)  # [N, T]
    macd_line = ema_fast - ema_slow  # [N, T]

    # Signal line: EMA of macd_line
    signal_line = _ema_2d(_fill_nan_2d(macd_line), signal_period)

    # Histogram
    histogram = macd_line - signal_line

    # Latest values
    latest_macd = macd_line[:, -1]  # [N]
    latest_signal = signal_line[:, -1]  # [N]
    latest_hist = histogram[:, -1]  # [N]

    # Signal text: vectorized comparison
    signal_text = np.full(n, "neutral", dtype=object)
    signal_text[(latest_macd > latest_signal) & (latest_hist > 0)] = "bullish"
    signal_text[(latest_macd < latest_signal) & (latest_hist < 0)] = "bearish"

    # Cross detection (requires t-2, vectorized)
    if t >= 2:
        prev_hist = histogram[:, -2]
        bull_cross = (latest_macd > latest_signal) & (prev_hist <= 0) & np.isfinite(prev_hist)
        bear_cross = (latest_macd < latest_signal) & (prev_hist >= 0) & np.isfinite(prev_hist)
        signal_text[bull_cross] = "bullish_cross"
        signal_text[bear_cross] = "bearish_cross"

    return {
        "macd": latest_macd,
        "signal": latest_signal,
        "histogram": latest_hist,
        "signal_text": signal_text,
    }


def _fill_nan_2d(arr: "np.ndarray") -> "np.ndarray":
    """Forward-fill NaN values along axis=1 (for EMA seeding)."""
    n, t = arr.shape
    result = arr.copy()
    for i in range(1, t):
        mask = np.isnan(result[:, i])
        result[mask, i] = result[mask, i - 1]
    return result


def calc_ma_2d(
    prices: "np.ndarray",
    periods: tuple[int, ...] = (9, 21, 50, 200),
) -> dict[str, "np.ndarray"]:
    """2D vectorized moving averages for N symbols.

    Args:
        prices: shape [N, T]
        periods: SMA periods to compute

    Returns:
        dict keyed by f"sma_{period}" → shape [N] latest SMA per symbol.
    """
    n, t = prices.shape
    result = {}

    for period in periods:
        key = f"sma_{period}"
        if t < period:
            result[key] = np.full(n, np.nan, dtype=np.float64)
        else:
            sma = _rolling_mean_2d(prices, period)
            result[key] = sma[:, -1]

    return result


def calc_bb_2d(
    prices: "np.ndarray",
    period: int = 20,
    std_dev: int = 2,
) -> dict[str, "np.ndarray"]:
    """2D vectorized Bollinger Bands for N symbols.

    Args:
        prices: shape [N, T]

    Returns:
        dict with 'middle', 'upper', 'lower', 'bandwidth' — each shape [N].
    """
    n, t = prices.shape
    empty = np.full(n, np.nan, dtype=np.float64)

    if t < period:
        return {"middle": empty.copy(), "upper": empty.copy(),
                "lower": empty.copy(), "bandwidth": empty.copy()}

    middle = _rolling_mean_2d(prices, period)[:, -1]  # [N]
    stds = _rolling_std_2d(prices, period)[:, -1]  # [N]

    upper = middle + std_dev * stds
    lower = middle - std_dev * stds
    bandwidth = upper - lower

    return {
        "middle": middle,
        "upper": upper,
        "lower": lower,
        "bandwidth": bandwidth,
    }


def calc_volatility_2d(prices: "np.ndarray") -> "np.ndarray":
    """2D annualized volatility per symbol.

    Args:
        prices: shape [N, T]

    Returns:
        shape [N] annualized volatility.
    """
    n, t = prices.shape
    if t < 2:
        return np.full(n, np.nan, dtype=np.float64)

    returns = np.diff(prices, axis=1) / prices[:, :-1]  # [N, T-1]
    daily_vol = np.std(returns, ddof=1, axis=1)  # [N]
    return daily_vol * np.sqrt(252)


def calc_sharpe_2d(prices: "np.ndarray", risk_free_rate: float = 0.02) -> "np.ndarray":
    """2D Sharpe ratio per symbol.

    Args:
        prices: shape [N, T]

    Returns:
        shape [N] annualized Sharpe ratio.
    """
    n, t = prices.shape
    if t < 2:
        return np.full(n, np.nan, dtype=np.float64)

    returns = np.diff(prices, axis=1) / prices[:, :-1]  # [N, T-1]
    mean_ret = np.mean(returns, axis=1)  # [N]
    vol = np.std(returns, ddof=1, axis=1)  # [N]

    daily_rfr = risk_free_rate / 252
    sharpe = np.where(vol > 0, (mean_ret - daily_rfr) / vol * np.sqrt(252), 0.0)
    return sharpe


def calc_momentum_2d(prices: "np.ndarray", periods: tuple[int, ...] = (5, 10, 20, 60)) -> dict[str, "np.ndarray"]:
    """2D price momentum per symbol.

    Args:
        prices: shape [N, T]
        periods: lookback periods

    Returns:
        dict keyed by f"momentum_{p}d" → shape [N] percentage change.
    """
    n, t = prices.shape
    result = {}
    latest = prices[:, -1]  # [N]

    for period in periods:
        key = f"momentum_{period}d"
        if t > period:
            past = prices[:, -period - 1]  # [N]
            with np.errstate(divide="ignore", invalid="ignore"):
                pct = (latest - past) / past * 100.0
            pct[~np.isfinite(pct)] = np.nan
            result[key] = pct
        else:
            result[key] = np.full(n, np.nan, dtype=np.float64)

    return result


# ═════════════════════════════════════════════════════════════════════════
# BATCH ORCHESTRATOR
# ═════════════════════════════════════════════════════════════════════════


class VectorEngine:
    """High-throughput batch signal generator.

    Takes a dict of symbol→price_list, pads to a 2D matrix, computes all
    indicators vectorized, then runs every strategy in batch.

    Usage::

        engine = VectorEngine(strategies=[momentum, mean_rev, breakout])
        signals = engine.run({
            "BTC/USD": [42000.0, 42100.0, ...],
            "ETH/USD": [2200.0, 2210.0, ...],
        })
        # signals["strategy.momentum"]["action"] → numpy array
    """

    def __init__(
        self,
        strategies: Optional[list] = None,
        registry: Optional[Any] = None,
    ):
        """Initialize the vector engine.

        Args:
            strategies: list of StrategyBase instances (takes precedence)
            registry: StrategyRegistry to pull strategies from (fallback)
        """
        if not HAS_NUMPY:
            raise RuntimeError(
                "VectorEngine requires numpy. Install with: pip install numpy"
            )
        self._strategies: list = list(strategies) if strategies else []
        if registry is not None and not self._strategies:
            # Pull all registered strategy instances/classes from registry
            for name in registry.list_all():
                instance = registry.get_strategy(name)
                if instance is None:
                    instance = registry.create_strategy(name)
                if instance is not None:
                    self._strategies.append(instance)
        self._last_benchmark_ms: float = 0.0

    @property
    def strategies(self) -> list:
        return self._strategies

    def add_strategy(self, strategy) -> None:
        """Register a strategy for batch execution."""
        self._strategies.append(strategy)

    def run(
        self,
        symbol_prices: dict[str, list[float]],
        *,
        indicators: Optional[list[str]] = None,
        benchmark: bool = False,
    ) -> dict[str, Any]:
        """Run batch signal generation across all symbols.

        Args:
            symbol_prices: dict of symbol → list of float prices (latest last).
                           All price lists must be the same length, or they
                           will be left-padded with NaN up to max length.
            indicators: list of indicator names to compute
                        (default: ["RSI", "MACD", "MA", "BB", "VOLATILITY"])
            benchmark: if True, log timing info

        Returns:
            dict with:
              - "symbols": list of symbol names (order preserved)
              - "indicators": dict of indicator name → numpy array [N]
              - "signals": dict of strategy name → dict of numpy arrays
              - "meta": {"n_symbols": int, "elapsed_ms": float}
        """
        if not symbol_prices:
            return {
                "symbols": [],
                "indicators": {},
                "signals": {},
                "meta": {"n_symbols": 0, "elapsed_ms": 0.0},
            }

        if indicators is None:
            indicators = ["RSI", "MACD", "MA", "BB", "VOLATILITY", "MOMENTUM"]

        t0 = time.perf_counter()

        # ── 1. Convert dict → 2D matrix ─────────────────────────
        symbols, price_matrix = self._dict_to_matrix(symbol_prices)
        n_symbols = len(symbols)
        current_prices = price_matrix[:, -1]  # [N] latest price per symbol

        # ── 2. Compute indicators ───────────────────────────────
        ind_results: dict[str, np.ndarray] = {}
        ind_map: dict[str, np.ndarray] = {}

        for ind_name in indicators:
            ind_upper = ind_name.upper()
            if ind_upper == "RSI":
                rsi = calc_rsi_2d(price_matrix)
                ind_map["RSI"] = rsi
                ind_results["RSI"] = rsi
            elif ind_upper == "MACD":
                macd = calc_macd_2d(price_matrix)
                ind_map["MACD"] = macd["macd"]
                ind_map["MACD_SIGNAL"] = macd["signal"]
                ind_map["MACD_HISTOGRAM"] = macd["histogram"]
                ind_map["MACD_SIGNAL_TEXT"] = macd["signal_text"]
                ind_results["MACD"] = macd
            elif ind_upper == "MA":
                ma = calc_ma_2d(price_matrix)
                ind_map.update(ma)
                ind_results["MA"] = ma
            elif ind_upper == "BB":
                bb = calc_bb_2d(price_matrix)
                ind_map["BB_MIDDLE"] = bb["middle"]
                ind_map["BB_UPPER"] = bb["upper"]
                ind_map["BB_LOWER"] = bb["lower"]
                ind_results["BB"] = bb
            elif ind_upper == "VOLATILITY":
                vol = calc_volatility_2d(price_matrix)
                ind_map["VOLATILITY"] = vol
                ind_results["volatility"] = vol
            elif ind_upper == "SHARPE":
                sharpe = calc_sharpe_2d(price_matrix)
                ind_map["SHARPE"] = sharpe
                ind_results["sharpe"] = sharpe
            elif ind_upper in ("MOMENTUM", "MOM"):
                mom = calc_momentum_2d(price_matrix)
                ind_map.update(mom)
                ind_results["momentum"] = mom

        # ── 3. Run strategies ──────────────────────────────────
        signals: dict[str, dict] = {}
        for strategy in self._strategies:
            if hasattr(strategy, "generate_signals_batch"):
                try:
                    result = strategy.generate_signals_batch(
                        symbols=symbols,
                        current_prices=current_prices,
                        indicators=ind_map,
                        prices_matrix=price_matrix,
                    )
                    signals[strategy.name] = result
                except Exception as e:
                    log.error(f"[vector_engine] strategy '{strategy.name}' failed: {e}")
                    signals[strategy.name] = {"error": str(e)}

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self._last_benchmark_ms = elapsed_ms

        if benchmark:
            log.info(
                f"[vector_engine] batch complete: {n_symbols} symbols, "
                f"{len(self._strategies)} strategies, "
                f"{elapsed_ms:.1f} ms "
                f"({n_symbols / max(elapsed_ms, 0.001) * 1000:.0f} symbols/s)"
            )

        return {
            "symbols": symbols,
            "indicators": ind_results,
            "signals": signals,
            "current_prices": current_prices,
            "meta": {
                "n_symbols": n_symbols,
                "n_strategies": len(self._strategies),
                "elapsed_ms": round(elapsed_ms, 3),
            },
        }

    def run_benchmark(self, n_symbols: int = 10000, n_bars: int = 200) -> dict:
        """Generate synthetic data and benchmark throughput.

        Args:
            n_symbols: number of symbols to simulate
            n_bars: number of price bars per symbol

        Returns:
            benchmark dict with timing and throughput.
        """
        rng = np.random.RandomState(42)
        prices = rng.randn(n_symbols, n_bars).cumsum(axis=1) + 100.0

        # Generate symbols
        symbols = [f"TOKEN_{i}" for i in range(n_symbols)]
        symbol_dict = {s: prices[i].tolist() for i, s in enumerate(symbols)}

        return self.run(symbol_dict, benchmark=True)

    # ── Internal helpers ────────────────────────────────────────

    @staticmethod
    def _dict_to_matrix(
        symbol_prices: dict[str, list[float]],
    ) -> tuple[list[str], "np.ndarray"]:
        """Convert dict of symbol→price_list to (symbols, price_matrix).

        Pads shorter lists with NaN from the left.
        """
        symbols = list(symbol_prices.keys())
        max_len = max(len(v) for v in symbol_prices.values())

        matrix = np.full((len(symbols), max_len), np.nan, dtype=np.float64)
        for i, symbol in enumerate(symbols):
            prices = symbol_prices[symbol]
            n = len(prices)
            matrix[i, -n:] = prices  # right-align with latest

        return symbols, matrix

    def to_serializable(self, batch_result: dict) -> dict:
        """Convert numpy arrays in batch result to JSON-serializable lists.

        Args:
            batch_result: dict returned by VectorEngine.run()

        Returns:
            JSON-serializable dict.
        """
        def _serialize(val):
            if isinstance(val, np.ndarray):
                return val.tolist()
            if isinstance(val, dict):
                return {k: _serialize(v) for k, v in val.items()}
            if isinstance(val, (np.floating,)):
                return float(val) if np.isfinite(val) else None
            if isinstance(val, (np.integer,)):
                return int(val)
            return val

        return _serialize(batch_result)
