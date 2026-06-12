"""
tests/test_si_configurators.py
================================
Unit tests for the SI Adaptive Engine configurators defined in hub.py.

Tests each apply_fn with valid + invalid inputs:
  - _apply_switchboard_param  (cache_ttl_seconds, min_offered_for_rate)
  - _apply_matching_param     (score_weights.*, default_top_n)
  - _apply_corridor_param     (min_interval_seconds)
  - _apply_outreach_param     (hot_threshold, score_per_click, score_per_reply)

Also tests read_fns, cache invalidation, rejection of out-of-range values,
and weight sum integrity after matching weight changes.
"""

import pytest


# ─────────────────────────────────────────────────────────────────
# FIXTURES: import and reset module-level state before each test
# ─────────────────────────────────────────────────────────────────


# Module-level cache invalidation spy — the fixture below patches
# empire_switchboard._invalidate_buyers_cache to append to this list.
_invalidation_calls: list = []


@pytest.fixture(autouse=True)
def _reset_subsystem_modules(monkeypatch):
    """Reset module-level config constants to their defaults before every test.

    The configurators in hub.py mutate module-level constants directly.
    We monkeypatch them back to defaults so each test starts clean.
    """
    _invalidation_calls.clear()

    # ── switchboard ──
    monkeypatch.setattr("empire_switchboard._BUYERS_CACHE_TTL",  60.0)
    monkeypatch.setattr("empire_switchboard._MIN_OFFERED_FOR_RATE", 5)
    # Replace _invalidate_buyers_cache with a spy that appends to the module-level list
    monkeypatch.setattr(
        "empire_switchboard._invalidate_buyers_cache",
        lambda: _invalidation_calls.append(1),
    )

    # ── matching ──
    monkeypatch.setattr("empire_matching.SCORE_WEIGHTS", {
        "metro_match":     0.40,
        "specialty_match": 0.25,
        "trust_score":     0.15,
        "payout_value":    0.10,
        "niche_specialist": 0.10,
    })
    monkeypatch.setattr("empire_matching.DEFAULT_TOP_N", 5)

    # ── corridor (orchestrator_agent) ──
    monkeypatch.setattr("orchestrator_agent.CORRIDOR_MIN_INTERVAL", 3600)

    # ── outreach ──
    monkeypatch.setattr("empire_outreach_agent.HOT_THRESHOLD",  5)
    monkeypatch.setattr("empire_outreach_agent.SCORE_PER_CLICK", 5)
    monkeypatch.setattr("empire_outreach_agent.SCORE_PER_REPLY", 10)


# ─────────────────────────────────────────────────────────────────
# Import the actual configurators AFTER monkeypatching defaults
# ─────────────────────────────────────────────────────────────────

from hub import (
    _apply_switchboard_param,
    _read_switchboard_param,
    _apply_matching_param,
    _read_matching_param,
    _apply_corridor_param,
    _read_corridor_param,
    _apply_outreach_param,
    _read_outreach_param,
    _apply_brain_param,
)


# ═════════════════════════════════════════════════════════════════
# SWITCHBOARD CONFIGURATOR
# ═════════════════════════════════════════════════════════════════


class TestSwitchboardConfigurator:
    """Test _apply_switchboard_param and _read_switchboard_param."""

    # ── cache_ttl_seconds ──

    def test_apply_cache_ttl_valid(self):
        """Applying a valid positive TTL should succeed and invalidate cache."""
        _invalidation_calls.clear()
        result = _apply_switchboard_param("cache_ttl_seconds", 120.0)
        assert result is True
        assert _read_switchboard_param("cache_ttl_seconds") == 120.0
        assert len(_invalidation_calls) == 1, "cache invalidation should fire"

    def test_apply_cache_ttl_zero(self):
        """TTL of 0 is valid (instant expiry)."""
        _invalidation_calls.clear()
        result = _apply_switchboard_param("cache_ttl_seconds", 0)
        assert result is True
        assert _read_switchboard_param("cache_ttl_seconds") == 0.0

    def test_apply_cache_ttl_negative(self):
        """Negative TTL should be rejected."""
        result = _apply_switchboard_param("cache_ttl_seconds", -5)
        assert result is False

    def test_apply_cache_ttl_non_numeric(self):
        """Non-numeric TTL should be rejected."""
        result = _apply_switchboard_param("cache_ttl_seconds", "fast")
        assert result is False

    # ── min_offered_for_rate ──

    def test_apply_min_offered_valid(self):
        """Applying a valid min_offered_for_rate should succeed."""
        result = _apply_switchboard_param("min_offered_for_rate", 10)
        assert result is True
        assert _read_switchboard_param("min_offered_for_rate") == 10

    def test_apply_min_offered_negative(self):
        """Negative min_offered_for_rate should be rejected."""
        result = _apply_switchboard_param("min_offered_for_rate", -1)
        assert result is False

    def test_apply_min_offered_non_int(self):
        """Non-integer min_offered_for_rate should be rejected."""
        result = _apply_switchboard_param("min_offered_for_rate", 3.5)
        assert result is False

    # ── unknown key ──

    def test_apply_unknown_key(self):
        """Unknown keys should return False."""
        result = _apply_switchboard_param("nonexistent_key", 42)
        assert result is False

    def test_read_unknown_key(self):
        """Reading an unknown key should return None."""
        assert _read_switchboard_param("nonexistent_key") is None


