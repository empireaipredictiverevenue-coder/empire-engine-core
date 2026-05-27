class SalesFunnel:
    def __init__(self):
        self.stage = "LEAD_INBOUND"

    def optimize_conversion(self, click_data):
        # Route lead to the correct landing page based on intent
        if click_data['intent'] == "high":
            return "REDIRECT_TO_VAPI_CLOSER"
        return "REDIRECT_TO_NURTURE_SEQUENCE"
