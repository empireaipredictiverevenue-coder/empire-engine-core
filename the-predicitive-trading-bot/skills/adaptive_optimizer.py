"""
PREDICITIVE TRADING BOT · ADAPTIVE OPTIMIZER
===============================================
Background auto-tuning engine that continuously optimizes strategy
parameters for the current market regime.

Architecture:
  - AdaptiveOptimizer: orchestrates detect → optimize → hot-swap cycle
  - tune(): one-shot tuning cycle for a single strategy+market+symbol
  - auto_tune_loop(): continuous background loop (call as a cron/PM2 job)
  - hot_swap(): updates live strategy instance and market_profiles

Integrates with:
  - MarketRegimeDetector: detects current regime
  - StrategyOptimizer: runs grid/scipy optimization
  - StrategyBase.market_profiles: hot-swaps best parameters
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .strategy import (
    StrategyBase, StrategyRegistry, register_builtin_strategies,
)
from .strategy_optimizer import StrategyOptimizer
from .market_regime import MarketRegimeDetector

log = logging.getLogger("trading.adaptive")


# ═════════════════════════════════════════════════════════════════════════
# ADAPTIVE OPTIMIZER
# ═════════════════════════════════════════════════════════════════════════


class AdaptiveOptimizer:
    """Background auto-tuning engine for per-market strategy parameters.

    Usage:
        optimizer = AdaptiveOptimizer(registry)
        result = await optimizer.tune(
            "strategy.momentum", "crypto", "BTC/USD", price_history)
    """

    def __init__(
        self,
        registry: Optional[StrategyRegistry] = None,
        regime_detector: Optional[MarketRegimeDetector] = None,
        strategy_optimizer: Optional[StrategyOptimizer] = None,
    ):
        self._registry = registry or _build_default_registry()
        self._regime = regime_detector or MarketRegimeDetector()
        self._optimizer = strategy_optimizer or StrategyOptimizer(self._registry)
        self._tune_history: list[dict[str, Any]] = []

    # ── One-Shot Tuning ────────────────────────────────────────────────

    async def tune(
        self,
        strategy_name: str,
        market: str,
        symbol: str,
        price_history: list[float],
        objective: str = "sharpe_ratio",
        method: str = "grid",
        num_steps: int = 4,
        apply_hot_swap: bool = True,
    ) -> dict[str, Any]:
        """Run one tuning cycle: detect regime → optimize → hot-swap.

        Args:
            strategy_name: Registered strategy to tune
            market: Market type (crypto, forex, gold, futures)
            symbol: Trading pair symbol
            price_history: Historical prices (oldest first)
            objective: Optimization objective
            method: Optimization method (grid, scipy, genetic)
            num_steps: Grid granularity for parameter ranges
            apply_hot_swap: If True, update the strategy's market_profiles

        Returns:
            dict with: strategy, market, regime, best_params, best_value,
                       tuning_time_sec, applied
        """
        _started = time.time()

        # 1. Detect current regime
        regime_result = self._regime.detect(price_history, market)
        if not regime_result:
            return {
                "success": False,
                "error": "Insufficient data for regime detection",
                "strategy_name": strategy_name,
                "market": market,
            }

        regime = regime_result["regime"]
        regime_key = regime_result["regime_key"]

        # 2. Build parameter ranges from strategy schema
        param_ranges = _build_param_ranges(
            self._registry, strategy_name, num_steps=num_steps
        )
        if not param_ranges:
            return {
                "success": False,
                "error": f"No tunable parameters for '{strategy_name}'",
                "strategy_name": strategy_name,
                "market": market,
            }

        # 3. Run optimization
        opt_result = await self._optimizer.optimize(
            strategy_name=strategy_name,
            symbol=symbol,
            price_history=price_history,
            parameter_ranges=param_ranges,
            objective=objective,
            method=method,
            num_steps=num_steps,
        )

        best_params = opt_result.get("best_params", {})
        best_value = opt_result.get("best_objective_value", 0.0)

        # 4. Hot-swap into strategy profiles
        applied = False
        if apply_hot_swap and best_params:
            applied = self._hot_swap(strategy_name, regime_key, best_params)

        elapsed = round(time.time() - _started, 2)
        entry = {
            "strategy_name": strategy_name,
            "market": market,
            "symbol": symbol,
            "regime": regime,
            "regime_key": regime_key,
            "regime_confidence": regime_result["confidence"],
            "best_params": best_params,
            "best_objective_value": best_value,
            "objective": objective,
            "method": method,
            "applied": applied,
            "tuning_time_sec": elapsed,
            "tuned_at": datetime.now(timezone.utc).isoformat(),
        }
        self._tune_history.append(entry)

        return entry

    # ── Continuous Loop ────────────────────────────────────────────────

    async def auto_tune_loop(
        self,
        strategy_market_pairs: list[dict[str, Any]],
        price_provider,
        interval_sec: int = 3600,
        max_iterations: int = 0,
    ) -> None:
        """Continuous background tuning loop.

        Call this from a PM2-managed process or cron job.

        Args:
            strategy_market_pairs: List of dicts with keys:
                strategy_name, market, symbol
            price_provider: Async callable(symbol) → list[float] price history
            interval_sec: Seconds between tuning cycles (default 1 hour)
            max_iterations: 0 = run forever, N = stop after N cycles
        """
        iteration = 0
        log.info(
            f"[adaptive] auto-tune loop started — "
            f"{len(strategy_market_pairs)} pairs, interval={interval_sec}s"
        )

        while max_iterations == 0 or iteration < max_iterations:
            iteration += 1
            cycle_start = time.time()

            for pair in strategy_market_pairs:
                name = pair["strategy_name"]
                market = pair["market"]
                symbol = pair["symbol"]

                try:
                    prices = await price_provider(symbol)
                    if not prices or len(prices) < 50:
                        log.warning(
                            f"[adaptive] insufficient data for {name}/{symbol}"
                        )
                        continue

                    result = await self.tune(
                        strategy_name=name,
                        market=market,
                        symbol=symbol,
                        price_history=prices,
                    )

                    status = "✓" if result.get("applied") else "✗"
                    log.info(
                        f"[adaptive] {status} {name}/{market}/{symbol} "
                        f"regime={result.get('regime', '?')} "
                        f"best_{result.get('objective', '?')}="
                        f"{result.get('best_objective_value', '?')}"
                    )

                except Exception as exc:
                    log.error(
                        f"[adaptive] tune failed for {name}/{symbol}: {exc}"
                    )

            cycle_elapsed = time.time() - cycle_start
            log.info(
                f"[adaptive] cycle {iteration} complete in {cycle_elapsed:.1f}s"
            )

            if max_iterations == 0 or iteration < max_iterations:
                wait = max(0, interval_sec - cycle_elapsed)
                await asyncio.sleep(wait)

        log.info(f"[adaptive] auto-tune loop finished after {iteration} cycles")

    # ── Hot-Swap ───────────────────────────────────────────────────────

    def _hot_swap(
        self,
        strategy_name: str,
        regime_key: str,
        params: dict[str, Any],
    ) -> bool:
        """Hot-swap optimized parameters into the strategy's market_profiles.

        Updates:
          - The strategy class's market_profiles dict (for future instances)
          - Any registered live instance's parameters + profiles
        """
        cls = self._registry._classes.get(strategy_name) if hasattr(self._registry, '_classes') else None
        if cls is None:
            log.warning(f"[adaptive] no class for '{strategy_name}' — can't hot-swap")
            return False

        # Update class-level profiles
        if not hasattr(cls, "market_profiles"):
            cls.market_profiles = {}
        cls.market_profiles[regime_key] = dict(params)
        log.info(
            f"[adaptive] hot-swapped {strategy_name} profile for "
            f"'{regime_key}': {list(params.keys())}"
        )

        # Update live instance if registered
        instance = self._registry._instances.get(strategy_name)
        if instance:
            for k, v in params.items():
                instance.parameters[k] = v
            if not hasattr(instance, "market_profiles"):
                instance.market_profiles = {}
            instance.market_profiles[regime_key] = dict(params)
            log.info(f"[adaptive] updated live instance '{strategy_name}'")

        return True

    # ── History ────────────────────────────────────────────────────────

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._tune_history)

    def clear_history(self) -> None:
        self._tune_history.clear()


# ═════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════


def _build_default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    register_builtin_strategies(registry)
    return registry


def _build_param_ranges(
    registry: StrategyRegistry,
    strategy_name: str,
    num_steps: int = 4,
) -> dict[str, tuple]:
    """Build parameter ranges from the strategy's parameter schema.

    Uses schema min/max to construct (min, max) tuples for grid search.
    """
    info = registry.get_strategy_info(strategy_name)
    if not info:
        return {}

    schema = info.get("schema", {})
    ranges = {}
    for name, spec in schema.items():
        lo = spec.get("min")
        hi = spec.get("max")
        if lo is not None and hi is not None:
            # Use (min, max, steps) tuple for grid search granularity
            ranges[name] = (float(lo), float(hi), num_steps)

    return ranges
