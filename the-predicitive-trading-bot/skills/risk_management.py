"""
PREDICITIVE TRADING BOT · PORTFOLIO RISK MANAGEMENT
=====================================================
Portfolio-level risk management adapted from QuantMuse.

Features:
  - Value at Risk (VaR): parametric + historical
  - Kelly criterion position sizing
  - Portfolio concentration / diversification scoring
  - Maximum drawdown tracking with daily loss limits
  - Risk budget allocation across strategies
  - Correlation-based risk decomposition

Architecture:
  - PortfolioRiskManager: standalone risk engine
  - PortfolioRiskSkill: BaseSkill wrapper for the skill system

Adapted from QuantMuse's C++ risk_manager + config risk params +
stock_selector constraints + factor calculator risk metrics.
"""

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics
from .indicators import _mean, _std

log = logging.getLogger("trading.risk")


# ═════════════════════════════════════════════════════════════════════════
# DATA CONTRACTS
# ═════════════════════════════════════════════════════════════════════════


@dataclass
class RiskReport:
    """Portfolio risk snapshot."""
    # VaR
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0  # Conditional VaR (expected shortfall)

    # Portfolio
    total_exposure: float = 0.0
    total_risk_pct: float = 0.0
    diversification_score: float = 1.0
    concentration_ratio: float = 0.0  # top-3 holdings / total

    # Drawdown
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    daily_pnl_pct: float = 0.0

    # Limits (set from config)
    max_position_size_pct: float = 0.0
    max_drawdown_limit: float = 0.2
    daily_loss_limit: float = 0.05

    # Status
    risk_level: str = "normal"  # normal / elevated / critical
    warnings: list[str] = field(default_factory=list)
    reported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PositionRisk:
    """Per-position risk assessment."""
    symbol: str
    position_size: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    volatility: float = 0.0
    max_position_pct: float = 0.0
    kelly_fraction: float = 0.0
    suggested_size: float = 0.0
    stop_loss: float = 0.0
    risk_contribution_pct: float = 0.0  # % of total portfolio risk
    status: str = "ok"  # ok / oversized / risky


# ═════════════════════════════════════════════════════════════════════════
# PORTFOLIO RISK MANAGER
# ═════════════════════════════════════════════════════════════════════════


