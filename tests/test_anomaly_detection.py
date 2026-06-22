"""Unit tests for _detect_anomalies() — cross-system anomaly correlation rules.

Covers all 5 anomaly patterns:
  Pattern 1 — Funnel Blockage    (amber)  — brain.decisions_24h > 5
  Pattern 2 — Revenue Drop        (amber)  — revenue.total_24h == 0 & calls_24h > 0
  Pattern 3 — Stale Agents        (red >5, amber >3) — agi.stale_count > 3
  Pattern 4 — Call Window Closed  (info)   — compliance.call_window_open == False
  Pattern 5 — AGI Hold            (amber)  — agi.status in ("HOLD", "MANUAL_HOLD")

Run with:
    python3 -m pytest tests/test_anomaly_detection.py -v
"""

import os
import sys
import unittest
from typing import Any

# Make the project root importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from empire_mission_control_os import _detect_anomalies


# ─── Helper: build a clean snapshot dict ────────────────────────────────

def make_snapshot(**overrides: Any) -> dict:
    """Build a system_snapshot with clean (non-anomalous) defaults.

    Default values are carefully chosen so that NO anomaly fires:
      - decisions_24h = 3   (≤ 5   → no funnel blockage)
      - total_24h    = 500  (> 0   → no revenue drop)
      - calls_24h    = 5
      - stale_count  = 0    (≤ 3   → no stale agents)
      - call_window_open = True     → no call window closed
      - agi.status = "RUNNING"      → no AGI hold
    """
    mc = {
        "brain": {
            "up": True,
            "supabase_up": True,
            "confidence_avg": 0.7,
            "decisions_24h": 3,
            "last_decision": "GO",
            "last_niche": "Wichita",
        },
        "agi": {
            "status": "RUNNING",
            "running": True,
            "cycles": 10,
            "stale_count": 0,
            "healthy_count": 11,
        },
        "revenue": {
            "total_24h": 500.0,
            "mrr_projected": 8000.0,
            "calls_24h": 5,
            "active_buyers": 4,
            "lanes_active": 12,
            "health_status": "healthy",
        },
        "compliance": {
            "blocked_today": 0,
            "dnc_total": 100,
            "call_window_open": True,
            "local_hour": 14,
        },
        "network": {
            "ws_connections": 1,
            "sse_connected": 0,
            "messages_sent": 100,
            "uptime_s": 600,
        },
    }
    # Apply overrides at any depth (e.g. "brain.decisions_24h" = 10)
    for key, value in overrides.items():
        parts = key.split(".")
        target = mc
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value

    return {"mission_control": mc}


def anomaly_names(anomalies: list) -> set:
    """Return the set of pattern names from a list of anomalies."""
    return {a["pattern"] for a in anomalies}


def anomaly_by_pattern(anomalies: list, pattern: str) -> dict:
    """Return the first anomaly matching the given pattern."""
    for a in anomalies:
        if a["pattern"] == pattern:
            return a
    return {}


# ═════════════════════════════════════════════════════════════════════════
# PATTERN 1 — FUNNEL BLOCKAGE
# ═════════════════════════════════════════════════════════════════════════

class TestFunnelBlockage(unittest.TestCase):
    """Rule: brain.decisions_24h > 5 → anomaly (amber)"""

    def test_fires_when_decisions_exceed_5(self):
        snap = make_snapshot(**{"brain.decisions_24h": 6})
        anoms = _detect_anomalies(snap)
        self.assertIn("funnel_blockage", anomaly_names(anoms))

    def test_shape_and_severity(self):
        snap = make_snapshot(**{"brain.decisions_24h": 10})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "funnel_blockage")
        self.assertEqual(a["severity"], "amber")
        self.assertEqual(a["subsystem"], "brain")
        self.assertEqual(a["metrics"]["decisions_24h"], 10)
        self.assertIn("10", a["message"])

    def test_does_not_fire_at_exactly_5(self):
        snap = make_snapshot(**{"brain.decisions_24h": 5})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("funnel_blockage", anomaly_names(anoms))

    def test_does_not_fire_below_5(self):
        snap = make_snapshot(**{"brain.decisions_24h": 3})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("funnel_blockage", anomaly_names(anoms))

    def test_no_false_positive_when_missing(self):
        snap = make_snapshot()
        del snap["mission_control"]["brain"]["decisions_24h"]
        anoms = _detect_anomalies(snap)
        self.assertNotIn("funnel_blockage", anomaly_names(anoms))

    def test_no_false_positive_when_zero(self):
        snap = make_snapshot(**{"brain.decisions_24h": 0})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("funnel_blockage", anomaly_names(anoms))


