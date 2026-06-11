"""
EMPIRE V49 · ROOT conftest.py
=============================
Loaded automatically by pytest before any test collection. Sets up the
project root on sys.path so test files inside `tests/` can do plain
`import empire_mission_control` without needing PYTHONPATH or relative
imports.
"""
import os
import sys

# Project root = directory containing this conftest.py
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Prepend to sys.path so the empire_* modules are importable from tests.
# (pytest already adds the rootdir to sys.path, but we add it explicitly
# with highest priority so test_*.py files run identically whether invoked
# from the project root or from inside the tests/ directory.)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def pytest_configure(config):
    """
    Hook called once at pytest startup. Useful for environment-level setup
    that should apply to every test (e.g. silencing loggers, seeding env
    vars). Kept minimal — the test files handle their own mocking.
    """
    # Set a deterministic test-mode env var so any module that checks it
    # (e.g. `_TESTING = os.environ.get("EMPIRE_TESTING")`) can short-circuit
    # network calls.
    os.environ.setdefault("EMPIRE_TESTING", "1")

    # Silence the verbose `log` loggers in empire_mission_control et al.
    # during test runs — assertion output is what we want to see.
    import logging
    for noisy in ("empire.mission_control", "empire.hub", "empire.si.strategy"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)