class PortfolioRiskManager:
    """Portfolio-level risk engine.

    Adapted from QuantMuse's C++ risk_manager + config risk params.
    """

    def __init__(
        self,
        max_position_size_pct: float = 0.1,
        max_drawdown_limit: float = 0.2,
        daily_loss_limit: float = 0.05,
        var_confidence: float = 0.95,
        max_concentration: float = 0.3,
    ):
        self.max_position_size_pct = max_position_size_pct
        self.max_drawdown_limit = max_drawdown_limit
        self.daily_loss_limit = daily_loss_limit
        self.var_confidence = var_confidence
        self.max_concentration = max_concentration

        # State tracking
        self._peak_portfolio_value: float = 0.0
        self._daily_start_value: float = 0.0
        self._current_portfolio_value: float = 0.0
        self._positions: list[dict] = []

    # ── VaR Calculations ────────────────────────────────────────────────

    @staticmethod
    def parametric_var(
        portfolio_value: float,
        volatility: float,
        confidence: float = 0.95,
    ) -> float:
        """Parametric VaR assuming normal distribution.

        Adapted from QuantMuse: VaR = portfolio_value * vol * z_score.

        Args:
            portfolio_value: total portfolio value
            volatility: annualized volatility as decimal (e.g. 0.25)
            confidence: confidence level (0.95 = 95%)
        """
        if volatility <= 0:
            return 0.0

        # Z-scores for common confidence levels
        z_scores = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
        z = z_scores.get(confidence, 1.645)

        # Daily VaR
        daily_vol = volatility / math.sqrt(252)
        var_daily = portfolio_value * daily_vol * z

        return round(var_daily, 2)

    @staticmethod
    def historical_var(
        returns: list[float],
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        """Historical VaR and CVaR from return series.

        Adapted from QuantMuse: VaR = percentile of returns, CVaR = mean of
        returns below VaR threshold.

        Returns:
            (var, cvar) tuple
        """
        if not returns or len(returns) < 10:
            return 0.0, 0.0

        sorted_returns = sorted(returns)
        var_idx = int(len(sorted_returns) * (1 - confidence))
        if var_idx >= len(sorted_returns):
            var_idx = len(sorted_returns) - 1
        if var_idx < 0:
            var_idx = 0

        var = abs(sorted_returns[var_idx])
        tail = sorted_returns[: var_idx + 1]
        cvar = abs(_mean(tail)) if tail else var

        return round(var, 6), round(cvar, 6)

    # ── Position Sizing ─────────────────────────────────────────────────

    @staticmethod
    def kelly_criterion(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Kelly criterion optimal bet size.

        f* = win_rate - (1 - win_rate) / (avg_win / avg_loss)

        Adapted from QuantMuse config: returns fractional Kelly (0-1).
        """
        if avg_loss <= 0 or avg_win <= 0:
            return 0.0

        win_loss_ratio = avg_win / avg_loss
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        return round(max(0.0, min(1.0, kelly)), 4)

    @staticmethod
    def fractional_kelly(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.5,
    ) -> float:
        """Fractional Kelly — safer version using half-Kelly by default."""
        kelly = PortfolioRiskManager.kelly_criterion(win_rate, avg_win, avg_loss)
        return round(kelly * fraction, 4)

    @staticmethod
    def volatility_adjusted_size(
        position_vol: float,
        portfolio_value: float,
        max_risk_pct: float = 0.02,
    ) -> float:
        """Position size based on volatility targeting.

        Size = (portfolio * max_risk) / (position_vol * sqrt(252))
        """
        if position_vol <= 0:
            return 0.0

        daily_vol = position_vol / math.sqrt(252)
        return round(portfolio_value * max_risk_pct / max(daily_vol, 0.0001), 2)

    # ── Portfolio Analysis ──────────────────────────────────────────────

    @staticmethod
    def concentration_ratio(positions: list[dict]) -> float:
        """Top-3 holdings as fraction of total portfolio."""
        if not positions:
            return 0.0

        total = sum(abs(p.get("value", 0)) for p in positions)
        if total <= 0:
            return 0.0

        sorted_positions = sorted(
            positions, key=lambda p: abs(p.get("value", 0)), reverse=True
        )
        top3 = sum(abs(p.get("value", 0)) for p in sorted_positions[:3])
        return round(top3 / total, 4)

    @staticmethod
    def diversification_score(positions: list[dict]) -> float:
        """Simple diversification score based on concentration.

        1.0 = perfectly diversified (equal weights)
        0.0 = fully concentrated (single position)

        Adapted from QuantMuse: max_concentration config param.
        """
        if not positions or len(positions) <= 1:
            return 1.0 if not positions else 0.0

        n = len(positions)
        total = sum(abs(p.get("value", 0)) for p in positions)
        if total <= 0:
            return 1.0

        values = [abs(p.get("value", 0)) / total for p in positions]
        # Herfindahl-Hirschman Index normalized: 1 - (HHI - 1/n) / (1 - 1/n)
        hhi = sum(v * v for v in values)
        if n == 1:
            return 0.0
        normalized = (1 - hhi) / (1 - 1 / n)
        return round(max(0.0, min(1.0, normalized)), 4)

    @staticmethod
    def correlation_risk(
        positions: list[dict],
        correlation_matrix: Optional[dict[str, dict[str, float]]] = None,
    ) -> float:
        """Estimate portfolio risk from pairwise correlations.

        If no correlation matrix, estimate using equal-category assumption.
        """
        if not positions or len(positions) <= 1:
            return 0.0

        n = len(positions)
        total = sum(abs(p.get("value", 0)) for p in positions)
        if total <= 0:
            return 0.0

        weights = [abs(p.get("value", 0)) / total for p in positions]

        # Without a real correlation matrix, assume average correlation of 0.5
        # between crypto assets (conservative). Use weighted average.
        if correlation_matrix is None:
            avg_correlation = 0.5
            weighted_corr = sum(
                w * avg_correlation for w in weights
            )
            return round(weighted_corr, 4)

        # With matrix, compute weighted average pairwise correlation
        pair_weight_sum = 0.0
        weighted_corr = 0.0
        for i, pi in enumerate(positions):
            for j, pj in enumerate(positions):
                if i >= j:
                    continue
                corr = correlation_matrix.get(pi["symbol"], {}).get(pj["symbol"], 0.5)
                pair_weight = weights[i] * weights[j]
                weighted_corr += pair_weight * corr
                pair_weight_sum += pair_weight

        if pair_weight_sum <= 0:
            return 0.0
        return round(weighted_corr / pair_weight_sum, 4)

    # ── Drawdown Tracking ───────────────────────────────────────────────

    def update_portfolio_value(self, current_value: float) -> Optional[float]:
        """Update portfolio value and track drawdown.

        Returns current drawdown as a fraction, or None if no data.
        """
        if current_value <= 0:
            return None

        self._current_portfolio_value = current_value

        # Track peak
        if current_value > self._peak_portfolio_value:
            self._peak_portfolio_value = current_value

        if self._peak_portfolio_value <= 0:
            return 0.0

        drawdown = (self._peak_portfolio_value - current_value) / self._peak_portfolio_value
        return round(drawdown, 4)

    def set_daily_start(self, value: float) -> None:
        """Record portfolio value at start of trading day."""
        self._daily_start_value = value

    def daily_pnl(self) -> float:
        """Current day P&L as fraction of start-of-day value."""
        if self._daily_start_value <= 0:
            return 0.0
        return round(
            (self._current_portfolio_value - self._daily_start_value)
            / self._daily_start_value,
            4,
        )

    # ── Risk Budget ─────────────────────────────────────────────────────

    @staticmethod
    def allocate_risk_budget(
        positions: list[dict],
        total_risk_budget_pct: float = 0.02,
        method: str = "equal",
    ) -> dict[str, float]:
        """Allocate risk budget across positions.

        Methods:
          - equal: equal allocation per position
          - var_parity: inverse volatility weighting
          - kelly: Kelly-optimal allocation

        Returns:
            dict mapping position symbol → risk budget fraction
        """
        if not positions:
            return {}

        n = len(positions)

        if method == "equal":
            budget_per_position = total_risk_budget_pct / n
            return {p.get("symbol", f"pos_{i}"): budget_per_position for i, p in enumerate(positions)}

        elif method == "var_parity":
            # Inverse volatility: lower vol → higher allocation
            vols = [p.get("volatility", 0.25) for p in positions]
            inv_vols = [1.0 / max(v, 0.01) for v in vols]
            total_inv = sum(inv_vols)
            if total_inv <= 0:
                return {p.get("symbol", f"pos_{i}"): total_risk_budget_pct / n for i, p in enumerate(positions)}

            return {
                p.get("symbol", f"pos_{i}"): round(
                    total_risk_budget_pct * inv_vol / total_inv, 4
                )
                for i, (p, inv_vol) in enumerate(zip(positions, inv_vols))
            }

        elif method == "kelly":
            budgets = {}
            for p in positions:
                wr = p.get("win_rate", 0.5)
                aw = p.get("avg_win", 0.05)
                al = p.get("avg_loss", 0.03)
                k = PortfolioRiskManager.kelly_criterion(wr, aw, al)
                budgets[p.get("symbol", "unknown")] = round(
                    total_risk_budget_pct * k, 4
                )
            return budgets

        return {}

    # ── Comprehensive Assessment ────────────────────────────────────────

    def assess(
        self,
        positions: list[dict],
        returns: Optional[list[float]] = None,
        portfolio_volatility: float = 0.25,
    ) -> RiskReport:
        """Comprehensive portfolio risk assessment.

        Args:
            positions: list of dicts with symbol, value, entry_price, current_price, volatility
            returns: optional list of historical returns for VaR
            portfolio_volatility: annualized portfolio vol (used if no returns)
        """
        report = RiskReport(
            max_position_size_pct=self.max_position_size_pct,
            max_drawdown_limit=self.max_drawdown_limit,
            daily_loss_limit=self.daily_loss_limit,
        )

        total_value = sum(abs(p.get("value", 0)) for p in positions)
        report.total_exposure = round(total_value, 2)

        # VaR
        if returns and len(returns) >= 10:
            var_95, cvar = self.historical_var(returns, 0.95)
            var_99, _ = self.historical_var(returns, 0.99)
            report.var_95 = var_95
            report.var_99 = var_99
            report.cvar_95 = cvar
        elif total_value > 0:
            report.var_95 = self.parametric_var(total_value, portfolio_volatility, 0.95)
            report.var_99 = self.parametric_var(total_value, portfolio_volatility, 0.99)
            report.cvar_95 = report.var_95 * 1.3  # rough estimate

        # Risk as % of portfolio
        if total_value > 0:
            report.total_risk_pct = round(report.var_95 / total_value * 100, 2)

        # Concentration
        report.concentration_ratio = self.concentration_ratio(positions)
        report.diversification_score = self.diversification_score(positions)

        # Drawdown
        if total_value > 0:
            dd = self.update_portfolio_value(total_value)
            report.current_drawdown_pct = round((dd or 0) * 100, 2)
        report.daily_pnl_pct = round(self.daily_pnl() * 100, 2)

        # Warnings
        warnings = []

        if report.current_drawdown_pct > self.max_drawdown_limit * 100:
            warnings.append(
                f"Drawdown ({report.current_drawdown_pct:.1f}%) exceeds limit "
                f"({self.max_drawdown_limit*100:.1f}%)"
            )

        if abs(report.daily_pnl_pct) > self.daily_loss_limit * 100:
            warnings.append(
                f"Daily loss ({abs(report.daily_pnl_pct):.1f}%) exceeds "
                f"limit ({self.daily_loss_limit*100:.1f}%)"
            )

        if report.concentration_ratio > self.max_concentration:
            warnings.append(
                f"Concentration ({report.concentration_ratio*100:.1f}%) "
                f"exceeds limit ({self.max_concentration*100:.1f}%)"
            )

        if report.diversification_score < 0.3:
            warnings.append(
                f"Low diversification (score: {report.diversification_score:.2f})"
            )

        # Risk level
        if len(warnings) >= 3:
            report.risk_level = "critical"
        elif len(warnings) >= 1:
            report.risk_level = "elevated"
        else:
            report.risk_level = "normal"

        report.warnings = warnings
        return report

    def assess_position(
        self,
        symbol: str,
        position_size: float,
        entry_price: float,
        current_price: float,
        volatility: float,
        win_rate: float = 0.5,
        avg_win: float = 0.05,
        avg_loss: float = 0.03,
    ) -> PositionRisk:
        """Assess risk for a single position.

        Returns sizing recommendations and risk flags.
        """
        pos = PositionRisk(
            symbol=symbol,
            position_size=position_size,
            entry_price=entry_price,
            current_price=current_price,
            volatility=volatility,
        )

        # Kelly sizing
        pos.kelly_fraction = self.kelly_criterion(win_rate, avg_win, avg_loss)
        portfolio_val = self._current_portfolio_value if self._current_portfolio_value > 0 else position_size
        pos.suggested_size = self.volatility_adjusted_size(
            volatility, portfolio_val
        )

        # Max position check
        if self._current_portfolio_value > 0:
            pos.max_position_pct = self.max_position_size_pct
            actual_pct = position_size / self._current_portfolio_value
            if actual_pct > self.max_position_size_pct:
                pos.status = "oversized"

        # Stop loss: 2 * volatility below entry
        if volatility > 0:
            pos.stop_loss = round(
                entry_price * (1 - 2 * volatility / math.sqrt(252)), 6
            )

        # Risk contribution (rough estimate)
        pos.risk_contribution_pct = round(volatility * position_size * 100, 2)

        return pos


# ═════════════════════════════════════════════════════════════════════════
# PORTFOLIO RISK SKILL (BaseSkill wrapper)
# ═════════════════════════════════════════════════════════════════════════


class PortfolioRiskSkill(BaseSkill):
    """Portfolio-level risk assessment skill.

    Wraps PortfolioRiskManager for integration with the skill system.
    """
    name = "trading.risk.portfolio"
    version = "1.0.0"
    description = "Portfolio risk — VaR, drawdown, concentration, position sizing, risk budget"
    tags = ["domain:trading", "mode:safe", "risk:portfolio"]
    timeout_seconds = 15.0
    dependencies = ["trading.risk.assess"]

    async def validate(self, input: SkillInput) -> bool:
        mode = input.params.get("mode", "assess")
        action = input.params.get("action", "assess")
        # Single-position sizing needs symbol + entry_price, not positions
        if mode == "position" and action == "sizing":
            return bool(input.params.get("symbol")) and bool(input.params.get("entry_price"))
        return bool(input.params.get("positions", []))

    async def execute(self, input: SkillInput) -> SkillOutput:
        positions = input.params.get("positions", [])
        returns = input.params.get("returns")
        portfolio_vol = float(input.params.get("portfolio_volatility", 0.25))
        mode = input.params.get("mode", "assess")  # assess | position | budget
        action = input.params.get("action", "assess")

        # Config overrides
        mgr = PortfolioRiskManager(
            max_position_size_pct=float(
                input.params.get("max_position_size_pct", 0.1)
            ),
            max_drawdown_limit=float(
                input.params.get("max_drawdown_limit", 0.2)
            ),
            daily_loss_limit=float(
                input.params.get("daily_loss_limit", 0.05)
            ),
            var_confidence=float(
                input.params.get("var_confidence", 0.95)
            ),
            max_concentration=float(
                input.params.get("max_concentration", 0.3)
            ),
        )

        if mode == "position" and action == "sizing":
            # Single position sizing
            symbol = input.params.get("symbol", "UNKNOWN")
            pos_size = float(input.params.get("position_size", 0))
            entry = float(input.params.get("entry_price", 0))
            current = float(input.params.get("current_price", entry))
            vol = float(input.params.get("volatility", 0.25))
            wr = float(input.params.get("win_rate", 0.5))
            aw = float(input.params.get("avg_win", 0.05))
            al = float(input.params.get("avg_loss", 0.03))

            result = mgr.assess_position(
                symbol, pos_size, entry, current, vol, wr, aw, al
            )
            return SkillOutput(
                success=True,
                data={
                    "position_risk": {
                        "symbol": result.symbol,
                        "kelly_fraction": result.kelly_fraction,
                        "suggested_size": result.suggested_size,
                        "stop_loss": result.stop_loss,
                        "max_position_pct": result.max_position_pct,
                        "status": result.status,
                        "risk_contribution_pct": result.risk_contribution_pct,
                    }
                },
            )

        elif mode == "budget":
            # Risk budget allocation
            method = input.params.get("method", "equal")
            total_budget = float(input.params.get("total_risk_budget_pct", 0.02))
            budget = mgr.allocate_risk_budget(positions, total_budget, method)
            return SkillOutput(
                success=True,
                data={
                    "risk_budget": budget,
                    "total_budget_pct": total_budget,
                    "method": method,
                },
            )

        else:
            # Full portfolio assessment
            report = mgr.assess(positions, returns, portfolio_vol)
            return SkillOutput(
                success=True,
                data={
                    "risk_report": {
                        "var_95": report.var_95,
                        "var_99": report.var_99,
                        "cvar_95": report.cvar_95,
                        "total_exposure": report.total_exposure,
                        "total_risk_pct": report.total_risk_pct,
                        "diversification_score": report.diversification_score,
                        "concentration_ratio": report.concentration_ratio,
                        "current_drawdown_pct": report.current_drawdown_pct,
                        "daily_pnl_pct": report.daily_pnl_pct,
                        "risk_level": report.risk_level,
                        "warnings": report.warnings,
                    },
                },
            )
