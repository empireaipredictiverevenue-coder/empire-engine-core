"""
PREDICITIVE TRADING BOT · STRATEGY RUNNER
===========================================
Strategy execution and backtest evaluation engine.

Adapted from QuantMuse StrategyRunner — runs individual strategies,
evaluates them over historical price data (walk-forward simulation),
and aggregates performance metrics.

Architecture:
  - StrategyRunner: creates and runs strategies via a StrategyRegistry
  - evaluate_strategy(): walk-forward simulation over price history
  - run_strategy(): single-point strategy execution
  - batch_run(): run multiple strategies in parallel

No pandas dependency — works with plain Python lists/dicts.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .strategy import StrategyBase, StrategyResult, StrategyRegistry
from .base import SkillContext
from .indicators import _mean, _std

log = logging.getLogger("trading.runner")


# ═════════════════════════════════════════════════════════════════════════
# STRATEGY RUNNER
# ═════════════════════════════════════════════════════════════════════════


class StrategyRunner:
    """Runner for executing and evaluating trading strategies.

    Adapted from QuantMuse StrategyRunner with these changes:
      - Async execution (our strategies use async generate_signals)
      - Works with plain lists (no pandas dependency)
      - evaluate_strategy() simulates walk-forward over historical data
      - Integrates with SkillContext for strategy skill composition

    Usage:
        registry = StrategyRegistry()
        register_builtin_strategies(registry)
        runner = StrategyRunner(registry, skill_context=ctx)

        # Single run
        result = await runner.run_strategy("strategy.momentum", "BTC/USD",
                                           {"price": 62000})

        # Historical evaluation
        metrics = await runner.evaluate_strategy("strategy.momentum", "BTC/USD",
                                                  price_history)
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        skill_context: Optional[SkillContext] = None,
    ):
        self._registry = registry
        self._skill_ctx = skill_context
        self._execution_history: list[dict[str, Any]] = []

    # ── Single Execution ────────────────────────────────────────────────

    async def run_strategy(
        self,
        strategy_name: str,
        symbol: str,
        price_data: Optional[dict] = None,
        parameters: Optional[dict[str, Any]] = None,
    ) -> StrategyResult:
        """Run a strategy once with given parameters and price data.

        Args:
            strategy_name: Name of the registered strategy
            symbol: Trading pair symbol
            price_data: Current price data dict (must include 'price' key)
            parameters: Optional parameter overrides

        Returns:
            StrategyResult with populated metrics
        """
        _started = time.time()

        # Get or create strategy instance
        strategy = self._registry.get_strategy(strategy_name)
        if strategy is None:
            strategy = self._registry.create_strategy(
                strategy_name,
                parameters=parameters,
                skill_context=self._skill_ctx,
            )
            if strategy is None:
                raise ValueError(f"Strategy '{strategy_name}' not found in registry")

        # Apply parameter overrides
        if parameters:
            # Merge overrides into strategy params without strict validation.
            # Strategies use .get(key, default) for each param, so partial
            # overrides are safe — missing keys fall back to defaults.
            for key, value in parameters.items():
                strategy.parameters[key] = value

        # Validate dependencies
        if not strategy.validate_dependencies():
            log.warning(
                f"[runner] strategy '{strategy_name}' has missing dependencies"
            )

        # Pipeline: preprocess → generate → postprocess → metrics
        processed = await strategy.preprocess(price_data)
        result = await strategy.generate_signals(symbol, price_data or processed)
        result = await strategy.postprocess(result)
        result.metrics = await strategy.calculate_metrics(result)

        elapsed = round(time.time() - _started, 3)
        result.metrics["execution_time_sec"] = elapsed
        result.metrics["evaluated_at"] = datetime.now(timezone.utc).isoformat()

        # Log execution
        self._log_execution(strategy_name, result, elapsed, parameters)

        return result

    # ── Historical Evaluation (Walk-Forward) ────────────────────────────

    async def evaluate_strategy(
        self,
        strategy_name: str,
        symbol: str,
        price_history: list[float],
        parameters: Optional[dict[str, Any]] = None,
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.2,
        trade_fee_pct: float = 0.001,
        warmup_bars: int = 20,
    ) -> dict[str, Any]:
        """Evaluate a strategy over historical price data via walk-forward simulation.

        Runs the strategy on each price point in sequence (oldest → newest),
        simulating buys/sells and tracking P&L. This is a realistic
        out-of-sample evaluation — the strategy only sees data up to the
        current point.

        Args:
            strategy_name: Name of the registered strategy
            symbol: Trading pair symbol
            price_history: List of historical prices (oldest first, newest last)
            parameters: Optional strategy parameter overrides
            initial_capital: Starting capital for simulation
            position_size_pct: Fraction of capital per trade
            trade_fee_pct: Fee per trade (e.g. 0.001 = 0.1%)
            warmup_bars: Number of initial bars to skip (strategy warmup)

        Returns:
            dict with keys: total_return_pct, sharpe_ratio, win_rate,
            max_drawdown_pct, total_trades, avg_win_pct, avg_loss_pct,
            profit_factor, final_capital, trade_log, metrics
        """
        if not price_history or len(price_history) < warmup_bars + 5:
            return _empty_evaluation()

        _started = time.time()

        capital = initial_capital
        position = 0.0  # Units held
        entry_price = 0.0
        trades: list[dict] = []
        equity_curve: list[float] = [initial_capital]
        in_position = False

        # Get strategy instance once, reuse for all data points
        strategy = self._registry.get_strategy(strategy_name)
        if strategy is None:
            strategy = self._registry.create_strategy(
                strategy_name,
                parameters=parameters,
                skill_context=self._skill_ctx,
            )
            if strategy is None:
                return _empty_evaluation()

        if parameters:
            # Merge overrides into strategy params without strict validation.
            # Strategies use .get(key, default) for each param, so partial
            # overrides are safe — missing keys fall back to defaults.
            for key, value in parameters.items():
                strategy.parameters[key] = value

        for i in range(warmup_bars, len(price_history)):
            current_price = price_history[i]

            # Build price data with history up to current point
            # (what the strategy could actually know at this point)
            price_data = {
                "price": current_price,
                "prices": price_history[: i + 1],
                "volumes": None,  # No volume data in basic mode
                "index": i,
                "total_bars": len(price_history),
            }

            try:
                result = await strategy.generate_signals(symbol, price_data)
            except Exception as exc:
                log.warning(f"[runner] strategy error at bar {i}: {exc}")
                continue

            action = result.action
            position_pct = result.position_size_pct or position_size_pct

            # Simulate trade execution
            if action == "buy" and not in_position and current_price > 0:
                # Enter long — deduct allocated capital from cash
                trade_capital = capital * position_pct
                fee = trade_capital * trade_fee_pct
                position = (trade_capital - fee) / current_price
                entry_price = current_price
                capital -= trade_capital  # Cash allocated to position
                in_position = True

            elif action == "sell" and in_position and current_price > 0:
                # Exit long — add proceeds back to cash
                trade_value = position * current_price
                fee = trade_value * trade_fee_pct
                proceeds = trade_value - fee
                pnl = proceeds - trade_capital
                pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

                capital += proceeds
                trades.append({
                    "entry": entry_price,
                    "exit": current_price,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct * 100, 2),
                    "bar_entry": i - 1,  # Approximate
                    "bar_exit": i,
                })
                position = 0.0
                in_position = False

            # Track equity
            equity = capital + (position * current_price if in_position else 0)
            equity_curve.append(equity)

        # Close any open position at final price
        if in_position and price_history:
            final_price = price_history[-1]
            trade_value = position * final_price
            fee = trade_value * trade_fee_pct
            proceeds = trade_value - fee
            capital += proceeds
            position = 0.0
            equity_curve.append(capital)

        # Compute metrics from the equity curve
        elapsed = time.time() - _started
        metrics = _compute_evaluation_metrics(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
            final_capital=capital,
            elapsed_sec=elapsed,
        )

        metrics["strategy_name"] = strategy_name
        metrics["symbol"] = symbol
        metrics["parameters"] = strategy.parameters.copy() if strategy else {}

        # Log evaluation
        self._execution_history.append({
            "strategy_name": strategy_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_sec": round(elapsed, 2),
            "action": "evaluate",
            "confidence": 0.0,
            "parameters": parameters,
            "metrics": {k: v for k, v in metrics.items() if k != "trades"},
        })

        return metrics

    # ── Batch Execution ─────────────────────────────────────────────────

    async def run_multiple_strategies(
        self,
        strategy_configs: list[dict[str, Any]],
        symbol: str,
        price_data: Optional[dict] = None,
    ) -> dict[str, StrategyResult]:
        """Run multiple strategies sequentially.

        Each config dict should have 'name' (required) and optional
        'parameters' key.
        """
        results: dict[str, StrategyResult] = {}

        for config in strategy_configs:
            name = config["name"]
            params = config.get("parameters", {})
            try:
                result = await self.run_strategy(name, symbol, price_data, params)
                results[name] = result
            except Exception as exc:
                log.error(f"[runner] strategy '{name}' failed: {exc}")
                # Return a failure result
                results[name] = StrategyResult(
                    strategy_name=name,
                    action="hold",
                    symbol=symbol,
                    confidence=0.0,
                    metrics={"error": str(exc)},
                )

        return results

    async def evaluate_multiple(
        self,
        strategy_names: list[str],
        symbol: str,
        price_history: list[float],
        parameters: Optional[dict[str, dict[str, Any]]] = None,
        **eval_kwargs,
    ) -> dict[str, dict[str, Any]]:
        """Evaluate multiple strategies over the same historical data.

        Returns dict mapping strategy_name → evaluation metrics.
        """
        results: dict[str, dict[str, Any]] = {}
        params_map = parameters or {}

        for name in strategy_names:
            try:
                eval_result = await self.evaluate_strategy(
                    name, symbol, price_history,
                    parameters=params_map.get(name),
                    **eval_kwargs,
                )
                results[name] = eval_result
            except Exception as exc:
                log.error(f"[runner] evaluation failed for '{name}': {exc}")
                results[name] = _empty_evaluation()

        return results

    # ── Logging ─────────────────────────────────────────────────────────

    def _log_execution(
        self,
        strategy_name: str,
        result: StrategyResult,
        elapsed: float,
        parameters: Optional[dict],
    ) -> None:
        entry = {
            "strategy_name": strategy_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_sec": elapsed,
            "action": result.action,
            "confidence": result.confidence,
            "parameters": parameters,
            "metrics": result.metrics,
        }
        self._execution_history.append(entry)

    def get_execution_history(
        self, strategy_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Return execution history, optionally filtered by strategy."""
        if strategy_name:
            return [
                e for e in self._execution_history
                if e["strategy_name"] == strategy_name
            ]
        return list(self._execution_history)

    def clear_history(self) -> None:
        """Clear execution history."""
        self._execution_history.clear()
        log.info("[runner] execution history cleared")


# ═════════════════════════════════════════════════════════════════════════
# EVALUATION METRICS
# ═════════════════════════════════════════════════════════════════════════


def _compute_evaluation_metrics(
    *,
    equity_curve: list[float],
    trades: list[dict],
    initial_capital: float,
    final_capital: float,
    elapsed_sec: float,
) -> dict[str, Any]:
    """Compute standard performance metrics from equity curve and trades.

    Adapted from QuantMuse performance metrics calculation.
    """
    total_return_pct = round(
        (final_capital - initial_capital) / initial_capital * 100, 2
    )

    # Compute returns from equity curve
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] > 0:
            ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            returns.append(ret)

    # Sharpe ratio (annualized, assuming daily data)
    sharpe = 0.0
    if returns and len(returns) > 1:
        mean_ret = _mean(returns)
        std_ret = _std(returns, ddof=1)
        if std_ret and std_ret > 0:
            sharpe = round((mean_ret / std_ret) * (252 ** 0.5), 4)

    # Max drawdown from equity curve
    max_dd_pct = 0.0
    peak = equity_curve[0]
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd_pct:
                max_dd_pct = dd
    max_dd_pct = round(max_dd_pct * 100, 2)

    # Trade stats
    total_trades = len(trades)
    winning_trades = [t for t in trades if t["pnl"] > 0]
    losing_trades = [t for t in trades if t["pnl"] <= 0]
    win_count = len(winning_trades)
    lose_count = len(losing_trades)

    win_rate = round(win_count / total_trades, 3) if total_trades > 0 else 0.0

    avg_win_pct = (
        round(_mean([t["pnl_pct"] for t in winning_trades]), 2)
        if winning_trades else 0.0
    )
    avg_loss_pct = (
        round(_mean([t["pnl_pct"] for t in losing_trades]), 2)
        if losing_trades else 0.0
    )

    # Profit factor
    total_wins = sum(t["pnl"] for t in winning_trades)
    total_losses = abs(sum(t["pnl"] for t in losing_trades))
    profit_factor = (
        round(total_wins / total_losses, 2) if total_losses > 0 else float("inf")
    )

    # Win/loss ratio
    win_loss_ratio = (
        round(abs(avg_win_pct / avg_loss_pct), 2)
        if avg_loss_pct != 0 else float("inf")
    )

    # Information ratio placeholder (can be extended with benchmark)
    information_ratio = 0.0

    return {
        "total_return_pct": total_return_pct,
        "sharpe_ratio": sharpe,
        "win_rate": win_rate,
        "max_drawdown_pct": max_dd_pct,
        "total_trades": total_trades,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "profit_factor": profit_factor,
        "win_loss_ratio": win_loss_ratio,
        "information_ratio": information_ratio,
        "final_capital": round(final_capital, 2),
        "initial_capital": initial_capital,
        "evaluation_time_sec": round(elapsed_sec, 2),
        "equity_curve_points": len(equity_curve),
        "trades": trades,
    }


def _empty_evaluation() -> dict[str, Any]:
    """Return a zeroed-out evaluation dict when data is insufficient."""
    return {
        "total_return_pct": 0.0,
        "sharpe_ratio": 0.0,
        "win_rate": 0.0,
        "max_drawdown_pct": 0.0,
        "total_trades": 0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "profit_factor": 0.0,
        "win_loss_ratio": 0.0,
        "information_ratio": 0.0,
        "final_capital": 0.0,
        "initial_capital": 0.0,
        "evaluation_time_sec": 0.0,
        "equity_curve_points": 0,
        "trades": [],
    }
