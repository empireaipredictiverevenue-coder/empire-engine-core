"""
EMPIRE V49 · CONVERSION FUNNEL
==============================
Routes inbound leads to the in-house AI Closer (AGI-brained voice pipeline)
or nurture sequences. No external API dependencies — the closer uses the
Synthetic Intelligence Brain + BrainDecider + VoiceStreamingAgent stack.
"""


class SalesFunnel:
    """
    Thin routing layer. For full AI closing, use empire_ai_closer.AICloser
    which orchestrates BrainDecider → VoiceStreamingAgent → SI feedback loop.
    """

    def __init__(self, closer=None):
        self.stage = "LEAD_INBOUND"
        self.closer = closer  # AICloser instance (injected)

    def optimize_conversion(self, click_data):
        """
        Route the lead based on intent signals.

        HIGH intent   → queue for AGI-brained voice closer (AICloser.close())
        MEDIUM intent → nurture sequence (SMS/Email drip)
        LOW intent    → low-touch follow-up

        When a closer is wired, high-intent leads get the full pipeline:
        BrainDecider → Strategy (SI genome) → Voice streaming / static call.
        """
        intent = click_data.get('intent', 'medium')

        if intent == "high":
            if self.closer:
                return "ROUTE_TO_AGI_CLOSER"
            return "ROUTE_TO_VOICE_PIPELINE"  # fallback: queue for voice_streaming_agent

        if intent == "medium":
            return "ROUTE_TO_NURTURE_SEQUENCE"

        return "ROUTE_TO_LOW_TOUCH"
