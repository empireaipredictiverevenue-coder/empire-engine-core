"""
EMPIRE V49 · BOT BASE
=====================
Base class for all Empire bots. Provides platform-agnostic execution
with AGI Governor + SI Strategy + Predictive Revenue formula injection.

AGI · SI · PREDICTIVE REVENUE WIRING:
  - AGI Governor: strategy_for_niche() selects best strategy per niche
  - SI Strategy: best_for_niche() evolves genome per strike outcome
  - Predictive Revenue: estimates per-strike revenue for prioritization
    REVENUE = asset_value × 0.01 × niche_win_rate × urgency_multiplier
"""

import random
import time
import logging
from typing import Dict, Optional, Any

log = logging.getLogger("empire.bot")

# ── Predictive Revenue Formula ────────────────────────────────────
COMMISSION_RATE = 0.01
URGENCY_MULTIPLIERS = {
    "Extreme": 2.5, "Severe": 1.8, "Moderate": 1.2, "Minor": 0.8,
}


class EmpireBot:
    def __init__(self, platform, proxy_list, agi_governor=None, si_strategy=None):
        self.platform = platform
        self.proxies = proxy_list
        self.status = "INITIALIZED"
        self._agi_governor = agi_governor
        self._si_strategy = si_strategy

    def rotate_proxy(self):
        return random.choice(self.proxies)

    def execute(self, niche, strategy, instruction, asset_value=0, urgency="Moderate"):
        """
        Execute a strike with AGI + SI + Predictive Revenue formulas.

        AGI Governor: if no explicit strategy, auto-selects best for niche
        SI Strategy: logs genome selection for evolutionary feedback
        Predictive Revenue: estimates per-strike value for prioritization
        """
        # ── AGI Governor: auto-select strategy ────────────────────
        if not strategy and self._agi_governor:
            try:
                strategy = self._agi_governor.strategy_for_niche(niche)
                log.debug(f"[empire.bot] AGI selected: {strategy} for {niche}")
            except Exception:
                strategy = "AGGRESSIVE_STRIKE"

        # ── SI Strategy: log selected genome ──────────────────────
        if self._si_strategy:
            try:
                best = self._si_strategy.best_for_niche(niche)
                if best:
                    log.debug(f"[empire.bot] SI genome: {best} for {niche}")
            except Exception:
                pass

        # ── Predictive Revenue: estimate strike value ─────────────
        predicted_revenue = 0.0
        if asset_value > 0:
            win_rate = 0.1
            if self._agi_governor:
                try:
                    win_rate = self._agi_governor.get_niche_win_rate(niche) or 0.1
                except Exception:
                    pass
            urgency_mult = URGENCY_MULTIPLIERS.get(urgency, 1.2)
            predicted_revenue = round(asset_value * COMMISSION_RATE * win_rate * urgency_mult, 2)

        # This is where the "subconscious" persuasion logic lives
        proxy = self.rotate_proxy()
        print(f"[{self.platform}] Executing {strategy} strike on {niche} via {proxy}")
        if predicted_revenue > 0:
            print(f"[{self.platform}]  └─ Predicted Revenue: ${predicted_revenue:,.2f}")
        # Actual API calls injected via empire_voice (Vonage), empire_sms (SMS),
        # empire_email (Resend), and bots/synthetic_brain (Kokoro TTS).
        # The AI Closer pipeline replaces the old Vapi stub — see empire_ai_closer.py.
        return True
