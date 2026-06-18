"""
PREDICITIVE TRADING BOT · STRATEGY BACKTESTER
================================================
Real walk-forward backtesting engine adapted from QuantMuse
FactorBacktest.

Replaces the simulated-random StrategyBacktestSkill with actual
strategy evaluation over historical data.

Architecture:
  - StrategyBacktester: wraps StrategyRunner for backtesting
  - run_backtest(): full walk-forward evaluation with all metrics
  - compute_information_coefficient(): IC between signals & returns
  - rolling_metrics(): rolling sharpe, win rate, return
  - compare_strategies(): side-by-side multi-strategy comparison
  - generate_report(): formatted text performance report

Adapted from QuantMuse FactorBacktest with these changes:
  - Works with single-symbol price history (not multi-symbol DataFrames)
  - Uses our StrategyRunner.evaluate_strategy() for walk-forward simulation
  - IC computed from strategy confidence vs forward price returns
  - No pandas dependency — plain Python lists/dicts
"""

import logging
import math
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional

from .strategy import StrategyRegistry
from .strategy_runner import StrategyRunner, _compute_evaluation_metrics
from .base import SkillContext
from .indicators import _mean, _std

log = logging.getLogger("trading.backtest")


# ═════════════════════════════════════════════════════════════════════════
# DATA CONTRACTS
# ═════════════════════════════════════════════════════════════════════════


@dataclass
class BacktestResult:
    """Full backtest result for a single strategy run.

    Adapted from QuantMuse BacktestResult.
    """
    strategy_name: str
    symbol: str
    start_date: str = ""
    end_date: str = ""
    total_bars: int = 0
    total_trades: int = 0
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    information_coefficient: Optional[float] = None
    ic_rank: Optional[float] = None
    ic_ir: Optional[float] = None
    rolling_sharpe: list[dict] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    evaluation_time_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_bars": self.total_bars,
            "total_trades": self.total_trades,
            "total_return_pct": self.total_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_win_pct": self.avg_win_pct,
            "avg_loss_pct": self.avg_loss_pct,
            "profit_factor": self.profit_factor,
            "information_coefficient": self.information_coefficient,
            "ic_rank": self.ic_rank,
            "ic_ir": self.ic_ir,
            "rolling_sharpe": self.rolling_sharpe,
            "parameters": self.parameters,
            "trades": self.trades,
            "evaluation_time_sec": self.evaluation_time_sec,
        }


@dataclass
class ComparisonResult:
    """Side-by-side comparison of multiple strategies."""
    symbol: str
    strategies: list[str] = field(default_factory=list)
    results: dict[str, BacktestResult] = field(default_factory=dict)
    winner: str = ""
    winner_metric: str = "sharpe_ratio"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategies": self.strategies,
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "winner": self.winner,
            "winner_metric": self.winner_metric,
            "summary": self.summary,
        }


# ═════════════════════════════════════════════════════════════════════════
# STRATEGY BACKTESTER
# ═════════════════════════════════════════════════════════════════════════


