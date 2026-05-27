class AdGuardrail:
    def __init__(self):
        # Define forbidden spending patterns
        self.blacklist_metrics = ["high_bounce_rate", "low_intent_keyword", "bot_traffic_spike"]
        
    def validate_lane(self, lane_data):
        # Guardrail: Kill spend if lane shows negative signals
        for metric in self.blacklist_metrics:
            if lane_data.get(metric, False):
                print(f"[GUARDRAIL] Rejecting spend for Lane {lane_data['id']}: {metric}")
                return False
        return True