# ═════════════════════════════════════════════════════════════════════════
# PATTERN 2 — REVENUE DROP
# ═════════════════════════════════════════════════════════════════════════

class TestRevenueDrop(unittest.TestCase):
    """Rule: revenue.total_24h == 0 AND revenue.calls_24h > 0 → anomaly (amber)"""

    def test_fires_when_zero_revenue_with_calls(self):
        snap = make_snapshot(**{"revenue.total_24h": 0, "revenue.calls_24h": 3})
        anoms = _detect_anomalies(snap)
        self.assertIn("revenue_drop", anomaly_names(anoms))

    def test_shape_and_severity(self):
        snap = make_snapshot(**{"revenue.total_24h": 0, "revenue.calls_24h": 5})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "revenue_drop")
        self.assertEqual(a["severity"], "amber")
        self.assertEqual(a["subsystem"], "revenue")
        self.assertEqual(a["metrics"]["total_24h"], 0)
        self.assertEqual(a["metrics"]["calls_24h"], 5)
        self.assertIn("$0", a["message"])

    def test_does_not_fire_when_revenue_is_positive(self):
        snap = make_snapshot(**{"revenue.total_24h": 100, "revenue.calls_24h": 3})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("revenue_drop", anomaly_names(anoms))

    def test_does_not_fire_when_no_calls(self):
        snap = make_snapshot(**{"revenue.total_24h": 0, "revenue.calls_24h": 0})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("revenue_drop", anomaly_names(anoms))

    def test_does_not_fire_when_both_missing(self):
        snap = make_snapshot()
        snap["mission_control"]["revenue"] = {}
        anoms = _detect_anomalies(snap)
        # total_24h defaults to 0, calls_24h defaults to 0 → no fire
        self.assertNotIn("revenue_drop", anomaly_names(anoms))

    def test_does_not_fire_when_calls_negative(self):
        snap = make_snapshot(**{"revenue.total_24h": 0, "revenue.calls_24h": -1})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("revenue_drop", anomaly_names(anoms))


# ═════════════════════════════════════════════════════════════════════════
# PATTERN 3 — STALE AGENTS
# ═════════════════════════════════════════════════════════════════════════

class TestStaleAgents(unittest.TestCase):
    """Rule: agi.stale_count > 3 → anomaly (amber 4-5, red >5)"""

    def test_fires_at_4(self):
        snap = make_snapshot(**{"agi.stale_count": 4})
        anoms = _detect_anomalies(snap)
        self.assertIn("stale_agents", anomaly_names(anoms))

    def test_amber_severity_for_4(self):
        snap = make_snapshot(**{"agi.stale_count": 4})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "stale_agents")
        self.assertEqual(a["severity"], "amber")
        self.assertEqual(a["metrics"]["stale_count"], 4)

    def test_amber_severity_for_5(self):
        snap = make_snapshot(**{"agi.stale_count": 5})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "stale_agents")
        self.assertEqual(a["severity"], "amber")
        self.assertEqual(a["metrics"]["stale_count"], 5)

    def test_red_severity_for_6(self):
        snap = make_snapshot(**{"agi.stale_count": 6})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "stale_agents")
        self.assertEqual(a["severity"], "red")
        self.assertEqual(a["metrics"]["stale_count"], 6)

    def test_red_severity_for_high_values(self):
        snap = make_snapshot(**{"agi.stale_count": 50})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "stale_agents")
        self.assertEqual(a["severity"], "red")

    def test_does_not_fire_at_3(self):
        snap = make_snapshot(**{"agi.stale_count": 3})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("stale_agents", anomaly_names(anoms))

    def test_does_not_fire_at_0(self):
        snap = make_snapshot(**{"agi.stale_count": 0})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("stale_agents", anomaly_names(anoms))

    def test_no_false_positive_when_missing(self):
        snap = make_snapshot()
        del snap["mission_control"]["agi"]["stale_count"]
        anoms = _detect_anomalies(snap)
        self.assertNotIn("stale_agents", anomaly_names(anoms))

    def test_subsystem_and_shape(self):
        snap = make_snapshot(**{"agi.stale_count": 4, "agi.healthy_count": 8})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "stale_agents")
        self.assertEqual(a["subsystem"], "agi")
        self.assertEqual(a["metrics"]["healthy_count"], 8)
        self.assertIn("4 stale", a["message"])


# ═════════════════════════════════════════════════════════════════════════
# PATTERN 4 — CALL WINDOW CLOSED
# ═════════════════════════════════════════════════════════════════════════

