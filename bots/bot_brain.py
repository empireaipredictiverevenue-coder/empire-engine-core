from empire_si_core import SyntheticIntelligence, get_si_core
from empire_si_strategy import StrategyEvolution


class BotBrain:
    """
    Strategy selector that uses the SI core's Bayesian inference
    to choose the best approach for a given niche/lane.
    """

    def __init__(self):
        self.si = get_si_core()

    def generate_strategy(self, niche: str, lane_id: int) -> dict:
        """
        Use SI core to simulate the best strategy for this niche/lane.
        Returns a dict with recommended strategy, win rate, and EV.
        """
        # Get evolved strategy from shared StrategyEvolution if available
        best_strategy_name = "STANDARD"
        try:
            si_strat = StrategyEvolution.get_shared_instance()
            if si_strat:
                best = si_strat.best_for_niche(niche)
                if best:
                    best_strategy_name = best
                    genome = si_strat.get_genome(best, niche)
        except Exception:
            genome = {}

        # Run SI core simulation
        result = self.si.simulate_strategy(
            strategy_name=best_strategy_name,
            wins=0,
            losses=0,
            revenue=0.0,
            n_opportunities=5,
        )
        result["niche"] = niche
        result["lane_id"] = lane_id
        return result
