"""
EMPIRE V49 · ASYNC PM2 HELPERS NON-BLOCKING TEST
==================================================
Verifies that _pm2_service_names() and _pm2_restart() from
bots/error_watcher.py use asyncio.to_thread() to run subprocess calls
in a thread pool, so concurrent invocations don't block the event loop.

The test mocks subprocess.run with a controlled delay and fires multiple
concurrent calls. If the helpers are genuinely async (via to_thread),
N concurrent calls should complete in roughly the same wall time as a
single call. If they were blocking, they'd take N × the delay.

Markers:
    - All tests are marked as `unit` (no external dependencies).
    - Run with: `pytest tests/test_pm2_async_helpers.py -v`
"""

import asyncio
import subprocess
import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

from bots.error_watcher import _pm2_restart, _pm2_service_names

# ── Test constants ─────────────────────────────────────────────────────

SLOW_CALL_DELAY = 0.3        # simulated subprocess latency (seconds)
CONCURRENT_CALLS = 5         # number of concurrent calls to fire
PARALLEL_THRESHOLD = 0.95    # assert elapsed < serial_time × this

pytestmark = pytest.mark.unit

MOCK_SERVICES_JSON = (
    '[{"name": "empire-hub"}, {"name": "empire-mesh"}, '
    '{"name": "empire-chrome"}, {"name": "empire-pulse-cron"}]'
)


