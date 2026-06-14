"""
EMPIRE V49 · SYNTHETIC INTELLIGENCE CORE
=========================================
Real probabilistic inference engine for the Empire AI fleet.

Replaces the stub with mathematically rigorous models:

  • Beta-Binomial Bayesian Model — win rates as Beta(α, β) posteriors
    with a Beta(1,1) uniform prior. Provides posterior means, credible
    intervals, and full probability densities for decision-making.

  • Thompson Sampling — explore/exploit by sampling from Beta posteriors
    and selecting the strategy with the highest draw. Naturally balances
    exploration (high-variance strategies get tried) with exploitation
    (high-mean strategies get chosen more often).

  • Expected Value with Confidence — E[revenue] = P(win) * avg_revenue,
    with 95% credible intervals propagated through the product.

  • Probability Calibration — Platt scaling (logistic regression fit on
    outcome history) to correct systematic bias in predicted probabilities.

  • Bayesian Change Detection — sliding-window KL divergence between
    consecutive revenue distributions to detect regime shifts.

All methods accept raw data and return dicts — no database coupling.
Integrates with empire_si_strategy.py's StrategyEvolution via the
shared instance pattern.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import numpy as np

log = logging.getLogger("empire.si.core")

# ── BETA-BINOMIAL BAYESIAN MODEL ──────────────────────────────────────────
# We model win rate as a Beta(α, β) posterior:
#   α = prior_alpha + wins
#   β = prior_beta  + losses
# With a Beta(1,1) uniform prior (no assumptions), the posterior mean is
#   (1 + wins) / (2 + total_trials)
# which is the "rule of succession" — mathematically sound and avoids
# the zero-vs-infinite problem when total_trials = 0.

PRIOR_ALPHA = 1.0
PRIOR_BETA = 1.0
CONFIDENCE_LEVEL = 0.95  # 95% credible interval


def beta_posterior(wins: int, losses: int) -> Dict[str, float]:
    """
    Compute Beta posterior parameters and derived statistics.

    Args:
        wins: Number of successful outcomes.
        losses: Number of failed outcomes.

    Returns:
        {alpha, beta, mean, std, ci_lower, ci_upper, mode, entropy}
        All values computed analytically from the Beta distribution.
    """
    a = PRIOR_ALPHA + wins
    b = PRIOR_BETA + losses

    n = a + b  # effective sample size

    # Posterior mean (shrinkage estimate)
    mean = a / n if n > 0 else 0.0

    # Standard deviation
    std = math.sqrt(a * b / (n * n * (n + 1))) if n > 0 else 0.0

    # Mode (MAP estimate): (a-1)/(a+b-2) for a>1, b>1
    mode = (a - 1) / (a + b - 2) if a > 1 and b > 1 else mean

    # 95% credible interval (equal-tailed) via inverse Beta CDF
    # Using scipy for the actual computation with fallback to normal approximation
    try:
        from scipy.stats import beta as beta_dist
        ci_lower = float(beta_dist.ppf((1 - CONFIDENCE_LEVEL) / 2, a, b))
        ci_upper = float(beta_dist.ppf(1 - (1 - CONFIDENCE_LEVEL) / 2, a, b))
    except ImportError:
        # Normal approximation (valid for large n, conservative for small n)
        z = 1.96  # 97.5th percentile of standard normal
        margin = z * std
        ci_lower = max(0.0, mean - margin)
        ci_upper = min(1.0, mean + margin)

    # Differential entropy of Beta(a,b):
    # ln(B(a,b)) - (a-1)ψ(a) - (b-1)ψ(b) + (a+b-2)ψ(a+b)
    # Where ψ is the digamma function. We use scipy's digamma if available,
    # otherwise return 0 (entropy not critical for decision-making).
    entropy = 0.0
    try:
        from scipy.special import digamma, betaln
        entropy = float(
            betaln(a, b) - (a - 1) * digamma(a) - (b - 1) * digamma(b)
            + (a + b - 2) * digamma(a + b)
        )
    except ImportError:
        pass

    return {
        "alpha": round(a, 4),
        "beta": round(b, 4),
        "mean": round(mean, 4),
        "std": round(std, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "mode": round(mode, 4),
        "entropy": round(entropy, 4),
        "effective_samples": n,
    }


def thompson_sample(strategies: Dict[str, Dict[str, float]], k: int = 1) -> List[Tuple[str, float]]:
    """
    Thompson sampling: for each strategy, draw one sample from its Beta posterior,
    then select the top-k strategies by sample value.

    This naturally balances exploration (strategies with high variance get
    sampled more broadly) and exploitation (high-mean strategies are more
    likely to produce high draws).

    Args:
        strategies: {strategy_id: {wins, losses, ...}}
        k: Number of strategies to select (default 1).

    Returns:
        [(strategy_id, sampled_value), ...] sorted descending by sampled value.
    """
    try:
        from scipy.stats import beta as beta_dist
        samples = []
        for sid, s in strategies.items():
            a = PRIOR_ALPHA + s.get("wins", 0)
            b = PRIOR_BETA + s.get("losses", 0)
            draw = float(beta_dist.rvs(a, b))
            samples.append((sid, draw))
    except ImportError:
        # Fallback: sample from Beta via Gamma variates (works without scipy)
        import random as _random
        samples = []
        for sid, s in strategies.items():
            wins = s.get("wins", 0)
            losses = s.get("losses", 0)
            # Beta is Gamma(a,1) / (Gamma(a,1) + Gamma(b,1))
            try:
                ga = _random.gammavariate(PRIOR_ALPHA + wins, 1)
                gb = _random.gammavariate(PRIOR_BETA + losses, 1)
                draw = ga / (ga + gb) if (ga + gb) > 0 else 0.5
            except (ValueError, ZeroDivisionError):
                draw = 0.5
            samples.append((sid, draw))

    samples.sort(key=lambda x: x[1], reverse=True)
    return samples[:k]


# ── EXPECTED VALUE WITH CONFIDENCE ────────────────────────────────────────

def expected_revenue(
    win_rate: Dict[str, float],
    avg_deal_size: float,
    n_opportunities: int,
) -> Dict[str, float]:
    """
    Compute expected revenue with propagated uncertainty.

    E[revenue] = P(win) * avg_deal_size * n_opportunities

    Uncertainty is propagated via the delta method:
      Var(E[revenue]) ≈ (avg_deal_size * n)^2 * Var(P(win))

    Args:
        win_rate: Dict with 'mean' and 'std' from beta_posterior()
        avg_deal_size: Average deal value in dollars.
        n_opportunities: Number of opportunities in pipeline.

    Returns:
        {expected, std, ci_lower, ci_upper, p5, p95}
    """
    p = win_rate["mean"]
    p_std = win_rate["std"]
    n = float(n_opportunities)
    v = float(avg_deal_size)

    ev = p * v * n

    # Delta method: Var(ev) ≈ (v * n)^2 * Var(p)
    ev_std = v * n * p_std if n > 0 else 0.0

    # 95% CI (normal approximation)
    z = 1.96
    ci_lower = max(0.0, ev - z * ev_std)
    ci_upper = ev + z * ev_std

    return {
        "expected": round(ev, 2),
        "std": round(ev_std, 2),
        "ci_lower": round(ci_lower, 2),
        "ci_upper": round(ci_upper, 2),
        "p5": round(max(0.0, ev - 1.645 * ev_std), 2),
        "p95": round(ev + 1.645 * ev_std, 2),
        "win_rate_used": round(p, 4),
    }


# ── PROBABILITY CALIBRATION (Platt Scaling) ──────────────────────────────

class ProbabilityCalibrator:
    """
    Platt scaling: fits a logistic regression log(p/(1-p)) = a * logit(pred) + b
    to correct systematic bias in predicted probabilities.

    This is the standard method used by scikit-learn's CalibratedClassifierCV
    but implemented here with pure numpy so we don't depend on sklearn.

    The fit is simple: collect pairs of (predicted_prob, actual_outcome),
    transform to logit space, and fit a linear model via gradient descent.
    """

    def __init__(self):
        self.a: float = 1.0  # slope (default = identity)
        self.b: float = 0.0  # intercept (default = zero bias)
        self._fitted: bool = False
        self._n_samples: int = 0

    def fit(self, predictions: List[float], outcomes: List[int]) -> Dict[str, float]:
        """
        Fit Platt scaling to (prediction, outcome) pairs.

        Args:
            predictions: List of predicted probabilities (0.0-1.0).
            outcomes: List of binary outcomes (0 or 1).

        Returns:
            {a, b, n_samples, bic} — model parameters and Bayesian IC.
        """
        if len(predictions) < 10:
            return {"a": 1.0, "b": 0.0, "n_samples": len(predictions), "bic": 0.0}

        # Transform to logit space, clipping to avoid infinities
        eps = 1e-10
        logits = []
        for p in predictions:
            p_clip = max(eps, min(1 - eps, p))
            logits.append(math.log(p_clip / (1 - p_clip)))

        outcomes_arr = np.array(outcomes, dtype=np.float64)
        logits_arr = np.array(logits, dtype=np.float64)

        # Gradient descent to find a, b that minimize binary cross-entropy
        a, b = 1.0, 0.0
        lr = 0.1
        n = len(predictions)

        for _ in range(500):
            # Forward: p_calibrated = sigmoid(a * logit + b)
            z = a * logits_arr + b
            # Clamp z to avoid exp overflow
            z = np.clip(z, -20, 20)
            p_cal = 1.0 / (1.0 + np.exp(-z))

            # Binary cross-entropy gradient
            grad_a = np.mean((p_cal - outcomes_arr) * logits_arr)
            grad_b = np.mean(p_cal - outcomes_arr)

            # Update with momentum-like clipping
            a -= lr * grad_a
            b -= lr * grad_b

            # L2 regularization (weak, to prevent extreme slopes)
            a -= lr * 0.001 * a
            b -= lr * 0.001 * b

        self.a = float(a)
        self.b = float(b)
        self._fitted = True
        self._n_samples = n

        # Bayesian Information Criterion (lower = better fit)
        z = np.clip(a * logits_arr + b, -20, 20)
        p_cal = 1.0 / (1.0 + np.exp(-z))
        # Avoid log(0)
        p_cal = np.clip(p_cal, eps, 1 - eps)
        neg_log_likelihood = -np.mean(
            outcomes_arr * np.log(p_cal) + (1 - outcomes_arr) * np.log(1 - p_cal)
        )
        bic = 2 * neg_log_likelihood + 2 * math.log(n) / n

        log.info(
            f"[si.core] Platt calibrated: a={a:.3f}, b={b:.3f}, "
            f"n={n}, BIC={bic:.3f}"
        )

        return {"a": round(a, 4), "b": round(b, 4), "n_samples": n, "bic": round(bic, 4)}

    def calibrate(self, probability: float) -> float:
        """
        Apply Platt scaling to a single probability.

        Args:
            probability: Raw predicted probability (0.0-1.0).

        Returns:
            Calibrated probability (0.0-1.0).
        """
        if not self._fitted:
            return probability
        eps = 1e-10
        p_clip = max(eps, min(1 - eps, probability))
        logit = math.log(p_clip / (1 - p_clip))
        z = self.a * logit + self.b
        # Clamp to avoid overflow
        z = max(-20, min(20, z))
        return 1.0 / (1.0 + math.exp(-z))


# ── BAYESIAN CHANGE DETECTION ─────────────────────────────────────────────

def detect_regime_shift(
    recent_revenues: List[float],
    historical_revenues: List[float],
    threshold: float = 0.5,
) -> Dict[str, float]:
    """
    Detect whether the revenue distribution has shifted between two windows
    using KL divergence between fitted Gamma distributions.

    Revenue data is modeled as Gamma(shape, rate) — a natural choice for
    positive-valued, right-skewed financial data.

    Args:
        recent_revenues: Revenue values from the recent window (e.g., last 7 days).
        historical_revenues: Revenue values from the baseline window (e.g., prior 30 days).
        threshold: KL divergence threshold for flagging a shift (default 0.5 nats).

    Returns:
        {kl_divergence, regime_shift_detected, recent_mean, historical_mean,
         pct_change, recommendation}
    """
    if not recent_revenues or len(recent_revenues) < 3:
        return {
            "kl_divergence": 0.0,
            "regime_shift_detected": False,
            "recent_mean": float(np.mean(recent_revenues)) if recent_revenues else 0.0,
            "historical_mean": float(np.mean(historical_revenues)) if historical_revenues else 0.0,
            "pct_change": 0.0,
            "recommendation": "insufficient_data",
        }

    recent = np.array(recent_revenues, dtype=np.float64) + 1e-6  # avoid zeros
    historical = np.array(historical_revenues, dtype=np.float64) + 1e-6

    recent_mean = float(np.mean(recent))
    hist_mean = float(np.mean(historical))
    pct_change = ((recent_mean - hist_mean) / max(hist_mean, 1e-6)) * 100

    # Fit Gamma distributions via method of moments
    # shape = mean² / variance, rate = mean / variance
    def _gamma_params(data):
        m = float(np.mean(data))
        v = float(np.var(data)) + 1e-10
        shape = m * m / v
        rate = m / v
        return shape, rate

    try:
        from scipy.stats import gamma as gamma_dist, entropy as kl_div

        s1, r1 = _gamma_params(recent)
        s2, r2 = _gamma_params(historical)

        # KL divergence D(Gamma1 || Gamma2) — analytic formula
        # D(Γ(s1,r1) || Γ(s2,r2)) = (s1-s2)*ψ(s1) - log(Γ(s1)/Γ(s2)) + s2*log(r1/r2) + s1*(r2-r1)/r1
        # We use scipy's generic KL divergence on discretized PDF for robustness
        x = np.linspace(1.0, max(np.max(recent), np.max(historical)) * 1.5, 1000)
        p = gamma_dist.pdf(x, s1, scale=1.0 / r1) + 1e-10
        q = gamma_dist.pdf(x, s2, scale=1.0 / r2) + 1e-10
        kl_div_value = float(kl_div(p, q))
    except ImportError:
        # Fallback: simple distribution comparison using mean + variance
        # Rough KL approximation for Gamma: (s1-s2)² / (2*s2²) when shapes are close
        s1, r1 = _gamma_params(recent)
        s2, r2 = _gamma_params(historical)
        kl_div_value = ((s1 - s2) ** 2) / (2 * max(s2, 0.1) ** 2)
        kl_div_value += abs(math.log(r1 / max(r2, 0.01)))

    kl_div_value = min(kl_div_value, 10.0)  # cap at 10 nats
    shift_detected = kl_div_value > threshold

    if shift_detected:
        log.info(
            f"[si.core] Regime shift detected: KL={kl_div_value:.3f}, "
            f"mean ${hist_mean:.0f} → ${recent_mean:.0f} ({pct_change:+.1f}%)"
        )

    # Recommendation based on shift direction
    if not shift_detected:
        rec = "stable"
    elif pct_change > 10:
        rec = "upshift_invest"  # Revenue growing — invest more
    elif pct_change < -10:
        rec = "downshift_conserve"  # Revenue declining — conserve resources
    else:
        rec = "shift_monitor"  # Structural change but flat revenue

    return {
        "kl_divergence": round(kl_div_value, 4),
        "regime_shift_detected": shift_detected,
        "recent_mean": round(recent_mean, 2),
        "historical_mean": round(hist_mean, 2),
        "pct_change": round(pct_change, 2),
        "recommendation": rec,
    }


# ── SYNTHETIC INTELLIGENCE CLASS ──────────────────────────────────────────

class SyntheticIntelligence:
    """
    Core probabilistic inference engine for Empire AI.

    This class replaces the stub with real mathematical models for
    strategy simulation, outcome prediction, and adaptive learning.

    It integrates with empire_si_strategy.py's StrategyEvolution via
    the shared instance pattern (StrategyEvolution.set_shared_instance()).
    """

    def __init__(self):
        # Knowledge base: strategy_id → {wins, losses, revenues, ...}
        self.knowledge_base: Dict[str, Dict] = {}

        # Probability calibrator (Platt scaling)
        self.calibrator = ProbabilityCalibrator()

        # Revenue history for change detection
        self._revenue_history: Dict[str, List[float]] = defaultdict(list)
        # (niche → list of daily revenue values)

        # Performance tracking
        self._total_predictions: int = 0
        self._calibrations_run: int = 0

    # ── STRATEGY SIMULATION ─────────────────────────────────────────────

    def simulate_strategy(
        self,
        strategy_name: str,
        wins: int = 0,
        losses: int = 0,
        revenue: float = 0.0,
        n_opportunities: int = 1,
    ) -> Dict:
        """
        Predict strategy outcome using Bayesian beta-binomial model.

        Args:
            strategy_name: Name of the strategy (e.g., "AGGRESSIVE_STRIKE").
            wins: Historical wins for this strategy.
            losses: Historical losses for this strategy.
            revenue: Total revenue from this strategy (for expected value).
            n_opportunities: Number of upcoming opportunities to forecast.

        Returns:
            Dict with win_rate (Beta posterior), expected_revenue (with CI),
            explore_score (Thompson sampling score), and recommendation.
        """
        self._total_predictions += 1

        # Update knowledge base
        self.knowledge_base.setdefault(strategy_name, {"wins": 0, "losses": 0, "revenue": 0.0})
        kb = self.knowledge_base[strategy_name]
        if wins > 0 or losses > 0:
            kb["wins"] += wins
            kb["losses"] += losses
            kb["revenue"] += revenue

        total_wins = kb["wins"] + wins
        total_losses = kb["losses"] + losses

        # 1. Bayesian win rate estimate
        win_rate = beta_posterior(total_wins, total_losses)

        # 2. Calibrate the probability (correct systematic bias)
        calibrated_p = self.calibrator.calibrate(win_rate["mean"])

        # 3. Expected revenue with uncertainty
        avg_deal = revenue / max(total_wins + total_losses, 1) if (total_wins + total_losses) > 0 else 0.0
        ev = expected_revenue(win_rate, avg_deal, n_opportunities)

        # 4. Thompson explore score (sample from posterior)
        explore = thompson_sample(
            {strategy_name: {"wins": total_wins, "losses": total_losses}},
            k=1,
        )
        explore_score = explore[0][1] if explore else 0.0

        # 5. Recommendation
        if win_rate["mean"] >= 0.6 and ev["expected"] > 0:
            recommendation = "AGGRESSIVE_EXECUTE"
        elif win_rate["mean"] >= 0.3:
            recommendation = "CAUTIOUS_PROCEED"
        elif total_wins + total_losses < 5:
            recommendation = "EXPLORE_NEED_MORE_DATA"
        else:
            recommendation = "HOLD_RECONSIDER"

        return {
            "strategy": strategy_name,
            "win_rate": win_rate,
            "calibrated_probability": round(calibrated_p, 4),
            "expected_revenue": ev,
            "explore_score": round(explore_score, 4),
            "recommendation": recommendation,
            "total_trials": total_wins + total_losses,
            "total_wins": total_wins,
            "total_losses": total_losses,
        }

    # ── EVOLVE LOGIC ────────────────────────────────────────────────────

    def evolve_logic(self, performance_feedback: Dict) -> Dict:
        """
        Integrate outcome feedback and update inference parameters.

        This is called by the SI strategy evolution loop after outcomes
        are collected. It:
          1. Updates the probability calibrator with new (prediction, outcome) pairs
          2. Detects revenue regime shifts
          3. Returns updated parameters

        Args:
            performance_feedback: Dict with 'predictions', 'outcomes',
                'revenues', 'niche' keys.

        Returns:
            Dict with calibration results, regime shift analysis, and
            updated "optimization weight" (sharpened posterior precision).
        """
        predictions = performance_feedback.get("predictions", [])
        outcomes = performance_feedback.get("outcomes", [])
        revenues = performance_feedback.get("revenues", [])
        niche = performance_feedback.get("niche", "default")

        # 1. Fit Platt calibration
        if predictions and outcomes:
            cal_result = self.calibrator.fit(predictions, outcomes)
            self._calibrations_run += 1
        else:
            cal_result = {"a": 1.0, "b": 0.0, "n_samples": 0, "bic": 0.0}

        # 2. Record revenue and detect regime shifts
        shift_result = {"regime_shift_detected": False, "recommendation": "insufficient_data"}
        if revenues:
            self._revenue_history[niche].extend(revenues)
            hist = self._revenue_history[niche]
            if len(hist) >= 10:
                # Split: recent = last 25%, historical = prior 75%
                split = max(3, len(hist) // 4)
                recent = hist[-split:]
                historical = hist[:-split]
                shift_result = detect_regime_shift(recent, historical)

        # 3. Compute new optimization weight
        # The weight is the posterior precision (1/variance) of the win rate
        # estimate, averaged across all strategies in the knowledge base.
        precisions = []
        for sid, kb in self.knowledge_base.items():
            wr = beta_posterior(kb.get("wins", 0), kb.get("losses", 0))
            if wr["std"] > 0:
                precisions.append(1.0 / wr["std"])

        avg_precision = float(np.mean(precisions)) if precisions else 1.0
        optimization_weight = round(min(10.0, max(0.1, avg_precision)), 2)

        return {
            "status": "calibrated",
            "calibration": cal_result,
            "regime_shift": shift_result,
            "niche": niche,
            "optimization_weight": optimization_weight,
            "total_predictions": self._total_predictions,
            "calibrations_run": self._calibrations_run,
        }

    # ── NICHE ANALYSIS ──────────────────────────────────────────────────

    def analyze_niche(self, niche: str, strategies: List[Dict]) -> Dict:
        """
        Run full SI analysis on a niche's strategies.

        Args:
            niche: Niche name (e.g., "Roofing Restoration").
            strategies: List of {name, wins, losses, revenue} dicts.

        Returns:
            Dict with per-strategy analysis, best strategy, and niche-level
            expected revenue.
        """
        results = []
        best_score = -1
        best_strategy = None

        total_wins = 0
        total_losses = 0
        total_revenue = 0.0

        for s in strategies:
            sim = self.simulate_strategy(
                strategy_name=s["name"],
                wins=s.get("wins", 0),
                losses=s.get("losses", 0),
                revenue=s.get("revenue", 0.0),
                n_opportunities=s.get("opportunities", 1),
            )
            results.append(sim)

            total_wins += s.get("wins", 0)
            total_losses += s.get("losses", 0)
            total_revenue += s.get("revenue", 0.0)

            # Track best by calibrated probability * explore score
            combined = sim["calibrated_probability"] * sim["explore_score"]
            if combined > best_score:
                best_score = combined
                best_strategy = s["name"]

        # Niche-level win rate
        niche_win_rate = beta_posterior(total_wins, total_losses) if (total_wins + total_losses) > 0 else {}

        # Niche-level expected revenue
        niche_ev = expected_revenue(
            niche_win_rate if niche_win_rate else {"mean": 0.5, "std": 0.3},
            total_revenue / max(total_wins + total_losses, 1) if (total_wins + total_losses) > 0 else 5000,
            n_opportunities=max(1, len(strategies) * 10),
        )

        return {
            "niche": niche,
            "strategies": results,
            "best_strategy": best_strategy,
            "best_score": round(best_score, 4),
            "niche_win_rate": niche_win_rate,
            "niche_expected_revenue": niche_ev,
            "total_trials": total_wins + total_losses,
        }


# ── CONVENIENCE FUNCTIONS ──────────────────────────────────────────────

# Shared singleton (mirrors the StrategyEvolution / AGIGovernor pattern)
_SI_CORE_INSTANCE: Optional[SyntheticIntelligence] = None


def get_si_core() -> SyntheticIntelligence:
    """Return the shared SI core instance (lazy-init)."""
    global _SI_CORE_INSTANCE
    if _SI_CORE_INSTANCE is None:
        _SI_CORE_INSTANCE = SyntheticIntelligence()
    return _SI_CORE_INSTANCE


def set_si_core(instance: Optional[SyntheticIntelligence]) -> None:
    """Set the shared SI core instance (for dependency injection)."""
    global _SI_CORE_INSTANCE
    _SI_CORE_INSTANCE = instance