class TestCallWindowClosed(unittest.TestCase):
    """Rule: compliance.call_window_open == False → anomaly (info)"""

    def test_fires_when_closed(self):
        snap = make_snapshot(**{"compliance.call_window_open": False})
        anoms = _detect_anomalies(snap)
        self.assertIn("call_window_closed", anomaly_names(anoms))

    def test_shape_and_severity(self):
        snap = make_snapshot(**{"compliance.call_window_open": False, "compliance.local_hour": 22})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "call_window_closed")
        self.assertEqual(a["severity"], "info")
        self.assertEqual(a["subsystem"], "compliance")
        self.assertEqual(a["metrics"]["local_hour"], 22)
        self.assertIn("22", a["message"])

    def test_does_not_fire_when_open(self):
        snap = make_snapshot(**{"compliance.call_window_open": True})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("call_window_closed", anomaly_names(anoms))

    def test_defaults_to_open_when_missing(self):
        snap = make_snapshot()
        del snap["mission_control"]["compliance"]["call_window_open"]
        anoms = _detect_anomalies(snap)
        self.assertNotIn("call_window_closed", anomaly_names(anoms))


# ═════════════════════════════════════════════════════════════════════════
# PATTERN 5 — AGI HOLD
# ═════════════════════════════════════════════════════════════════════════

class TestAgiHold(unittest.TestCase):
    """Rule: agi.status in ("HOLD", "MANUAL_HOLD") → anomaly (amber)"""

    def test_fires_for_HOLD(self):
        snap = make_snapshot(**{"agi.status": "HOLD"})
        anoms = _detect_anomalies(snap)
        self.assertIn("agi_hold", anomaly_names(anoms))

    def test_fires_for_MANUAL_HOLD(self):
        snap = make_snapshot(**{"agi.status": "MANUAL_HOLD"})
        anoms = _detect_anomalies(snap)
        self.assertIn("agi_hold", anomaly_names(anoms))

    def test_shape_and_severity(self):
        snap = make_snapshot(**{"agi.status": "HOLD"})
        anoms = _detect_anomalies(snap)
        a = anomaly_by_pattern(anoms, "agi_hold")
        self.assertEqual(a["severity"], "amber")
        self.assertEqual(a["subsystem"], "agi")
        self.assertEqual(a["metrics"]["status"], "HOLD")
        self.assertIn("HOLD", a["message"])

    def test_does_not_fire_for_RUNNING(self):
        snap = make_snapshot(**{"agi.status": "RUNNING"})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("agi_hold", anomaly_names(anoms))

    def test_does_not_fire_for_UNKNOWN(self):
        snap = make_snapshot(**{"agi.status": "UNKNOWN"})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("agi_hold", anomaly_names(anoms))

    def test_does_not_fire_for_AGGRESSIVE_STRIKE(self):
        snap = make_snapshot(**{"agi.status": "AGGRESSIVE_STRIKE"})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("agi_hold", anomaly_names(anoms))

    def test_does_not_fire_for_empty_string(self):
        snap = make_snapshot(**{"agi.status": ""})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("agi_hold", anomaly_names(anoms))

    def test_defaults_to_UNKNOWN_when_missing(self):
        snap = make_snapshot()
        del snap["mission_control"]["agi"]["status"]
        anoms = _detect_anomalies(snap)
        self.assertNotIn("agi_hold", anomaly_names(anoms))


# ═════════════════════════════════════════════════════════════════════════
# COMBINATION TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestMultipleAnomalies(unittest.TestCase):
    """Multiple patterns can fire simultaneously."""

    def test_funnel_blockage_and_stale_agents_together(self):
        snap = make_snapshot(
            **{"brain.decisions_24h": 10, "agi.stale_count": 6}
        )
        anoms = _detect_anomalies(snap)
        names = anomaly_names(anoms)
        self.assertIn("funnel_blockage", names)
        self.assertIn("stale_agents", names)

    def test_all_five_patterns(self):
        """Trigger all 5 anomalies at once."""
        snap = make_snapshot(
            **{
                "brain.decisions_24h": 10,
                "revenue.total_24h": 0,
                "revenue.calls_24h": 2,
                "agi.stale_count": 4,
                "agi.status": "HOLD",
                "compliance.call_window_open": False,
            }
        )
        anoms = _detect_anomalies(snap)
        names = anomaly_names(anoms)
        self.assertIn("funnel_blockage", names)
        self.assertIn("revenue_drop", names)
        self.assertIn("stale_agents", names)
        self.assertIn("call_window_closed", names)
        self.assertIn("agi_hold", names)
        self.assertEqual(len(anoms), 5)

    def test_clean_snapshot_fires_none(self):
        snap = make_snapshot()
        anoms = _detect_anomalies(snap)
        self.assertEqual(anoms, [])

    def test_anomalies_are_independent(self):
        """One anomaly should not prevent another from firing."""
        snap = make_snapshot(
            **{
                "brain.decisions_24h": 6,
                "revenue.total_24h": 0,
                "revenue.calls_24h": 1,
            }
        )
        anoms = _detect_anomalies(snap)
        names = anomaly_names(anoms)
        self.assertIn("funnel_blockage", names)
        self.assertIn("revenue_drop", names)