class StrategyBacktester:
    """Real walk-forward backtester for trading strategies.

    Unlike the old simulated StrategyBacktestSkill (which used random numbers),
    this runs actual strategy evaluations over historical price data via the
    StrategyRunner.

    Adapted from QuantMuse FactorBacktest with additions for single-symbol
    strategy evaluation.

    Usage:
        registry = StrategyRegistry()
        register_builtin_strategies(registry)
        backtester = StrategyBacktester(registry)

        result = await backtester.run_backtest(
            "strategy.momentum", "BTC/USD", price_history)
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        skill_context: Optional[SkillContext] = None,
        runner: Optional[StrategyRunner] = None,
    ):
        self._registry = registry
        self._skill_ctx = skill_context
        self._runner = runner or StrategyRunner(registry, skill_context)

    # ── Core Backtest ───────────────────────────────────────────────────

    async def run_backtest(
        self,
        strategy_name: str,
        symbol: str,
        price_history: list[float],
        parameters: Optional[dict[str, Any]] = None,
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.2,
        trade_fee_pct: float = 0.001,
        warmup_bars: int = 20,
        compute_ic: bool = True,
        ic_lag: int = 1,
        rolling_window: int = 50,
    ) -> BacktestResult:
        """Run a full backtest with all metrics.

        Args:
            strategy_name: Registered strategy name
            symbol: Trading pair symbol
            price_history: Historical prices (oldest first)
            parameters: Optional strategy parameters
            initial_capital: Starting capital
            position_size_pct: Fraction of capital per trade
            trade_fee_pct: Trading fee (e.g. 0.001 = 0.1%)
            warmup_bars: Bars to skip at start (strategy warmup)
            compute_ic: Whether to compute Information Coefficient
            ic_lag: Lag for IC calculation (1 = next-bar return)
            rolling_window: Window size for rolling metrics

        Returns:
            BacktestResult with full metrics
        """
        _started = time.time()

        if not price_history or len(price_history) < warmup_bars + 5:
            return BacktestResult(
                strategy_name=strategy_name,
                symbol=symbol,
                evaluation_time_sec=time.time() - _started,
            )

        # Run walk-forward evaluation via StrategyRunner
        eval_result = await self._runner.evaluate_strategy(
            strategy_name,
            symbol,
            price_history,
            parameters=parameters,
            initial_capital=initial_capital,
            position_size_pct=position_size_pct,
            trade_fee_pct=trade_fee_pct,
            warmup_bars=warmup_bars,
        )

        # Build BacktestResult from evaluation
        result = BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=f"bar_{warmup_bars}",
            end_date=f"bar_{len(price_history) - 1}",
            total_bars=len(price_history) - warmup_bars,
            total_trades=eval_result.get("total_trades", 0),
            total_return_pct=eval_result.get("total_return_pct", 0.0),
            sharpe_ratio=eval_result.get("sharpe_ratio", 0.0),
            win_rate=eval_result.get("win_rate", 0.0),
            max_drawdown_pct=eval_result.get("max_drawdown_pct", 0.0),
            avg_win_pct=eval_result.get("avg_win_pct", 0.0),
            avg_loss_pct=eval_result.get("avg_loss_pct", 0.0),
            profit_factor=eval_result.get("profit_factor", 0.0),
            parameters=eval_result.get("parameters", parameters or {}),
            trades=eval_result.get("trades", []),
            evaluation_time_sec=time.time() - _started,
        )

        # Compute Information Coefficient (IC)
        if compute_ic and len(price_history) > warmup_bars + ic_lag + 10:
            ic, rank_ic, ic_ir = await self.compute_information_coefficient(
                strategy_name,
                symbol,
                price_history,
                parameters=parameters,
                lag=ic_lag,
                warmup_bars=warmup_bars,
            )
            result.information_coefficient = ic
            result.ic_rank = rank_ic
            result.ic_ir = ic_ir

        # Compute rolling metrics
        if eval_result.get("equity_curve_points", 0) > rolling_window:
            result.rolling_sharpe = self.rolling_metrics(
                eval_result.get("trades", []),
                window=rolling_window,
            )

        return result

    # ── Information Coefficient ─────────────────────────────────────────

    async def compute_information_coefficient(
        self,
        strategy_name: str,
        symbol: str,
        price_history: list[float],
        parameters: Optional[dict[str, Any]] = None,
        lag: int = 1,
        warmup_bars: int = 20,
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """Compute Information Coefficient — correlation between strategy
        signals and forward returns.

        Adapted from QuantMuse FactorBacktest.calculate_information_coefficient.

        IC measures how well the strategy's confidence score predicts
        forward price movement. Positive IC means the strategy's signals
        are directionally correct.

        Returns:
            (ic_mean, rank_ic_mean, ic_ir) tuple — each can be None if
            insufficient data.
        """
        if not price_history or len(price_history) < warmup_bars + lag + 5:
            return None, None, None

        signals: list[float] = []      # Strategy confidence (direction-aware)
        forward_returns: list[float] = []  # Forward price return

        # Get strategy instance once, reuse
        strategy = self._registry.get_strategy(strategy_name)
        if strategy is None:
            strategy = self._registry.create_strategy(
                strategy_name,
                parameters=parameters,
                skill_context=self._skill_ctx,
            )
        if strategy is None:
            return None, None, None

        if parameters:
            for key, value in parameters.items():
                strategy.parameters[key] = value

        for i in range(warmup_bars, len(price_history) - lag):
            current_price = price_history[i]
            forward_price = price_history[i + lag]

            price_data = {
                "price": current_price,
                "prices": price_history[: i + 1],
            }

            try:
                result = await strategy.generate_signals(symbol, price_data)
            except Exception:
                continue

            # Signal: confidence with direction
            # buy=positive, sell=negative, hold=0
            if result.action == "buy":
                signal = result.confidence
            elif result.action == "sell":
                signal = -result.confidence
            else:
                signal = 0.0

            # Forward return
            if current_price > 0:
                fwd_ret = (forward_price - current_price) / current_price
            else:
                fwd_ret = 0.0

            signals.append(signal)
            forward_returns.append(fwd_ret)

        if len(signals) < 10:
            return None, None, None

        # Pearson IC: correlation between signals and forward returns
        ic_values = []
        rank_ic_values = []
        # Compute rolling IC (per-bar, using a mini-window)
        mini_window = min(20, len(signals))

        for j in range(mini_window - 1, len(signals)):
            seg_signals = signals[j - mini_window + 1 : j + 1]
            seg_returns = forward_returns[j - mini_window + 1 : j + 1]
            ic = _pearson_correlation(seg_signals, seg_returns)
            if ic is not None:
                ic_values.append(ic)
            rank_ic = _spearman_rank_correlation(seg_signals, seg_returns)
            if rank_ic is not None:
                rank_ic_values.append(rank_ic)

        if not ic_values:
            return None, None, None

        ic_mean = round(_mean(ic_values), 4)
        ic_std = _std(ic_values, ddof=1)
        ic_ir = round(ic_mean / ic_std, 4) if ic_std and ic_std > 0 else 0.0

        rank_ic_mean = round(_mean(rank_ic_values), 4) if rank_ic_values else None

        return ic_mean, rank_ic_mean, ic_ir

    # ── Rolling Metrics ─────────────────────────────────────────────────

    @staticmethod
    def rolling_metrics(
        trades: list[dict],
        window: int = 50,
    ) -> list[dict]:
        """Compute rolling window metrics from trade history.

        Returns a list of dicts with: window_start, window_end, win_rate,
        avg_return_pct, profit_factor.
        """
        if not trades or len(trades) < 3:
            return []

        results: list[dict] = []
        for start in range(0, len(trades), max(1, window // 2)):
            end = min(start + window, len(trades))
            window_trades = trades[start:end]

            if len(window_trades) < 3:
                continue

            wins = [t for t in window_trades if t["pnl"] > 0]
            losses = [t for t in window_trades if t["pnl"] <= 0]

            win_rate = round(len(wins) / len(window_trades), 3)
            avg_return = round(
                _mean([t["pnl_pct"] for t in window_trades]), 2
            )
            total_wins = sum(t["pnl"] for t in wins)
            total_losses = abs(sum(t["pnl"] for t in losses))
            profit_factor = (
                round(total_wins / total_losses, 2)
                if total_losses > 0 else float("inf")
            )

            results.append({
                "window_start": start,
                "window_end": end,
                "num_trades": len(window_trades),
                "win_rate": win_rate,
                "avg_return_pct": avg_return,
                "profit_factor": profit_factor if profit_factor != float("inf") else 999.99,
            })

        return results

    # ── Strategy Comparison ─────────────────────────────────────────────

    async def compare_strategies(
        self,
        strategy_names: list[str],
        symbol: str,
        price_history: list[float],
        parameters: Optional[dict[str, dict[str, Any]]] = None,
        winner_metric: str = "sharpe_ratio",
        **backtest_kwargs,
    ) -> ComparisonResult:
        """Run backtests for multiple strategies and compare side by side.

        Returns a ComparisonResult identifying the winner on the chosen metric.
        """
        params_map = parameters or {}
        results: dict[str, BacktestResult] = {}
        best_value: float = float("-inf")
        best_strategy: str = ""

        for name in strategy_names:
            try:
                bt = await self.run_backtest(
                    name,
                    symbol,
                    price_history,
                    parameters=params_map.get(name),
                    **backtest_kwargs,
                )
                results[name] = bt

                # Track winner
                metric_val = _get_metric(bt, winner_metric)
                if metric_val > best_value:
                    best_value = metric_val
                    best_strategy = name

            except Exception as exc:
                log.error(f"[backtest] comparison failed for '{name}': {exc}")

        # Build summary
        summary_lines = [f"Strategy Comparison — {symbol}"]
        summary_lines.append(f"Winner ({winner_metric}): {best_strategy} ({best_value})")
        summary_lines.append("")
        for name, bt in sorted(
            results.items(),
            key=lambda kv: _get_metric(kv[1], winner_metric),
            reverse=True,
        ):
            summary_lines.append(
                f"  {name}: return={bt.total_return_pct}%, "
                f"sharpe={bt.sharpe_ratio}, win_rate={bt.win_rate}, "
                f"trades={bt.total_trades}"
            )

        return ComparisonResult(
            symbol=symbol,
            strategies=strategy_names,
            results=results,
            winner=best_strategy,
            winner_metric=winner_metric,
            summary="\n".join(summary_lines),
        )

    # ── Report Generation ───────────────────────────────────────────────

    def generate_report(self, result: BacktestResult) -> str:
        """Generate a formatted performance report.

        Adapted from QuantMuse generate_performance_report.
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"  BACKTEST REPORT: {result.strategy_name}")
        lines.append("=" * 60)
        lines.append(f"  Symbol:          {result.symbol}")
        lines.append(f"  Period:          {result.start_date} → {result.end_date}")
        lines.append(f"  Bars evaluated:  {result.total_bars}")
        lines.append(f"  Evaluation time: {result.evaluation_time_sec:.1f}s")
        lines.append("-" * 60)

        # Returns
        lines.append(f"  Total Return:    {result.total_return_pct:+.2f}%")
        lines.append(f"  Sharpe Ratio:    {result.sharpe_ratio:.4f}")
        lines.append(f"  Max Drawdown:    {result.max_drawdown_pct:.2f}%")

        # Trades
        lines.append("-" * 60)
        lines.append(f"  Total Trades:    {result.total_trades}")
        lines.append(f"  Win Rate:        {result.win_rate * 100:.1f}%")
        lines.append(f"  Avg Win:         {result.avg_win_pct:+.2f}%")
        lines.append(f"  Avg Loss:        {result.avg_loss_pct:+.2f}%")
        lines.append(f"  Profit Factor:   {result.profit_factor:.2f}")

        # IC
        if result.information_coefficient is not None:
            lines.append("-" * 60)
            lines.append(f"  IC (Pearson):    {result.information_coefficient:.4f}")
            if result.ic_rank is not None:
                lines.append(f"  IC Rank:         {result.ic_rank:.4f}")
            lines.append(f"  IC IR:           {result.ic_ir:.4f}")

        # Rolling
        if result.rolling_sharpe:
            lines.append("-" * 60)
            lines.append("  Rolling Metrics (most recent windows):")
            for rw in result.rolling_sharpe[-3:]:
                lines.append(
                    f"    Trades {rw['window_start']}-{rw['window_end']}: "
                    f"win_rate={rw['win_rate'] * 100:.0f}%, "
                    f"avg_return={rw['avg_return_pct']:+.1f}%, "
                    f"PF={rw['profit_factor']:.2f}"
                )

        lines.append("=" * 60)
        return "\n".join(lines)

    def generate_comparison_report(self, comparison: ComparisonResult) -> str:
        """Generate a comparison report for multiple strategies."""
        lines = []
        lines.append("=" * 70)
        lines.append("  STRATEGY COMPARISON REPORT")
        lines.append("=" * 70)
        lines.append(f"  Symbol:    {comparison.symbol}")
        lines.append(f"  Winner:    {comparison.winner} (by {comparison.winner_metric})")
        lines.append("-" * 70)
        lines.append(
            f"  {'Strategy':<30} {'Return':>8} {'Sharpe':>8} "
            f"{'Win%':>7} {'Trades':>7} {'MaxDD':>7}"
        )
        lines.append("-" * 70)

        for name, bt in sorted(
            comparison.results.items(),
            key=lambda kv: _get_metric(kv[1], comparison.winner_metric),
            reverse=True,
        ):
            lines.append(
                f"  {name:<30} {bt.total_return_pct:>+7.1f}% "
                f"{bt.sharpe_ratio:>8.3f} {bt.win_rate*100:>6.0f}% "
                f"{bt.total_trades:>7} {bt.max_drawdown_pct:>6.1f}%"
            )

        lines.append("=" * 70)
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════


