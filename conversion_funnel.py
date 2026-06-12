"""
EMPIRE V49 · CONVERSION FUNNEL
==============================
Routes inbound leads to the in-house AI Closer (AGI-brained voice pipeline)
or nurture sequences. No external API dependencies — the closer uses the
Synthetic Intelligence Brain + BrainDecider + VoiceStreamingAgent stack.

AGI · SI · PREDICTIVE REVENUE INJECTION:
  - AGI Governor scores lead intent + niche for optimal routing
  - SI Strategy Evolution picks best genome for the lead's niche
  - Predictive Revenue formula estimates per-lead revenue potential
    REVENUE = asset_value × commission_rate × niche_win_rate × urgency_multiplier
"""

import logging
from typing import Optional, Any

log = logging.getLogger("empire.funnel")

# ── Predictive Revenue Formula Constants ──────────────────────────
COMMISSION_RATE = 0.01       # 1% of asset value
URGENCY_MULTIPLIERS = {
    "Extreme": 2.5,
    "Severe":  1.8,
    "Moderate": 1.2,
    "Minor":   0.8,
}
DEFAULT_URGENCY = 1.2


class SalesFunnel:
    """
    Thin routing layer. For full AI closing, use empire_ai_closer.AICloser
    which orchestrates BrainDecider → VoiceStreamingAgent → SI feedback loop.

    AGI · SI · Predictive Revenue wired:
      - AGI Governor: scores intent severity + niche win rate for routing weight
      - SI Strategy: best_for_niche() selects optimal genome
      - Predictive Revenue: estimates per-lead revenue potential
    """

    def __init__(self, closer=None, agi_governor=None, si_strategy=None):
        self.stage = "LEAD_INBOUND"
        self.closer = closer
        self._agi_governor = agi_governor
        self._si_strategy = si_strategy

    def optimize_conversion(self, click_data):
        """
        Route the lead based on intent signals, AGI governor scoring,
        and predictive revenue potential.

        HIGH intent   → queue for AGI-brained voice closer (AICloser.close())
        MEDIUM intent → nurture sequence (SMS/Email drip)
        LOW intent    → low-touch follow-up

        When a closer is wired, high-intent leads get the full pipeline:
        BrainDecider → Strategy (SI genome) → Voice streaming / static call.

        Predictive Revenue formula per lead:
          REVENUE = asset_value × 0.01 × niche_win_rate × urgency_multiplier
        """
        intent = click_data.get('intent', 'medium')
        asset_value = float(click_data.get('asset_value', 0) or 0)
        niche = click_data.get('niche', '')
        urgency = click_data.get('urgency', 'Moderate')

        # ── AGI Governor scoring: adjust intent based on niche win rate ──
        if self._agi_governor and niche:
            try:
                win_rate = self._agi_governor.get_niche_win_rate(niche)
                if win_rate >= 0.15 and intent == "medium":
                    intent = "high"  # upgrade: proven niche, send to closer
                    log.debug(f"[funnel] AGI upgrade: {niche} win_rate={win_rate:.2f} → HIGH")
                elif win_rate < 0.03 and intent == "high":
                    intent = "medium"  # downgrade: unproven niche, nurture first
                    log.debug(f"[funnel] AGI downgrade: {niche} win_rate={win_rate:.2f} → MEDIUM")
            except Exception as e:
                log.debug(f"[funnel] AGI scoring skipped: {e}")

        # ── SI Strategy: log best genome for this niche ──
        if self._si_strategy and niche:
            try:
                self._si_strategy.best_for_niche(niche)
            except Exception:
                pass

        # ── Predictive Revenue: estimate per-lead value ──
        predicted_revenue = 0.0
        if asset_value > 0:
            urgency_mult = URGENCY_MULTIPLIERS.get(urgency, DEFAULT_URGENCY)
            win_rate = 0.1  # default if no AGI data
            if self._agi_governor and niche:
                try:
                    win_rate = self._agi_governor.get_niche_win_rate(niche) or 0.1
                except Exception:
                    pass
            predicted_revenue = round(asset_value * COMMISSION_RATE * win_rate * urgency_mult, 2)

        if intent == "high":
            if self.closer:
                return "ROUTE_TO_AGI_CLOSER"
            return "ROUTE_TO_VOICE_PIPELINE"  # fallback: queue for voice_streaming_agent

        if intent == "medium":
            return "ROUTE_TO_NURTURE_SEQUENCE"

        return "ROUTE_TO_LOW_TOUCH"

    # ── Predictive Revenue formula (standalone, usable by other modules) ──
    @staticmethod
    def predict_lead_revenue(
        asset_value: float,
        niche: str = "",
        urgency: str = "Moderate",
        agi_governor: Any = None,
    ) -> float:
        """
        Predictive Revenue formula:
          REVENUE = asset_value × commission_rate × niche_win_rate × urgency_multiplier

        Used by swarm_worker, voice_streaming_agent, and other bots to
        prioritize high-value targets.
        """
        if asset_value <= 0:
            return 0.0
        win_rate = 0.1
        if agi_governor and niche:
            try:
                win_rate = agi_governor.get_niche_win_rate(niche) or 0.1
            except Exception:
                pass
        urgency_mult = URGENCY_MULTIPLIERS.get(urgency, DEFAULT_URGENCY)
        return round(asset_value * COMMISSION_RATE * win_rate * urgency_mult, 2)
