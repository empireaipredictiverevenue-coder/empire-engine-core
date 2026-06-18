"""
PREDICITIVE TRADING BOT · STRATEGY FRAMEWORK
=============================================
Adapted from QuantMuse — strategy base, registry, and built-in strategies.

Architecture:
  - StrategyResult: typed output for every strategy execution
  - StrategyBase: abstract base for all strategies (composes skills)
  - StrategyRegistry: registration, discovery, and instance management
  - Built-in strategies: momentum, mean-reversion, breakout, grid

  Strategies sit on TOP of the skill system — they compose multiple
  skills (market.analyze, indicators.calculate, rug.detect, risk.assess)
  into a complete trading pipeline that generates actionable decisions.
"""

import abc
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional

from .base import SkillContext, SkillInput

log = logging.getLogger("trading.strategy")


# ═════════════════════════════════════════════════════════════════════════
# DATA CONTRACTS
# ═════════════════════════════════════════════════════════════════════════


@dataclass
class StrategyResult:
    """Typed output from every strategy execution.

    Adapted from QuantMuse for crypto/Solana trading — replaces
    stock-centric fields (selected_stocks, weights) with token/mint
    fields and action-oriented signals.
    """
    strategy_name: str
    action: str  # "buy", "sell", "hold", "skip"
    symbol: str
    confidence: float = 0.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_pct: float = 0.0  # % of portfolio
    reasoning: str = ""
    token_mint: Optional[str] = None  # Solana mint address
    execution_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parameters: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_signals: Optional[dict[str, Any]] = None  # internal signal data

    def to_dict(self) -> dict:
        """Convert to plain dict for JSON serialization."""
        return {
            "strategy_name": self.strategy_name,
            "action": self.action,
            "symbol": self.symbol,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size_pct": self.position_size_pct,
            "reasoning": self.reasoning,
            "token_mint": self.token_mint,
            "execution_time": self.execution_time,
            "parameters": self.parameters,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


# ═════════════════════════════════════════════════════════════════════════
# STRATEGY BASE
# ═════════════════════════════════════════════════════════════════════════


class StrategyBase(abc.ABC):
    """Abstract base for every trading strategy.

    Subclasses override:
      - name, version, description (class-level metadata)
      - generate_signals() — core strategy logic
      - validate_parameters() — parameter validation
      - get_parameter_schema() — parameter schema for external tools

    Optional overrides:
      - preprocess(), postprocess(), calculate_metrics()

    Built-in: run() orchestrates preprocess → generate → postprocess → metrics.
    Accepts a SkillContext for composing trading skills into the pipeline.
    """

    # ── Metadata (override in subclass) ────────────────────────────────
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = []
    required_skills: list[str] = []
    markets: list[str] = []  # e.g. ["crypto", "forex"]

    # ── Market-specific parameter profiles ────────────────────────────
    # Override in subclass. Keyed by market or (market_regime).
    # e.g. {"crypto": {"lookback_period": 14}, "forex": {"lookback_period": 21}}
    market_profiles: dict[str, dict[str, Any]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.name:
            raise ValueError(f"{cls.__name__} must define a 'name' class attribute")

    def __init__(
        self,
        parameters: Optional[dict[str, Any]] = None,
        skill_context: Optional[SkillContext] = None,
    ):
        self.parameters: dict[str, Any] = parameters or {}
        self.metadata: dict[str, Any] = {}
        self._skill_ctx = skill_context

    @property
    def skill_ctx(self) -> Optional[SkillContext]:
        """Access the skill context for composing trading skills."""
        return self._skill_ctx

    @skill_ctx.setter
    def skill_ctx(self, ctx: Optional[SkillContext]):
        self._skill_ctx = ctx

    # ── Abstract methods ───────────────────────────────────────────────

    @abc.abstractmethod
    async def generate_signals(
        self,
        symbol: str,
        price_data: Optional[dict] = None,
        **kwargs,
    ) -> StrategyResult:
        """Core strategy logic. Must return a StrategyResult.

        Args:
            symbol: Trading pair symbol (e.g. "BTC/USD", "SOL/USDC")
            price_data: Optional current price data dict
        """
        ...

    # ── Market profile loading ─────────────────────────────────────

    def load_market_profile(
        self,
        market: str,
        regime: Optional[str] = None,
    ) -> dict[str, Any]:
        """Load parameter overrides for a given market and optional regime.

        Returns a dict of parameter overrides, or empty dict if no
        profile exists for this market.
        """
        # Try most specific first: market_regime
        if regime:
            key = f"{market}_{regime}"
            if key in self.market_profiles:
                return dict(self.market_profiles[key])
        # Try market-only
        if market in self.market_profiles:
            return dict(self.market_profiles[market])
        return {}

    def apply_market_profile(
        self,
        market: str,
        regime: Optional[str] = None,
    ) -> None:
        """Apply market-specific parameter overrides in-place."""
        overrides = self.load_market_profile(market, regime)
        if overrides:
            for k, v in overrides.items():
                self.parameters[k] = v
            log.debug(
                f"[strategy.{self.name}] applied {market} profile: "
                f"{list(overrides.keys())}"
            )

    def validate_parameters(self, parameters: dict[str, Any]) -> bool:
        """Validate strategy parameters. Override in subclass."""
        return True

    def set_parameters(self, parameters: dict[str, Any]) -> None:
        """Set parameters if validation passes."""
        if self.validate_parameters(parameters):
            self.parameters.update(parameters)
        else:
            raise ValueError(f"Invalid parameters for strategy '{self.name}': {parameters}")

    def get_parameter_info(self) -> dict[str, Any]:
        """Return parameter metadata for external tooling / UI."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "active_parameters": self.parameters,
            "schema": self.get_parameter_schema(),
        }

    def get_parameter_schema(self) -> dict[str, Any]:
        """Return parameter validation schema. Override in subclass."""
        return {}

    # ── Batch signal generation ────────────────────────────────────

    def generate_signals_batch(
        self,
        symbols: list[str],
        current_prices: "np.ndarray",
        indicators: dict[str, "np.ndarray"],
        prices_matrix: "np.ndarray",
    ) -> dict[str, "np.ndarray"]:
        """Synchronous, vectorized signal generation for N symbols.

        Override in subclass. Called by VectorEngine.

        Args:
            symbols: list of symbol names, length N
            current_prices: shape [N] latest price per symbol
            indicators: dict of indicator_name → np.ndarray [N]
            prices_matrix: shape [N, T] full price matrix

        Returns:
            dict of field_name → np.ndarray [N], e.g.:
              {"action": np.array of int (1=buy, -1=sell, 0=hold),
               "confidence": np.array of float,
               "position_size_pct": np.array of float}
        """
        raise NotImplementedError(
            f"{self.name} does not implement generate_signals_batch()"
        )

    # ── Dependency validation ──────────────────────────────────────────

    def validate_dependencies(self) -> bool:
        """Validate that all required_skills are available in the skill context.

        Returns False if required skills are missing, allowing strategies
        to fail fast rather than silently degrading.
        """
        if not self.required_skills:
            return True
        if not self.skill_ctx:
            log.warning(
                f"[strategy.{self.name}] no SkillContext available, "
                f"cannot validate dependencies: {self.required_skills}"
            )
            return False
        missing = [
            req for req in self.required_skills
            if not self.skill_ctx.get_skill(req)
        ]
        if missing:
            log.warning(
                f"[strategy.{self.name}] missing required skills: {missing}"
            )
            return False
        return True

    # ── Pipeline hooks ─────────────────────────────────────────────────

    async def preprocess(self, price_data: Optional[dict]) -> dict:
        """Pre-execution data transformation. Override in subclass."""
        return price_data or {}

    async def postprocess(self, result: StrategyResult) -> StrategyResult:
        """Post-execution result modification. Override in subclass."""
        return result

    async def calculate_metrics(
        self, result: StrategyResult
    ) -> dict[str, Any]:
        """Calculate performance metrics for the result. Override in subclass."""
        return {
            "confidence": result.confidence,
            "position_size_pct": result.position_size_pct,
            "action": result.action,
        }

    # ── Representation ─────────────────────────────────────────────────

    def __str__(self) -> str:
        return f"Strategy({self.name} v{self.version})"

    def __repr__(self) -> str:
        return (
            f"Strategy(name='{self.name}', version='{self.version}', "
            f"params={list(self.parameters.keys())})"
        )


# ═════════════════════════════════════════════════════════════════════════
# STRATEGY REGISTRY
# ═════════════════════════════════════════════════════════════════════════


class StrategyRegistry:
    """Central registry for trading strategies.

    Manages two tiers:
      - _classes: registered strategy classes (for instantiation)
      - _instances: pre-configured strategy instances

    Adapted from QuantMuse with additions:
      - inject_skill() for SkillContext compatibility
      - get_by_market() for market-aware strategy lookup
      - register() alias for simple registration
    """

    def __init__(self):
        self._classes: dict[str, type[StrategyBase]] = {}
        self._instances: dict[str, StrategyBase] = {}
        self._param_cache: dict[str, dict[str, Any]] = {}

    # ── Registration ───────────────────────────────────────────────────

    def register(self, cls: type[StrategyBase]) -> None:
        """Register a strategy class (SkillContext-compatible alias)."""
        self.register_strategy(cls)

    def register_strategy(
        self, strategy_class: type[StrategyBase], strategy_name: Optional[str] = None
    ) -> None:
        """Register a strategy class that inherits from StrategyBase."""
        if not issubclass(strategy_class, StrategyBase):
            raise TypeError(
                f"Expected StrategyBase subclass, got {strategy_class.__name__}"
            )
        name = strategy_name or strategy_class.name
        self._classes[name] = strategy_class
        # Cache parameter info at registration time
        try:
            self._param_cache[name] = strategy_class().get_parameter_info()
        except Exception:
            self._param_cache[name] = {"name": name, "error": "failed to extract params"}
        log.info(f"[strategy.registry] registered class '{name}'")

    def register_instance(
        self, strategy_instance: StrategyBase, strategy_name: Optional[str] = None
    ) -> None:
        """Register a pre-configured strategy instance."""
        if not isinstance(strategy_instance, StrategyBase):
            raise TypeError(
                f"Expected StrategyBase instance, got {type(strategy_instance).__name__}"
            )
        name = strategy_name or strategy_instance.name
        self._instances[name] = strategy_instance
        # Cache parameter info at registration time
        try:
            self._param_cache[name] = strategy_instance.get_parameter_info()
        except Exception:
            self._param_cache[name] = {"name": name, "error": "failed to extract params"}
        log.info(f"[strategy.registry] registered instance '{name}'")

    def inject_skill(self, name: str, skill) -> None:
        """SkillContext-compatible: register a strategy as if it were a skill."""
        if isinstance(skill, type) and issubclass(skill, StrategyBase):
            self.register_strategy(skill, strategy_name=name)
        elif isinstance(skill, StrategyBase):
            self.register_instance(skill, strategy_name=name)
        else:
            raise TypeError(f"Cannot register {type(skill)} as a strategy")

    # ── Discovery ──────────────────────────────────────────────────────

    def list_strategies(self) -> list[str]:
        """Return names of all registered strategy classes."""
        return list(self._classes.keys())

    def list_instances(self) -> list[str]:
        """Return names of all registered strategy instances."""
        return list(self._instances.keys())

    def list_all(self) -> list[str]:
        """Return all registered strategy names (classes + instances)."""
        return sorted(set(self._classes.keys()) | set(self._instances.keys()))

    def get_by_market(self, market: str) -> list[str]:
        """Get strategy names that support a given market (e.g. 'crypto')."""
        results = []
        for name, cls in self._classes.items():
            if market.lower() in [m.lower() for m in getattr(cls, "markets", [])]:
                results.append(name)
        return results

    # ── Retrieval ──────────────────────────────────────────────────────

    def get_strategy(self, strategy_name: str) -> Optional[StrategyBase]:
        """Retrieve a registered strategy instance by name."""
        # Check instances first, then try to create from class
        if strategy_name in self._instances:
            return self._instances[strategy_name]
        return None

    def create_strategy(
        self,
        strategy_name: str,
        parameters: Optional[dict[str, Any]] = None,
        skill_context: Optional[SkillContext] = None,
    ) -> Optional[StrategyBase]:
        """Instantiate a registered strategy class with parameters."""
        cls = self._classes.get(strategy_name)
        if cls is None:
            log.warning(f"[strategy.registry] no class registered for '{strategy_name}'")
            return None

        instance = cls(parameters=parameters, skill_context=skill_context)
        log.info(f"[strategy.registry] created '{strategy_name}' instance")
        # Auto-apply market profile if market context is provided in kwargs
        if "market" in (parameters or {}):
            market = parameters.get("market")
            regime = parameters.get("regime") if parameters else None
            instance.apply_market_profile(market, regime)
        return instance

    def get_strategy_info(self, strategy_name: str) -> Optional[dict[str, Any]]:
        """Return parameter metadata for a strategy (from cache)."""
        return self._param_cache.get(strategy_name)

    # ── Management ─────────────────────────────────────────────────────

    def remove_strategy(self, strategy_name: str) -> bool:
        """Remove a strategy from the registry. Returns True if found."""
        removed = False
        if strategy_name in self._classes:
            del self._classes[strategy_name]
            removed = True
        if strategy_name in self._instances:
            del self._instances[strategy_name]
            removed = True
        self._param_cache.pop(strategy_name, None)
        return removed

    def clear(self) -> None:
        """Remove all registered strategies."""
        self._classes.clear()
        self._instances.clear()
        self._param_cache.clear()
        log.info("[strategy.registry] cleared all strategies")

    # ── Python protocol ────────────────────────────────────────────────

    def __contains__(self, strategy_name: str) -> bool:
        return strategy_name in self._classes or strategy_name in self._instances

    def __len__(self) -> int:
        return len(set(self._classes.keys()) | set(self._instances.keys()))

    def __repr__(self) -> str:
        return (
            f"StrategyRegistry(classes={list(self._classes.keys())}, "
            f"instances={list(self._instances.keys())})"
        )


# ═════════════════════════════════════════════════════════════════════════
# BUILT-IN STRATEGIES
# ═════════════════════════════════════════════════════════════════════════


class MomentumStrategy(StrategyBase):
    """Buy tokens showing strong upward momentum, sell when momentum fades.

    Uses trading.indicators.calculate for RSI + MACD and
    trading.market.analyze for trend confirmation.
    """
    name = "strategy.momentum"
    version = "1.0.0"
    description = "Momentum-based strategy — enter on strength, exit on weakness"
    tags = ["mode:execution", "risk:medium"]
    required_skills = [
        "trading.indicators.calculate",
        "trading.market.analyze",
    ]
    markets = ["crypto", "forex"]

    # Market-specific parameter presets
    market_profiles = {
        "crypto": {
            "lookback_period": 14, "rsi_threshold": 60, "confidence_min": 0.6,
            "take_profit_pct": 0.15, "stop_loss_pct": 0.08,
        },
        "crypto_volatile": {
            "lookback_period": 10, "rsi_threshold": 65, "confidence_min": 0.7,
            "take_profit_pct": 0.20, "stop_loss_pct": 0.06,
        },
        "crypto_calm": {
            "lookback_period": 21, "rsi_threshold": 55, "confidence_min": 0.55,
            "take_profit_pct": 0.10, "stop_loss_pct": 0.10,
        },
        "forex": {
            "lookback_period": 21, "rsi_threshold": 55, "confidence_min": 0.55,
            "take_profit_pct": 0.05, "stop_loss_pct": 0.03,
        },
    }

    def validate_parameters(self, parameters: dict[str, Any]) -> bool:
        required = ["lookback_period", "rsi_threshold", "confidence_min"]
        return all(k in parameters for k in required)

    def get_parameter_schema(self) -> dict[str, Any]:
        return {
            "lookback_period": {"type": "int", "default": 14, "min": 5, "max": 200},
            "rsi_threshold": {"type": "float", "default": 60.0, "min": 0, "max": 100},
            "confidence_min": {"type": "float", "default": 0.6, "min": 0, "max": 1},
            "take_profit_pct": {"type": "float", "default": 0.15, "min": 0.01, "max": 1},
            "stop_loss_pct": {"type": "float", "default": 0.08, "min": 0.01, "max": 0.5},
        }

    async def generate_signals(
        self,
        symbol: str,
        price_data: Optional[dict] = None,
        **kwargs,
    ) -> StrategyResult:
        lookback = int(self.parameters.get("lookback_period", 14))
        rsi_threshold = float(self.parameters.get("rsi_threshold", 60))
        confidence_min = float(self.parameters.get("confidence_min", 0.6))
        tp_pct = float(self.parameters.get("take_profit_pct", 0.15))
        sl_pct = float(self.parameters.get("stop_loss_pct", 0.08))

        # Compose skills via SkillContext
        indicators = {}
        market_analysis = {}
        if self.skill_ctx:
            indicators_skill = self.skill_ctx.get_skill("trading.indicators.calculate")
            if indicators_skill:
                ind_out = await indicators_skill.run(SkillInput(params={
                    "symbol": symbol,
                    "indicators": ["RSI", "MACD", "MA"],
                    "ma_periods": [9, 21],
                }))
                if ind_out.success and ind_out.data:
                    indicators = ind_out.data.get("indicators", {})

            market_skill = self.skill_ctx.get_skill("trading.market.analyze")
            if market_skill:
                mkt_out = await market_skill.run(SkillInput(params={
                    "market": "crypto",
                    "symbol": symbol,
                    "timeframe": "1h",
                }))
                if mkt_out.success and mkt_out.data:
                    market_analysis = mkt_out.data

        # Simple momentum heuristic
        rsi = indicators.get("RSI", {})
        macd = indicators.get("MACD", {})
        trend = market_analysis.get("trend", "neutral")

        rsi_signal = rsi.get("signal", "neutral")
        macd_signal = macd.get("signal_text", "cross_pending")

        # Scoring
        score = 0.5  # neutral baseline
        reasons = []

        if rsi_signal == "bullish" or rsi.get("value", 50) > rsi_threshold:
            score += 0.2
            reasons.append(f"RSI momentum positive")
        elif rsi_signal == "bearish":
            score -= 0.2
            reasons.append(f"RSI bearish")

        if macd_signal == "bullish_cross":
            score += 0.15
            reasons.append("MACD bullish cross")
        elif macd_signal == "bearish_cross":
            score -= 0.15
            reasons.append("MACD bearish cross")

        if trend == "upward" or trend == "watching":
            score += 0.1
            reasons.append(f"Market trend: {trend}")
        elif trend == "downward":
            score -= 0.15

        # Decision
        current_price = price_data.get("price") if price_data else None
        if score >= confidence_min:
            action = "buy"
            position_pct = min(0.2, (score - confidence_min) * 2)
        elif score <= 0.3:
            action = "sell"
            position_pct = 0.0
        else:
            action = "hold"
            position_pct = 0.0

        return StrategyResult(
            strategy_name=self.name,
            action=action,
            symbol=symbol,
            confidence=round(score, 3),
            entry_price=current_price,
            stop_loss=round(current_price * (1 - sl_pct), 6) if current_price else None,
            take_profit=round(current_price * (1 + tp_pct), 6) if current_price else None,
            position_size_pct=round(position_pct, 3),
            reasoning="; ".join(reasons) if reasons else "Insufficient signal data",
            parameters=self.parameters,
            raw_signals={
                "rsi": rsi,
                "macd": macd,
                "trend": trend,
                "score": score,
            },
        )

    def generate_signals_batch(
        self,
        symbols: list[str],
        current_prices: "np.ndarray",
        indicators: dict[str, "np.ndarray"],
        prices_matrix: "np.ndarray",
    ) -> dict[str, "np.ndarray"]:
        """Batch momentum signals — vectorized RSI + MACD scoring."""
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("numpy required for batch execution")

        n = len(symbols)
        lookback = int(self.parameters.get("lookback_period", 14))
        rsi_threshold = float(self.parameters.get("rsi_threshold", 60))
        confidence_min = float(self.parameters.get("confidence_min", 0.6))
        tp_pct = float(self.parameters.get("take_profit_pct", 0.15))
        sl_pct = float(self.parameters.get("stop_loss_pct", 0.08))

        # Extract indicator arrays (handle missing)
        rsi = indicators.get("RSI", np.full(n, 50.0))
        macd_signal_text = indicators.get("MACD_SIGNAL_TEXT", np.full(n, "neutral", dtype=object))
        momentum_5d = indicators.get("momentum_5d", np.full(n, 0.0))

        # Scoring
        score = np.full(n, 0.5, dtype=np.float64)

        # RSI component
        score += np.where(np.isfinite(rsi) & (rsi > rsi_threshold), 0.2, 0.0)
        score -= np.where(np.isfinite(rsi) & (rsi < 30), 0.2, 0.0)

        # MACD component
        score += np.where(macd_signal_text == "bullish_cross", 0.15, 0.0)
        score -= np.where(macd_signal_text == "bearish_cross", 0.15, 0.0)
        score += np.where(macd_signal_text == "bullish", 0.08, 0.0)
        score -= np.where(macd_signal_text == "bearish", 0.08, 0.0)

        # Momentum confirmation
        score += np.where(np.isfinite(momentum_5d) & (momentum_5d > 0), 0.05, 0.0)

        # Decision: 1=buy, -1=sell, 0=hold
        action = np.zeros(n, dtype=np.int8)
        action[score >= confidence_min] = 1  # buy
        action[score <= 0.3] = -1  # sell

        # Position sizing
        position_pct = np.zeros(n, dtype=np.float64)
        buy_mask = score >= confidence_min
        position_pct[buy_mask] = np.minimum(0.2, (score[buy_mask] - confidence_min) * 2)

        # Stop loss / take profit
        stop_loss = np.where(np.isfinite(current_prices) & (current_prices > 0),
                             current_prices * (1 - sl_pct), np.nan)
        take_profit = np.where(np.isfinite(current_prices) & (current_prices > 0),
                               current_prices * (1 + tp_pct), np.nan)

        return {
            "action": action,
            "confidence": np.round(score.astype(np.float64), 3),
            "entry_price": current_prices,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size_pct": np.round(position_pct, 3),
        }


class MeanReversionStrategy(StrategyBase):
    """Buy when price deviates significantly below moving average, sell on reversion.

    Uses trading.indicators.calculate for MA + Bollinger Bands.
    """
    name = "strategy.mean_reversion"
    version = "1.0.0"
    description = "Mean-reversion strategy — buy below MA, sell at mean"
    tags = ["mode:execution", "risk:medium"]
    required_skills = ["trading.indicators.calculate"]
    markets = ["crypto", "forex", "gold"]

    market_profiles = {
        "crypto": {"ma_period": 50, "deviation_threshold": 0.05, "confidence_min": 0.65},
        "crypto_volatile": {"ma_period": 30, "deviation_threshold": 0.08, "confidence_min": 0.70},
        "forex": {"ma_period": 100, "deviation_threshold": 0.03, "confidence_min": 0.60},
        "gold": {"ma_period": 60, "deviation_threshold": 0.04, "confidence_min": 0.65},
    }

    def validate_parameters(self, parameters: dict[str, Any]) -> bool:
        return "ma_period" in parameters and "deviation_threshold" in parameters

    def get_parameter_schema(self) -> dict[str, Any]:
        return {
            "ma_period": {"type": "int", "default": 50, "min": 5, "max": 200},
            "deviation_threshold": {"type": "float", "default": 0.05, "min": 0.01, "max": 0.2},
            "confidence_min": {"type": "float", "default": 0.65, "min": 0, "max": 1},
        }

    async def generate_signals(
        self,
        symbol: str,
        price_data: Optional[dict] = None,
        **kwargs,
    ) -> StrategyResult:
        ma_period = int(self.parameters.get("ma_period", 50))
        threshold = float(self.parameters.get("deviation_threshold", 0.05))
        confidence_min = float(self.parameters.get("confidence_min", 0.65))

        indicators = {}
        current_price = price_data.get("price") if price_data else None

        if self.skill_ctx:
            skill = self.skill_ctx.get_skill("trading.indicators.calculate")
            if skill:
                out = await skill.run(SkillInput(params={
                    "symbol": symbol,
                    "indicators": ["MA", "BB"],
                    "ma_type": "SMA",
                    "ma_periods": [ma_period],
                }))
                if out.success and out.data:
                    indicators = out.data.get("indicators", {})

        mas = indicators.get("MA", {}).get("periods", {})
        bb = indicators.get("BB", {})

        # Score based on price vs MA deviation
        score = 0.5
        reasons = []

        if current_price and mas:
            ma_val = mas.get(str(ma_period), 0)
            if ma_val and isinstance(ma_val, (int, float)) and ma_val > 0:
                deviation = (current_price - ma_val) / ma_val
                if deviation < -threshold:
                    score += 0.3
                    reasons.append(f"Price {abs(deviation)*100:.1f}% below MA{ma_period} — buy signal")
                elif deviation > threshold:
                    score -= 0.3
                    reasons.append(f"Price {deviation*100:.1f}% above MA{ma_period} — overbought")
                else:
                    reasons.append(f"Price near MA{ma_period} (±{abs(deviation)*100:.1f}%)")

        if score >= confidence_min:
            action = "buy"
            position_pct = 0.15
        elif score <= 0.3:
            action = "sell"
            position_pct = 0.0
        else:
            action = "hold"
            position_pct = 0.0

        return StrategyResult(
            strategy_name=self.name,
            action=action,
            symbol=symbol,
            confidence=round(score, 3),
            entry_price=current_price,
            position_size_pct=round(position_pct, 3),
            reasoning="; ".join(reasons) if reasons else "Insufficient MA data",
            parameters=self.parameters,
            raw_signals={"indicators": indicators, "score": score},
        )

    def generate_signals_batch(
        self,
        symbols: list[str],
        current_prices: "np.ndarray",
        indicators: dict[str, "np.ndarray"],
        prices_matrix: "np.ndarray",
    ) -> dict[str, "np.ndarray"]:
        """Batch mean-reversion signals — vectorized MA deviation scoring."""
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("numpy required for batch execution")

        n = len(symbols)
        ma_period = int(self.parameters.get("ma_period", 50))
        threshold = float(self.parameters.get("deviation_threshold", 0.05))
        confidence_min = float(self.parameters.get("confidence_min", 0.65))

        sma_key = f"sma_{ma_period}"
        sma = indicators.get(sma_key, np.full(n, np.nan, dtype=np.float64))

        score = np.full(n, 0.5, dtype=np.float64)

        # Deviation from SMA
        with np.errstate(divide="ignore", invalid="ignore"):
            deviation = (current_prices - sma) / sma  # [N]

        below_ma = np.isfinite(deviation) & (deviation < -threshold)
        above_ma = np.isfinite(deviation) & (deviation > threshold)

        score[below_ma] += 0.3  # buy signal
        score[above_ma] -= 0.3  # overbought

        action = np.zeros(n, dtype=np.int8)
        action[score >= confidence_min] = 1
        action[score <= 0.3] = -1

        position_pct = np.zeros(n, dtype=np.float64)
        position_pct[score >= confidence_min] = 0.15

        return {
            "action": action,
            "confidence": np.round(score.astype(np.float64), 3),
            "entry_price": current_prices,
            "position_size_pct": np.round(position_pct, 3),
        }


class BreakoutStrategy(StrategyBase):
    """Enter on confirmed breakouts with volume confirmation.

    Uses trading.indicators.calculate for Bollinger Bands and VWAP.
    """
    name = "strategy.breakout"
    version = "1.0.0"
    description = "Breakout strategy — enter on volume-confirmed level breaks"
    tags = ["mode:execution", "risk:high"]
    required_skills = ["trading.indicators.calculate"]
    markets = ["crypto"]

    market_profiles = {
        "crypto": {"breakout_threshold": 0.03, "confidence_min": 0.7, "volume_multiplier": 1.5},
        "crypto_volatile": {"breakout_threshold": 0.05, "confidence_min": 0.80, "volume_multiplier": 2.0},
        "crypto_calm": {"breakout_threshold": 0.02, "confidence_min": 0.65, "volume_multiplier": 1.2},
    }

    def validate_parameters(self, parameters: dict[str, Any]) -> bool:
        return "breakout_threshold" in parameters

    def get_parameter_schema(self) -> dict[str, Any]:
        return {
            "breakout_threshold": {"type": "float", "default": 0.03, "min": 0.01, "max": 0.1},
            "volume_multiplier": {"type": "float", "default": 1.5, "min": 1, "max": 5},
            "confidence_min": {"type": "float", "default": 0.7, "min": 0, "max": 1},
        }

    async def generate_signals(
        self,
        symbol: str,
        price_data: Optional[dict] = None,
        **kwargs,
    ) -> StrategyResult:
        threshold = float(self.parameters.get("breakout_threshold", 0.03))
        confidence_min = float(self.parameters.get("confidence_min", 0.7))
        current_price = price_data.get("price") if price_data else None

        indicators = {}
        if self.skill_ctx:
            skill = self.skill_ctx.get_skill("trading.indicators.calculate")
            if skill:
                out = await skill.run(SkillInput(params={
                    "symbol": symbol,
                    "indicators": ["BB", "VWAP", "OBV"],
                }))
                if out.success and out.data:
                    indicators = out.data.get("indicators", {})

        bb = indicators.get("BB", {})
        vwap = indicators.get("VWAP", {})
        obv = indicators.get("OBV", {})

        score = 0.5
        reasons = []

        if current_price:
            bb_upper = bb.get("upper", 0)
            if bb_upper and isinstance(bb_upper, (int, float)) and bb_upper > 0:
                if current_price > bb_upper * (1 + threshold):
                    score += 0.25
                    reasons.append("Price above upper Bollinger Band — breakout")
                elif bb.get("lower") and current_price < bb["lower"] * (1 - threshold):
                    score -= 0.25
                    reasons.append("Price below lower band — breakdown")

            vwap_value = vwap.get("value", 0)
            if vwap_value and isinstance(vwap_value, (int, float)):
                if current_price > vwap_value:
                    score += 0.1
                    reasons.append("Price above VWAP")
                else:
                    score -= 0.05

        if obv.get("trend") == "upward":
            score += 0.1
            reasons.append("OBV confirming trend")

        if score >= confidence_min:
            action = "buy"
            position_pct = 0.25
        elif score <= 0.25:
            action = "sell"
            position_pct = 0.0
        else:
            action = "hold"
            position_pct = 0.0

        return StrategyResult(
            strategy_name=self.name,
            action=action,
            symbol=symbol,
            confidence=round(score, 3),
            entry_price=current_price,
            position_size_pct=round(position_pct, 3),
            reasoning="; ".join(reasons) if reasons else "No breakout signal",
            parameters=self.parameters,
            raw_signals={"indicators": indicators, "score": score},
        )

    def generate_signals_batch(
        self,
        symbols: list[str],
        current_prices: "np.ndarray",
        indicators: dict[str, "np.ndarray"],
        prices_matrix: "np.ndarray",
    ) -> dict[str, "np.ndarray"]:
        """Batch breakout signals — vectorized BB + OBV scoring."""
        try:
            import numpy as np
        except ImportError:
            raise RuntimeError("numpy required for batch execution")

        n = len(symbols)
        threshold = float(self.parameters.get("breakout_threshold", 0.03))
        confidence_min = float(self.parameters.get("confidence_min", 0.7))

        bb_upper = indicators.get("BB_UPPER", np.full(n, np.nan, dtype=np.float64))
        bb_lower = indicators.get("BB_LOWER", np.full(n, np.nan, dtype=np.float64))

        score = np.full(n, 0.5, dtype=np.float64)

        # Breakout above upper band
        with np.errstate(divide="ignore", invalid="ignore"):
            price_vs_upper = current_prices / bb_upper
        above_upper = np.isfinite(price_vs_upper) & (price_vs_upper > (1 + threshold))
        score[above_upper] += 0.25

        # Breakdown below lower band
        with np.errstate(divide="ignore", invalid="ignore"):
            price_vs_lower = current_prices / bb_lower
        below_lower = np.isfinite(price_vs_lower) & (price_vs_lower < (1 - threshold))
        score[below_lower] -= 0.25

        action = np.zeros(n, dtype=np.int8)
        action[score >= confidence_min] = 1
        action[score <= 0.25] = -1

        position_pct = np.zeros(n, dtype=np.float64)
        position_pct[score >= confidence_min] = 0.25

        return {
            "action": action,
            "confidence": np.round(score.astype(np.float64), 3),
            "entry_price": current_prices,
            "position_size_pct": np.round(position_pct, 3),
        }


# ═════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════════

BUILTIN_STRATEGIES: list[type[StrategyBase]] = [
    MomentumStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
]


def register_builtin_strategies(registry: StrategyRegistry) -> None:
    """Register all built-in strategies into a StrategyRegistry."""
    for cls in BUILTIN_STRATEGIES:
        registry.register_strategy(cls)
    log.info(f"[strategy] registered {len(BUILTIN_STRATEGIES)} built-in strategies")


def get_strategy_names() -> list[str]:
    """Return all built-in strategy names."""
    return [cls.name for cls in BUILTIN_STRATEGIES]
