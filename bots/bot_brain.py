from empire_si_core import SyntheticIntelligence

class BotBrain:
    def __init__(self):
        self.si = SyntheticIntelligence()

    def generate_strategy(self, niche, lane_id):
        # The "Brain" decides the approach
        context = {"niche": niche, "lane": lane_id}
        strategy = self.si.simulate_strategy(context)
        return strategy
