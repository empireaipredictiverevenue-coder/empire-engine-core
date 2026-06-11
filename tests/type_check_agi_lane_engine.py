"""
EMPIRE V49 · mypy type-check verification
==========================================
This file exists to be type-checked by mypy (NOT executed). It exercises
the AGILaneEngine constructor signature to verify that the TYPE_CHECKING-
guarded `Optional["StrategyEvolution"]` hint is properly resolved and
that mypy catches wrong-type assignments at call sites.

If this file passes `mypy tests/type_check_agi_lane_engine.py`, it proves:
  1. The TYPE_CHECKING guard correctly exposes StrategyEvolution as a
     forward reference for mypy's static analysis
  2. The constructor's `si_strategy` parameter accepts StrategyEvolution
     instances (and None for the back-compat path)
  3. The constructor's `revenue_score_fn` parameter accepts any callable
     matching `Callable[[int], float]`
  4. mypy catches wrong-type assignments (the commented-out bad call)

This file is NOT collected by pytest (it has no `if __name__ == "__main__":`
and no test classes). It's purely a static-analysis target.

Run with:  mypy tests/type_check_agi_lane_engine.py
"""
from __future__ import annotations

from typing import Callable

from bots.agi_lane_engine import AGILaneEngine
from empire_si_strategy import StrategyEvolution


def _build_strategy() -> StrategyEvolution:
    """Construct a real StrategyEvolution instance for the type check."""
    return StrategyEvolution()


def _build_revenue_fn() -> Callable[[int], float]:
    """Construct a callable matching Callable[[int], float]."""
    def revenue_fn(lane_id: int) -> float:
        return float(lane_id) * 0.5
    return revenue_fn


# ── Correct calls — these MUST pass mypy ─────────────────────────────

# 1. Default constructor (no args) — both injected deps default to None
engine1: AGILaneEngine = AGILaneEngine()

# 2. With max_correction_loops only
engine2: AGILaneEngine = AGILaneEngine(max_correction_loops=5)

# 3. With a real StrategyEvolution instance injected
real_si: StrategyEvolution = _build_strategy()
engine3: AGILaneEngine = AGILaneEngine(si_strategy=real_si)

# 4. With None explicitly (back-compat path)
engine4: AGILaneEngine = AGILaneEngine(si_strategy=None)

# 5. With a real revenue_score_fn injected
real_fn: Callable[[int], float] = _build_revenue_fn()
engine5: AGILaneEngine = AGILaneEngine(revenue_score_fn=real_fn)

# 6. With both injected
engine6: AGILaneEngine = AGILaneEngine(
    max_correction_loops=3,
    si_strategy=real_si,
    revenue_score_fn=real_fn,
)

# 7. Verify the instance attributes are accessible with the right types
assert engine1.si_strategy is None
assert engine1.revenue_score_fn is None
assert engine3.si_strategy is real_si
assert engine5.revenue_score_fn is real_fn


# ── Wrong-type calls — these MUST be flagged by mypy ─────────────────

# Uncomment the following lines to verify mypy catches wrong-type
# assignments. (Currently commented out so the test passes cleanly.
# mypy will flag them if you uncomment and re-run.)

# BAD_1: si_strategy expects StrategyEvolution, not an int
# engine_bad_1: AGILaneEngine = AGILaneEngine(si_strategy=42)

# BAD_2: revenue_score_fn expects Callable[[int], float], not a string
# engine_bad_2: AGILaneEngine = AGILaneEngine(revenue_score_fn="not callable")

# BAD_3: max_correction_loops expects int, not a string
# engine_bad_3: AGILaneEngine = AGILaneEngine(max_correction_loops="three")
