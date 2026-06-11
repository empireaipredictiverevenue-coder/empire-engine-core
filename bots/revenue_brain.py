"""
EMPIRE V49 · REVENUE BRAIN (Thin wrapper)
===========================================
Entry point for main.py agent loop. Delegates to the
RevenueBrain class in bots/predictive_revenue.py.
"""
from bots.predictive_revenue import RevenueBrain


def run():
    """Entry point for main.py agent loop."""
    brain = RevenueBrain(interval_sec=3600)
    brain.run()