# ═════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═════════════════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Empty/missing data should not crash the detector."""

    def test_empty_system_snapshot(self):
        anoms = _detect_anomalies({})
        self.assertEqual(anoms, [])

    def test_empty_mission_control(self):
        anoms = _detect_anomalies({"mission_control": {}})
        self.assertEqual(anoms, [])

    def test_missing_mission_control_key(self):
        """When top-level 'mission_control' key is absent."""
        anoms = _detect_anomalies({"other": "data"})
        self.assertEqual(anoms, [])

    def test_partial_brain_data(self):
        """Only brain data present, everything else missing."""
        snap = {"mission_control": {"brain": {"decisions_24h": 0}}}
        anoms = _detect_anomalies(snap)
        self.assertEqual(anoms, [])

    def test_partial_agi_data(self):
        """Only agi data present."""
        snap = {"mission_control": {"agi": {"stale_count": 0, "status": "RUNNING"}}}
        anoms = _detect_anomalies(snap)
        self.assertEqual(anoms, [])

    def test_extra_unknown_keys_ignored(self):
        """Extra keys in subsystem dicts are silently ignored."""
        snap = make_snapshot(**{"brain.unknown_field": "test"})
        anoms = _detect_anomalies(snap)
        self.assertEqual(anoms, [])

    def test_non_dict_mission_control(self):
        """When mission_control is unexpectedly not a dict."""
        anoms = _detect_anomalies({"mission_control": "corrupted"})
        # .get() won't crash; sub-dict defaults all return 0/True/UNKNOWN
        self.assertEqual(anoms, [])

    def test_negative_stale_count(self):
        """Negative stale_count should not trigger stale_agents anomaly."""
        snap = make_snapshot(**{"agi.stale_count": -1})
        anoms = _detect_anomalies(snap)
        self.assertNotIn("stale_agents", anomaly_names(anoms))


# ═════════════════════════════════════════════════════════════════════════
# RESPONSE STRUCTURE TESTS
# ═════════════════════════════════════════════════════════════════════════

class TestAnomalyResponseShape(unittest.TestCase):
    """Every anomaly must have the required fields."""

    REQUIRED_KEYS = {"pattern", "severity", "message", "subsystem", "metrics"}

    def _trigger_all(self) -> list:
        snap = make_snapshot(
            **{
                "brain.decisions_24h": 10,
                "revenue.total_24h": 0,
                "revenue.calls_24h": 2,
                "agi.stale_count": 6,
                "agi.status": "HOLD",
                "compliance.call_window_open": False,
                "compliance.local_hour": 23,
            }
        )
        return _detect_anomalies(snap)

    def test_every_anomaly_has_required_keys(self):
        anoms = self._trigger_all()
        self.assertEqual(len(anoms), 5)
        for a in anoms:
            with self.subTest(pattern=a["pattern"]):
                missing = self.REQUIRED_KEYS - set(a.keys())
                self.assertFalse(missing, f"Missing keys in {a['pattern']}: {missing}")

    def test_pattern_is_string(self):
        for a in self._trigger_all():
            self.assertIsInstance(a["pattern"], str)
            self.assertGreater(len(a["pattern"]), 0)

    def test_severity_is_valid(self):
        valid_severities = {"info", "amber", "red"}
        for a in self._trigger_all():
            self.assertIn(a["severity"], valid_severities,
                          f"Invalid severity '{a['severity']}' for {a['pattern']}")

    def test_subsystem_is_string(self):
        for a in self._trigger_all():
            self.assertIsInstance(a["subsystem"], str)

    def test_message_is_non_empty_string(self):
        for a in self._trigger_all():
            self.assertIsInstance(a["message"], str)
            self.assertGreater(len(a["message"]), 5)

    def test_metrics_is_dict(self):
        for a in self._trigger_all():
            self.assertIsInstance(a["metrics"], dict)
            self.assertGreater(len(a["metrics"]), 0)

    def test_no_unknown_keys_in_anomaly(self):
        allowed_keys = self.REQUIRED_KEYS
        for a in self._trigger_all():
            extra = set(a.keys()) - allowed_keys
            self.assertFalse(extra, f"Extra keys in {a['pattern']}: {extra}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
