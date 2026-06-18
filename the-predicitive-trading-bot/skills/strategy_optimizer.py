"""
PREDICITIVE TRADING BOT · STRATEGY OPTIMIZER
===============================================
Parameter optimization for trading strategies.

Adapted from QuantMuse StrategyOptimizer with these changes:
  - Works with our StrategyRunner (async, no pandas)
  - Supports 3 optimization methods: scipy L-BFGS-B, differential evolution,
    and exhaustive grid search
  - Graceful fallback: if scipy is not installed, grid search is always available
  - Objective functions: sharpe_ratio, total_return, win_rate, profit_factor
  - Parameter ranges use our strategy get_parameter_schema() for defaults

Architecture:
  - StrategyOptimizer: main optimizer class
  - _optimize_scipy(): L-BFGS-B via scipy.optimize.minimize
  - _optimize_genetic(): differential evolution via scipy
  - _optimize_grid(): exhaustive grid search (always available)
  - _evaluate_params(): runs strategy evaluation for a candidate parameter set

No scipy dependency at import time — graceful ImportError handling with
clear user messaging when trying to use scipy/genetic without it installed.
"""

import asyncio
import logging
import time
import itertools
from datetime import datetime, timezone
from typing import Any, Optional, Callable

from .strategy import StrategyRegistry
from .strategy_runner import StrategyRunner
from .base import SkillContext

log = logging.getLogger("trading.optimizer")

# ── Scipy availability ──────────────────────────────────────────────────

try:
    from scipy.optimize import minimize, differential_evolution

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    log.info("[optimizer] scipy not available — only grid search is supported")


# ═════════════════════════════════════════════════════════════════════════
# STRATEGY OPTIMIZER
# ═════════════════════════════════════════════════════════════════════════


