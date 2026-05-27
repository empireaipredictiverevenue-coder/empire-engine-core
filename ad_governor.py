class AdGovernor:
    def __init__(self):
        self.budget_cap = 10000  # Daily limit per lane
        
    def adjust_spend(self, lane_id, si_probability):
        # Dynamically scale budget based on AI simulation success
        if si_probability > 0.85:
            print(f"[AD-GOVERNOR] Lane-{lane_id} probability {si_probability} is high. Increasing spend.")
            return self.budget_cap * 1.5
        return self.budget_cap * 0.5

# This creates an autonomous feedback loop for traffic acquisition