def _pearson_correlation(x: list[float], y: list[float]) -> Optional[float]:
    """Pearson correlation coefficient."""
    if len(x) != len(y) or len(x) < 3:
        return None
    n = len(x)
    mean_x = _mean(x)
    mean_y = _mean(y)
    std_x = _std(x, ddof=0)
    std_y = _std(y, ddof=0)
    if std_x == 0 or std_y == 0:
        return 0.0
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / n
    return cov / (std_x * std_y)


def _spearman_rank_correlation(x: list[float], y: list[float]) -> Optional[float]:
    """Spearman rank correlation coefficient."""
    if len(x) != len(y) or len(x) < 3:
        return None
    n = len(x)
    # Rank x and y
    x_ranks = _rank(x)
    y_ranks = _rank(y)
    return _pearson_correlation(x_ranks, y_ranks)


def _rank(values: list[float]) -> list[float]:
    """Return ranks (1-based) for values. Ties get average rank."""
    indexed = sorted(enumerate(values), key=lambda p: p[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _get_metric(bt: BacktestResult, metric: str) -> float:
    """Extract a numeric metric from a BacktestResult."""
    mapping = {
        "sharpe_ratio": bt.sharpe_ratio,
        "total_return_pct": bt.total_return_pct,
        "win_rate": bt.win_rate,
        "profit_factor": bt.profit_factor if bt.profit_factor != float("inf") else 999.0,
        "max_drawdown_pct": -bt.max_drawdown_pct,  # negated: smaller drawdown wins
    }
    return mapping.get(metric, bt.sharpe_ratio)