class StrategyOptimizer:
    """Optimizer for strategy parameters.

    Adapted from QuantMuse StrategyOptimizer.

    Supports 3 optimization methods:
      - "scipy": L-BFGS-B via scipy.optimize.minimize
      - "genetic": differential evolution via scipy.optimize.differential_evolution
      - "grid": exhaustive grid search over parameter values

    Objective functions:
      - "sharpe_ratio": risk-adjusted return
      - "total_return": absolute percentage return
      - "win_rate": fraction of winning trades
      - "profit_factor": gross profit / gross loss

    Usage:
        registry = StrategyRegistry()
        register_builtin_strategies(registry)
        optimizer = StrategyOptimizer(registry)

        result = await optimizer.optimize(
            "strategy.momentum",
            symbol="BTC/USD",
            price_history=prices,
            parameter_ranges={
                "lookback_period": (5, 50),
                "rsi_threshold": (50.0, 80.0),
                "confidence_min": (0.4, 0.8),
            },
            objective="sharpe_ratio",
            method="genetic",
        )
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
        self._history: list[dict[str, Any]] = []

    # ── Main API ────────────────────────────────────────────────────────

    async def optimize(
        self,
        strategy_name: str,
        symbol: str,
        price_history: list[float],
        parameter_ranges: dict[str, tuple],
        objective: str = "sharpe_ratio",
        method: str = "grid",
        initial_capital: float = 10000.0,
        **kwargs,
    ) -> dict[str, Any]:
        """Optimize strategy parameters.

        Args:
            strategy_name: Registered strategy name to optimize
            symbol: Trading pair symbol
            price_history: Historical price list (oldest first)
            parameter_ranges: Dict mapping param_name → (min, max) for
                              continuous params, or param_name → [val1, val2, ...]
                              for discrete params (grid search)
            objective: "sharpe_ratio", "total_return", "win_rate", or "profit_factor"
            method: "scipy", "genetic", or "grid"
            initial_capital: Starting capital for evaluation
            **kwargs: Passed to optimizer (maxiter, popsize, seed, etc.)

        Returns:
            dict with: strategy_name, method, objective, best_params,
                       best_objective_value, objective_name, all_results
                       (grid only), evaluation_time_sec, success, note
        """
        _started = time.time()

        # Validate method availability
        if method in ("scipy", "genetic") and not HAS_SCIPY:
            log.warning(
                f"[optimizer] scipy not installed — falling back to grid search "
                f"for method '{method}'"
            )
            method = "grid"

        # Validate strategy exists
        if strategy_name not in self._registry:
            return {
                "success": False,
                "error": f"Strategy '{strategy_name}' not found in registry",
            }

        # Build objective function (negated for minimization).
        # Run evaluations in a fresh event loop since scipy calls
        # _objective synchronously — we can't use a running loop.
        def _objective(params_list: list[float]) -> float:
            param_names = list(parameter_ranges.keys())
            params = dict(zip(param_names, params_list))
            new_loop = asyncio.new_event_loop()
            try:
                obj_val = new_loop.run_until_complete(
                    self._evaluate_params(
                        strategy_name,
                        symbol,
                        price_history,
                        params,
                        objective,
                        initial_capital,
                    )
                )
            except Exception:
                log.debug(
                    f"[optimizer] objective eval failed for params "
                    f"{ {k: round(v, 4) if isinstance(v, float) else v for k, v in params.items()} }",
                    exc_info=True,
                )
                obj_val = 0.0
            finally:
                new_loop.close()
            return -obj_val

        if method == "grid":
            result = await self._optimize_grid(
                strategy_name,
                symbol,
                price_history,
                parameter_ranges,
                objective,
                initial_capital,
                **kwargs,
            )
        elif method == "scipy":
            result = self._optimize_scipy(
                _objective,
                parameter_ranges,
                strategy_name=strategy_name,
                objective=objective,
                **kwargs,
            )
        elif method == "genetic":
            result = self._optimize_genetic(
                _objective,
                parameter_ranges,
                strategy_name=strategy_name,
                objective=objective,
                **kwargs,
            )
        else:
            return {"success": False, "error": f"Unknown method: {method}"}

        result["evaluation_time_sec"] = round(time.time() - _started, 2)
        self._history.append(result)
        return result

    async def _evaluate_params(
        self,
        strategy_name: str,
        symbol: str,
        price_history: list[float],
        parameters: dict[str, Any],
        objective: str,
        initial_capital: float,
    ) -> float:
        """Run strategy evaluation and return the objective value."""
        eval_result = await self._runner.evaluate_strategy(
            strategy_name,
            symbol,
            price_history,
            parameters=parameters,
            initial_capital=initial_capital,
        )

        if objective == "sharpe_ratio":
            return eval_result.get("sharpe_ratio", 0.0)
        elif objective == "total_return":
            return eval_result.get("total_return_pct", 0.0)
        elif objective == "win_rate":
            return eval_result.get("win_rate", 0.0)
        elif objective == "profit_factor":
            pf = eval_result.get("profit_factor", 0.0)
            return 0.0 if pf == float("inf") else pf
        else:
            log.warning(f"[optimizer] unknown objective '{objective}', using sharpe")
            return eval_result.get("sharpe_ratio", 0.0)

    # ── Scipy L-BFGS-B ──────────────────────────────────────────────────

    def _optimize_scipy(
        self,
        objective_func: Callable[[list[float]], float],
        parameter_ranges: dict[str, tuple],
        strategy_name: str = "",
        objective: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Optimize using scipy.optimize.minimize with L-BFGS-B.

        Adapted from QuantMuse _optimize_scipy.
        """
        if not HAS_SCIPY:
            return {
                "success": False,
                "error": "scipy not installed",
                "strategy_name": strategy_name,
                "method": "scipy",
            }

        param_names = list(parameter_ranges.keys())
        bounds = list(parameter_ranges.values())

        # Initial guess: middle of each range
        x0 = [(lo + hi) / 2.0 for lo, hi in bounds]

        try:
            result = minimize(
                objective_func,
                x0,
                method="L-BFGS-B",
                bounds=bounds,
                options={
                    "maxiter": kwargs.get("maxiter", 200),
                    "ftol": kwargs.get("ftol", 1e-8),
                },
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"Scipy optimization failed: {exc}",
                "strategy_name": strategy_name,
                "method": "scipy",
            }

        best_params = dict(zip(param_names, result.x.tolist()))
        best_value = -result.fun  # Un-negate

        return {
            "success": result.success,
            "strategy_name": strategy_name,
            "method": "scipy",
            "objective": objective,
            "best_params": best_params,
            "best_objective_value": round(best_value, 6),
            "iterations": result.nit if hasattr(result, "nit") else 0,
            "optimizer_message": str(result.message),
        }

    # ── Differential Evolution (Genetic) ────────────────────────────────

    def _optimize_genetic(
        self,
        objective_func: Callable[[list[float]], float],
        parameter_ranges: dict[str, tuple],
        strategy_name: str = "",
        objective: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Optimize using differential evolution (genetic algorithm).

        Adapted from QuantMuse _optimize_genetic.
        """
        if not HAS_SCIPY:
            return {
                "success": False,
                "error": "scipy not installed",
                "strategy_name": strategy_name,
                "method": "genetic",
            }

        param_names = list(parameter_ranges.keys())
        bounds = list(parameter_ranges.values())

        try:
            result = differential_evolution(
                objective_func,
                bounds,
                maxiter=kwargs.get("maxiter", 500),
                popsize=kwargs.get("popsize", 15),
                seed=kwargs.get("seed", 42),
                tol=kwargs.get("tol", 1e-8),
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"Genetic optimization failed: {exc}",
                "strategy_name": strategy_name,
                "method": "genetic",
            }

        best_params = dict(zip(param_names, result.x.tolist()))
        best_value = -result.fun

        return {
            "success": result.success,
            "strategy_name": strategy_name,
            "method": "genetic",
            "objective": objective,
            "best_params": best_params,
            "best_objective_value": round(best_value, 6),
            "iterations": result.nit if hasattr(result, "nit") else 0,
            "optimizer_message": str(result.message),
        }

    # ── Grid Search ─────────────────────────────────────────────────────

    async def _optimize_grid(
        self,
        strategy_name: str,
        symbol: str,
        price_history: list[float],
        parameter_ranges: dict[str, Any],
        objective: str,
        initial_capital: float,
        **kwargs,
    ) -> dict[str, Any]:
        """Exhaustive grid search over discrete parameter values.

        Each parameter value can be:
          - A list of discrete values: [5, 10, 15, 20]
          - A tuple of (min, max) — will be converted to `num_steps` points
          - A tuple of (min, max, num_steps) for custom granularity

        Adapted from QuantMuse grid_search_optimization.
        """
        param_names = list(parameter_ranges.keys())
        default_steps = kwargs.get("num_steps", 5)

        # Build the grid: convert ranges to discrete value lists
        # Convention: tuples are ranges (min, max) or (min, max, steps);
        # lists are discrete values to try.
        grid_values: list[list] = []
        for name in param_names:
            val = parameter_ranges[name]
            if isinstance(val, tuple):
                if len(val) == 2 and isinstance(val[0], (int, float)) and isinstance(val[1], (int, float)):
                    # (min, max) — generate evenly spaced points
                    lo, hi = val
                    steps = default_steps
                    grid_values.append(_linspace(lo, hi, steps))
                elif len(val) == 3 and all(isinstance(v, (int, float)) for v in val):
                    # (min, max, steps)
                    lo, hi, steps = val
                    grid_values.append(_linspace(lo, hi, int(steps)))
                else:
                    grid_values.append(list(val))
            elif isinstance(val, list):
                # List of discrete values to try
                grid_values.append(list(val))
            else:
                grid_values.append([val])

        total_combos = 1
        for gv in grid_values:
            total_combos *= len(gv)
        log.info(
            f"[optimizer] grid search: {total_combos} combinations "
            f"across {len(param_names)} parameters"
        )

        best_value: float = float("-inf")
        best_params: dict[str, Any] = {}
        all_results: list[dict[str, Any]] = []

        for combo in itertools.product(*grid_values):
            params = dict(zip(param_names, combo))

            try:
                obj_val = await self._evaluate_params(
                    strategy_name,
                    symbol,
                    price_history,
                    params,
                    objective,
                    initial_capital,
                )

                entry = {
                    "params": params.copy(),
                    "objective_value": round(obj_val, 6),
                }
                all_results.append(entry)

                if obj_val > best_value:
                    best_value = obj_val
                    best_params = params.copy()

            except Exception as exc:
                log.warning(f"[optimizer] grid eval failed for {params}: {exc}")
                continue

        return {
            "success": True,
            "strategy_name": strategy_name,
            "method": "grid",
            "objective": objective,
            "best_params": best_params,
            "best_objective_value": round(best_value, 6),
            "total_combinations": total_combos,
            "all_results_sorted": sorted(
                all_results, key=lambda r: r["objective_value"], reverse=True
            )[:kwargs.get("top_n", 10)],
            "all_results_count": len(all_results),
        }

    # ── History ─────────────────────────────────────────────────────────

    def get_history(
        self, strategy_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Return optimization history, optionally filtered."""
        if strategy_name:
            return [
                h for h in self._history
                if h.get("strategy_name") == strategy_name
            ]
        return list(self._history)

    def clear_history(self) -> None:
        """Clear optimization history."""
        self._history.clear()
        log.info("[optimizer] history cleared")


# ═════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════


def _linspace(start: float, stop: float, num: int) -> list[float]:
    """Generate `num` evenly spaced floats between start and stop."""
    if num <= 1:
        return [start]
    step = (stop - start) / (num - 1)
    return [start + i * step for i in range(num)]