def _make_slow_result(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Build a MagicMock that sleeps for SLOW_CALL_DELAY, then returns."""
    def _inner(*args, **kwargs):
        time.sleep(SLOW_CALL_DELAY)
        mr = MagicMock()
        mr.returncode = returncode
        mr.stdout = stdout
        mr.stderr = stderr
        return mr
    return _inner


# ── Infrastructure ─────────────────────────────────────────────────────

def _reset_cache():
    """Reset the module-level PM2 cache so each test starts fresh."""
    import bots.error_watcher as ew
    ew._PM2_CACHE_TIMESTAMP = 0
    ew._PM2_SERVICE_NAMES_CACHE = set()


# ── Tests ──────────────────────────────────────────────────────────────

class TestPm2ServiceNamesConcurrency(unittest.TestCase):
    """_pm2_service_names() must run subprocess in a thread, not the event loop."""

    def setUp(self):
        _reset_cache()

    # ── Core non-blocking assertion ───────────────────────────────────

    @patch("bots.error_watcher.subprocess.run")
    def test_service_names_parallel_completion_time(self, mock_run):
        """5 concurrent _pm2_service_names() calls complete faster than serial.

        Each call is mocked with a 0.3s subprocess delay. 5 serial calls
        would take ~1.5s. If async_to_thread is working, they should
        complete in roughly 0.3-0.5s (limited by the thread pool).
        """
        mock_run.side_effect = _make_slow_result(stdout=MOCK_SERVICES_JSON)

        async def fire():
            return await asyncio.gather(
                *[_pm2_service_names() for _ in range(CONCURRENT_CALLS)]
            )

        start = time.monotonic()
        results = asyncio.run(fire())
        elapsed = time.monotonic() - start

        serial_estimate = SLOW_CALL_DELAY * CONCURRENT_CALLS  # ~1.5s

        # All results must be correct
        expected = {"empire-hub", "empire-mesh", "empire-chrome", "empire-pulse-cron"}
        for r in results:
            self.assertEqual(r, expected)

        # Wall time must be far below serial time (proof of parallelism)
        self.assertLess(
            elapsed, serial_estimate * PARALLEL_THRESHOLD,
            f"{CONCURRENT_CALLS} concurrent calls took {elapsed:.3f}s. "
            f"Serial estimate: {serial_estimate:.1f}s. "
            f"Expected parallel execution via asyncio.to_thread."
        )

    # ── Cache behavior ────────────────────────────────────────────────

    @patch("bots.error_watcher.subprocess.run")
    def test_service_names_cache_hit_skips_subprocess(self, mock_run):
        """When the 60s cache is fresh, subprocess.run must not be called."""
        import bots.error_watcher as ew
        ew._PM2_CACHE_TIMESTAMP = time.time()
        ew._PM2_SERVICE_NAMES_CACHE = {"empire-hub", "empire-mesh"}

        result = asyncio.run(_pm2_service_names())

        mock_run.assert_not_called()
        self.assertEqual(result, {"empire-hub", "empire-mesh"})

    # ── Error paths ───────────────────────────────────────────────────

    @patch("bots.error_watcher.subprocess.run")
    def test_service_names_subprocess_error_returns_empty(self, mock_run):
        """On FileNotFoundError (pm2 missing), return empty set."""
        mock_run.side_effect = FileNotFoundError("pm2 not found")

        result = asyncio.run(_pm2_service_names())

        self.assertEqual(result, set())

    @patch("bots.error_watcher.subprocess.run")
    def test_service_names_json_decode_error_fallback(self, mock_run):
        """On JSON decode error, fall back to stale cache."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = asyncio.run(_pm2_service_names())

        self.assertEqual(result, set())  # no stale cache either

    @patch("bots.error_watcher.subprocess.run")
    def test_service_names_nonzero_returncode(self, mock_run):
        """On nonzero returncode, return stale cache or empty."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        result = asyncio.run(_pm2_service_names())

        self.assertEqual(result, set())


class TestPm2RestartConcurrency(unittest.TestCase):
    """_pm2_restart() must run subprocess in a thread, not the event loop."""

    def setUp(self):
        _reset_cache()

    # ── Core non-blocking assertion ───────────────────────────────────

    @patch("bots.error_watcher.subprocess.run")
    def test_restart_parallel_completion_time(self, mock_run):
        """5 concurrent _pm2_restart() calls complete faster than serial."""
        mock_run.side_effect = _make_slow_result(returncode=0)

        async def fire():
            return await asyncio.gather(
                *[_pm2_restart("empire-hub") for _ in range(CONCURRENT_CALLS)]
            )

        start = time.monotonic()
        results = asyncio.run(fire())
        elapsed = time.monotonic() - start

        serial_estimate = SLOW_CALL_DELAY * CONCURRENT_CALLS  # ~1.5s

        # All must return True (success)
        self.assertTrue(all(results), f"Expected all True, got {results}")

        # Each call must have passed the correct command
        for call_args in mock_run.call_args_list:
            args, _ = call_args
            self.assertEqual(args[0], ["pm2", "restart", "empire-hub"])

        # Wall time must prove parallelism
        self.assertLess(
            elapsed, serial_estimate * PARALLEL_THRESHOLD,
            f"{CONCURRENT_CALLS} concurrent restart calls took {elapsed:.3f}s. "
            f"Serial estimate: {serial_estimate:.1f}s."
        )

    # ── Error paths ───────────────────────────────────────────────────

    @patch("bots.error_watcher.subprocess.run")
    def test_restart_failure_returns_false(self, mock_run):
        """On nonzero returncode, _pm2_restart() returns False."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Service not found"
        mock_run.return_value = mock_result

        result = asyncio.run(_pm2_restart("nonexistent"))

        self.assertFalse(result)

    @patch("bots.error_watcher.subprocess.run")
    def test_restart_file_not_found(self, mock_run):
        """On FileNotFoundError (pm2 CLI missing), return False."""
        mock_run.side_effect = FileNotFoundError("pm2 not found")

        result = asyncio.run(_pm2_restart("any-service"))

        self.assertFalse(result)

    @patch("bots.error_watcher.subprocess.run")
    def test_restart_timeout(self, mock_run):
        """On TimeoutExpired, return False."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pm2 restart test", timeout=30, output="", stderr=""
        )

        result = asyncio.run(_pm2_restart("test"))

        self.assertFalse(result)


class TestMixedConcurrency(unittest.TestCase):
    """Simultaneous calls to different PM2 helpers must not deadlock."""

    def setUp(self):
        _reset_cache()

    @patch("bots.error_watcher.subprocess.run")
    def test_mixed_service_names_and_restart(self, mock_run):
        """Fire service_names and restart calls concurrently — no deadlock."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"name": "empire-hub"}]'
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        async def mixed():
            s1, r1, s2, r2 = await asyncio.gather(
                _pm2_service_names(),
                _pm2_restart("hub"),
                _pm2_service_names(),
                _pm2_restart("mesh"),
            )
            return s1, r1, s2, r2

        s1, r1, s2, r2 = asyncio.run(mixed())

        self.assertEqual(s1, {"empire-hub"})
        self.assertTrue(r1)
        # Second service_names call should hit cache
        self.assertEqual(s2, {"empire-hub"})
        self.assertTrue(r2)

    @patch("bots.error_watcher.subprocess.run")
    def test_concurrent_cache_miss_all_calls_subprocess(self, mock_run):
        """When cache is cold, concurrent calls all call subprocess (but in parallel).

        This validates that even with a cache miss, the calls don't block
        the event loop — they all dispatch to the thread pool.
        """
        mock_run.side_effect = _make_slow_result(stdout='[{"name": "x"}]')

        async def fire():
            return await asyncio.gather(
                *[_pm2_service_names() for _ in range(3)]
            )

        start = time.monotonic()
        results = asyncio.run(fire())
        elapsed = time.monotonic() - start

        # All must return the same correct result
        for r in results:
            self.assertEqual(r, {"x"})

        # Must complete far faster than 3 × 0.3s = 0.9s serial
        self.assertLess(elapsed, 0.7, f"3 concurrent cache-miss calls took {elapsed:.3f}s")