# ═════════════════════════════════════════════════════════════════
# MATCHING CONFIGURATOR
# ═════════════════════════════════════════════════════════════════


class TestMatchingConfigurator:
    """Test _apply_matching_param and _read_matching_param."""

    # ── score_weights.* ──

    def test_apply_valid_weight(self):
        """Applying a valid weight should succeed."""
        result = _apply_matching_param("score_weights.metro_match", 0.55)
        assert result is True
        assert _read_matching_param("score_weights.metro_match") == 0.55

    def test_apply_weight_negative(self):
        """Negative weight should be rejected."""
        result = _apply_matching_param("score_weights.metro_match", -0.1)
        assert result is False

    def test_apply_weight_above_one(self):
        """Weight > 1.0 should be rejected."""
        result = _apply_matching_param("score_weights.metro_match", 1.5)
        assert result is False

    def test_apply_weight_non_numeric(self):
        """Non-numeric weight should be rejected."""
        result = _apply_matching_param("score_weights.metro_match", "high")
        assert result is False

    def test_apply_unknown_weight_name(self):
        """Unknown weight name should return False."""
        result = _apply_matching_param("score_weights.nonexistent", 0.5)
        assert result is False

    def test_apply_weight_preserves_other_weights(self):
        """Changing one weight should not affect others."""
        original = _read_matching_param("score_weights.specialty_match")
        _apply_matching_param("score_weights.metro_match", 0.60)
        assert _read_matching_param("score_weights.specialty_match") == original

    # ── default_top_n ──

    def test_apply_top_n_valid(self):
        """Valid top_n should succeed."""
        result = _apply_matching_param("default_top_n", 8)
        assert result is True
        assert _read_matching_param("default_top_n") == 8

    def test_apply_top_n_zero(self):
        """top_n of 0 should be rejected (min 1)."""
        result = _apply_matching_param("default_top_n", 0)
        assert result is False

    def test_apply_top_n_negative(self):
        """Negative top_n should be rejected."""
        result = _apply_matching_param("default_top_n", -3)
        assert result is False

    def test_apply_top_n_non_int(self):
        """Non-integer top_n should be rejected."""
        result = _apply_matching_param("default_top_n", 5.5)
        assert result is False

    # ── unknown key ──

    def test_apply_unknown_key(self):
        """Unknown matching key should return False."""
        result = _apply_matching_param("unknown_param", 42)
        assert result is False

    def test_read_unknown_key(self):
        """Reading an unknown key should return None."""
        assert _read_matching_param("nonexistent_key") is None


# ═════════════════════════════════════════════════════════════════
# CORRIDOR CONFIGURATOR
# ═════════════════════════════════════════════════════════════════


class TestCorridorConfigurator:
    """Test _apply_corridor_param and _read_corridor_param."""

    def test_apply_min_interval_valid(self):
        """Valid min_interval_seconds should succeed."""
        result = _apply_corridor_param("min_interval_seconds", 7200)
        assert result is True
        assert _read_corridor_param("min_interval_seconds") == 7200

    def test_apply_min_interval_zero(self):
        """Zero interval is valid (no throttling)."""
        result = _apply_corridor_param("min_interval_seconds", 0)
        assert result is True
        assert _read_corridor_param("min_interval_seconds") == 0.0

    def test_apply_min_interval_negative(self):
        """Negative interval should be rejected."""
        result = _apply_corridor_param("min_interval_seconds", -100)
        assert result is False

    def test_apply_min_interval_non_numeric(self):
        """Non-numeric interval should be rejected."""
        result = _apply_corridor_param("min_interval_seconds", "fast")
        assert result is False

    def test_apply_unknown_key(self):
        """Unknown corridor key should return False."""
        result = _apply_corridor_param("max_interval_seconds", 999)
        assert result is False

    def test_read_unknown_key(self):
        """Reading an unknown key should return None."""
        assert _read_corridor_param("unknown_key") is None


