from .scanner import run, main

__all__ = ["run", "main", "run_once"]


def run_once():
    """Compatibility wrapper for agent_runner."""
    return run()
