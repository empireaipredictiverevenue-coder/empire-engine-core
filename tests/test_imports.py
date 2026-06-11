"""
EMPIRE V49 · IMPORT-SAFETY TESTS
=================================
Verifies that the empire modules with real external-service dependencies
(Supabase, Ollama, httpx) can be imported with EMPIRE_TESTING=1 set,
without external credentials. Catches future regressions where someone
adds a network call at module level (like empire_agi_governor.py used
to have with `governor.direct_strategy()` at import time).

Pattern:
  - conftest.py sets `os.environ.setdefault("EMPIRE_TESTING", "1")` in
    `pytest_configure()`, so this test runs in test mode by default.
  - If any module under MODULES_TO_TEST fails to import, the test fails
    with the actual exception so the developer can fix it (likely by
    wrapping the network call in an `os.environ.get("EMPIRE_TESTING")
    == "1"` guard).

Run with:  python3 -m pytest tests/test_imports.py -v
"""
import importlib
import os
import sys
import unittest

# Ensure EMPIRE_TESTING=1 even when running this file directly
# (conftest.py handles it for `pytest tests/`, but not for plain python3)
os.environ.setdefault("EMPIRE_TESTING", "1")

# Make project root importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ─── Modules with actual external-service dependencies ─────────────────
# Focused list — only modules that reference Supabase, Ollama, or httpx
# at import time. Adding more modules would create false-positive
# "regressions" when those modules legitimately grow I/O dependencies
# later. If a module here fails to import, the fix is almost always:
#
#   if os.environ.get("EMPIRE_TESTING") == "1":
#       return  # or set module-level singleton to a test stub
#
# See empire_agi_governor.py for the canonical example.
MODULES_TO_TEST = [
    # ── Always-on (core) ──
    ("empire_agi_governor", "AGI governor (canonical EMPIRE_TESTING guard example)"),
    ("empire_si_strategy",  "SI strategy evolution (no import-time I/O, but core dep)"),
    ("empire_dream",        "Dream loop — Supabase brain_memory writes"),

    # ── Bots with Supabase at module level ──
    ("bots.predictive_revenue",   "Revenue engine — supabase + ollama"),
    ("bots.agi_lane_engine",      "32-lane engine — supabase at module level, but fully unit-testable in isolation via constructor injection of si_strategy + revenue_score_fn"),
    ("bots.panel_court",          "10-agent ensemble — supabase lazy, unit-testable via constructor injection of live_broadcaster + get_latest_wisdom + sb"),
    ("bots.hermes_controller",    "Task queue GodMode — EMPIRE_TESTING guard + sb injection"),
    ("bots.seo_agent",            "SEO agent — supabase + httpx/Ollama"),
    ("bots.storm_predictor",      "Storm predictor — supabase"),
    ("bots.prospector",           "Prospector — supabase"),
    ("bots.decision_makers",      "Decision routers — supabase"),
    ("bots.buyer_outreach",       "Buyer outreach — supabase"),
    ("bots.angi_scraper",         "Angi scraper — supabase"),
    ("bots.seed_mass_tort_buyer", "Mass tort buyer seeder — supabase"),
    ("bots.check_ledger",         "Billing ledger check — supabase"),

    # ── Loops with httpx/asyncio at module level ──
    ("empire_hourly_digest", "Hourly digest loop — asyncio.create_task at import"),
]


class TestImports(unittest.TestCase):
    """
    Every module listed in MODULES_TO_TEST must be importable when
    EMPIRE_TESTING=1 is set, without external Supabase/Ollama creds.
    """

    def test_all_modules_importable(self):
        """Import every module in MODULES_TO_TEST. Failures show the actual exception."""
        failures = []
        for mod_name, reason in MODULES_TO_TEST:
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                failures.append((mod_name, reason, type(e).__name__, str(e)[:200]))
        if failures:
            msg = "\n".join(
                f"  - {name} ({reason}): {etype}: {details}"
                for name, reason, etype, details in failures
            )
            self.fail(
                f"{len(failures)}/{len(MODULES_TO_TEST)} modules failed to import "
                f"with EMPIRE_TESTING=1:\n{msg}\n\n"
                f"Fix: wrap the module-level network call in an "
                f"`os.environ.get('EMPIRE_TESTING') == '1'` guard, "
                f"like empire_agi_governor.py does."
            )

    def test_empire_testing_env_is_set(self):
        """Sanity check: EMPIRE_TESTING=1 must be set (via conftest or directly)."""
        self.assertEqual(
            os.environ.get("EMPIRE_TESTING"), "1",
            "EMPIRE_TESTING must be '1' for these import tests to be meaningful "
            "(conftest.py sets it via setdefault)."
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