# ═════════════════════════════════════════════════════════════════
# OUTREACH CONFIGURATOR
# ═════════════════════════════════════════════════════════════════


class TestOutreachConfigurator:
    """Test _apply_outreach_param and _read_outreach_param."""

    # ── hot_threshold ──

    def test_apply_hot_threshold_valid(self):
        """Valid hot_threshold should succeed."""
        result = _apply_outreach_param("hot_threshold", 8)
        assert result is True
        assert _read_outreach_param("hot_threshold") == 8

    def test_apply_hot_threshold_zero(self):
        """Zero hot_threshold should be clamped to 0 (valid)."""
        result = _apply_outreach_param("hot_threshold", 0)
        assert result is True
        assert _read_outreach_param("hot_threshold") == 0.0

    def test_apply_hot_threshold_negative_clamped(self):
        """Negative hot_threshold should be clamped to 0.0 by coerce fn."""
        result = _apply_outreach_param("hot_threshold", -5)
        assert result is True
        assert _read_outreach_param("hot_threshold") == 0.0

    def test_apply_hot_threshold_non_numeric(self):
        """Non-numeric hot_threshold should be rejected."""
        result = _apply_outreach_param("hot_threshold", "high")
        assert result is False

    # ── score_per_click ──

    def test_apply_score_per_click_valid(self):
        """Valid score_per_click should succeed."""
        result = _apply_outreach_param("score_per_click", 7)
        assert result is True
        assert _read_outreach_param("score_per_click") == 7

    # ── score_per_reply ──

    def test_apply_score_per_reply_valid(self):
        """Valid score_per_reply should succeed."""
        result = _apply_outreach_param("score_per_reply", 15)
        assert result is True
        assert _read_outreach_param("score_per_reply") == 15

    # ── unknown key ──

    def test_apply_unknown_key(self):
        """Unknown outreach key should return False."""
        result = _apply_outreach_param("score_per_impression", 3)
        assert result is False

    def test_read_unknown_key(self):
        """Reading an unknown key should return None."""
        assert _read_outreach_param("unknown_key") is None


# ═════════════════════════════════════════════════════════════════
# BRAIN CONFIGURATOR
# ═════════════════════════════════════════════════════════════════


class TestBrainConfigurator:
    """Test _apply_brain_param (always returns True — DB-driven)."""

    def test_apply_any_brain_param_succeeds(self):
        """Brain params are DB-driven; apply_fn always returns True."""
        result = _apply_brain_param("tuned_urgency_floor", 0.42)
        assert result is True

    def test_apply_arbitrary_brain_key(self):
        """Any brain.* key is accepted (idempotent DB write)."""
        result = _apply_brain_param("some_future_param", "value")
        assert result is True


# ═════════════════════════════════════════════════════════════════
# EDGE CASES & INTEGRATION
# ═════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Cross-subsystem edge cases and safety checks."""

    def test_matching_weights_sum_does_not_break(self):
        """After changing a weight, the sum may drift but reads still work."""
        # Change one weight
        _apply_matching_param("score_weights.metro_match", 0.90)
        # Reading another weight should not be affected
        specialty = _read_matching_param("score_weights.specialty_match")
        assert specialty == 0.25

    def test_rapid_config_changes(self):
        """Multiple rapid config changes should all succeed."""
        results = [
            _apply_switchboard_param("cache_ttl_seconds", 30),
            _apply_switchboard_param("cache_ttl_seconds", 45),
            _apply_switchboard_param("cache_ttl_seconds", 90),
        ]
        assert all(results)
        assert _read_switchboard_param("cache_ttl_seconds") == 90

    def test_switchboard_cache_invalidates_on_ttl_change(self):
        """Every cache_ttl_seconds change should trigger invalidation."""
        _invalidation_calls.clear()
        _apply_switchboard_param("cache_ttl_seconds", 15)
        _apply_switchboard_param("cache_ttl_seconds", 30)
        _apply_switchboard_param("cache_ttl_seconds", 60)
        assert len(_invalidation_calls) == 3

    def test_switchboard_min_offered_no_cache_invalidation(self):
        """Changing min_offered_for_rate should NOT invalidate cache."""
        _invalidation_calls.clear()
        _apply_switchboard_param("min_offered_for_rate", 20)
        assert len(_invalidation_calls) == 0
