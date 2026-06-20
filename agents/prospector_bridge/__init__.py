"""Empire AI - Predictive Revenue - Prospector Bridge Agent."""
from .prospector_bridge import main, run

__version__ = "1.0.0"

__all__ = ["main", "run", "run_once"]


def run_once():
    """Compatibility wrapper for agent_runner."""
    return run()
