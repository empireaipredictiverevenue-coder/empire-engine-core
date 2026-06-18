"""
SNIPER BRAIN · OPERATOR OVERRIDE UNIT TESTS
=============================================
Tests for the operator override endpoints on the Sniper Brain Bridge.

Endpoints tested:
  POST /api/v1/sniper/brain/override   — set an override with TTL
  GET  /api/v1/sniper/dynamic-config    — returns override when active
  DELETE /api/v1/sniper/brain/override  — clears override immediately
  GET  /api/v1/sniper/brain/health      — reports override_active flag

Key test: override expires after ttl_seconds (patched time.time).
All external dependencies (AIRouter, Supabase) are unavailable at import
time, so the app falls back to static mode automatically — no mocking needed.

Usage:
    pytest tests/test_sniper_brain_override.py -v
    python3 -m pytest tests/test_sniper_brain_override.py -v
"""

import os
import sys
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from empire_sniper_brain import app, DEFAULT_CONFIG


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_globals():
    """Reset the operator override globals before each test.

    Since POST modifies module-level _operator_override and
    _override_expires_at, we must reset them between tests to
    prevent test-order bleed.
    """
    import empire_sniper_brain as esb
    esb._operator_override = None
    esb._override_expires_at = 0.0


@pytest.fixture
def client():
    """FastAPI TestClient wired directly to the sniper brain app.

    The app auto-falls back to static mode when AIRouter and Supabase
    are not available — no additional patching needed for baseline tests.
    """
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# OVERRIDE LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════

class TestOverrideLifecycle:
    """Set → verify active → verify values → clear → verify gone."""

    BASE_CONFIG_URL = "/api/v1/sniper/dynamic-config"
    OVERRIDE_URL = "/api/v1/sniper/brain/override"

    def test_initial_state_returns_static_config(self, client):
        """Before any override, dynamic-config returns static defaults."""
        resp = client.get(self.BASE_CONFIG_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_by"] == "static"
        assert data["buy_amount_sol"] == DEFAULT_CONFIG["buy_amount_sol"]

    def test_set_override_returns_200_with_ok(self, client):
        """POST override returns 200 with ok=true and the override values."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.42, "market_mode": "aggressive", "ttl_seconds": 300},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "override" in data
        assert "ttl_seconds" in data
        assert "expires_at" in data

    def test_override_values_match_what_was_sent(self, client):
        """The override response contains exactly the keys that were POST'd."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={
                "buy_amount_sol": 0.42,
                "market_mode": "aggressive",
                "min_risk_score": 25,
                "ttl_seconds": 120,
            },
        )
        assert resp.status_code == 200
        override = resp.json()["override"]
        assert override["buy_amount_sol"] == 0.42
        assert override["market_mode"] == "aggressive"
        assert override["min_risk_score"] == 25
        assert override["generated_by"] == "operator_override"

    def test_override_ttl_reported_correctly(self, client):
        """TTL in response matches what was sent."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 180},
        )
        assert resp.json()["ttl_seconds"] == 180

    def test_override_is_active_on_next_poll(self, client):
        """After setting override, GET returns the override config (not static)."""
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.99, "market_mode": "aggressive", "ttl_seconds": 60},
        )
        resp = client.get(self.BASE_CONFIG_URL)
        data = resp.json()
        assert data["generated_by"] == "operator_override"
        assert data["buy_amount_sol"] == 0.99
        assert data["market_mode"] == "aggressive"

    def test_clear_override_returns_200(self, client):
        """DELETE override returns 200 with ok=true."""
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        resp = client.delete(self.OVERRIDE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "Override cleared" in data["message"]

    def test_override_no_longer_active_after_clear(self, client):
        """After DELETE, GET returns config WITHOUT operator_override."""
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        client.delete(self.OVERRIDE_URL)
        resp = client.get(self.BASE_CONFIG_URL)
        data = resp.json()
        assert data["generated_by"] != "operator_override"
        # Should be back to static or agi
        assert data["generated_by"] in ("static", "agi")


# ═══════════════════════════════════════════════════════════════════════════
# TTL EXPIRY — CORE TEST
# ═══════════════════════════════════════════════════════════════════════════

class TestOverrideTtlExpiry:
    """Verify override expires after ttl_seconds using patched time.time."""

    BASE_CONFIG_URL = "/api/v1/sniper/dynamic-config"
    OVERRIDE_URL = "/api/v1/sniper/brain/override"
    T0 = 1_000_000.0  # arbitrary epoch

    @patch("empire_sniper_brain.time.time")
    def test_override_active_within_ttl(self, mock_time, client):
        """Override is still active before TTL expires."""
        mock_time.return_value = self.T0
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        # Advance clock by 30s — still within 60s TTL
        mock_time.return_value = self.T0 + 30.0
        resp = client.get(self.BASE_CONFIG_URL)
        assert resp.json()["generated_by"] == "operator_override"

    @patch("empire_sniper_brain.time.time")
    def test_override_expires_exactly_at_ttl(self, mock_time, client):
        """At exactly T0 + ttl, the override should have expired (time < expires_at is false)."""
        mock_time.return_value = self.T0
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        # Advance exactly to the expiry boundary (T0 + 60)
        mock_time.return_value = self.T0 + 60.0
        resp = client.get(self.BASE_CONFIG_URL)
        # At exactly the boundary, 60.0 < 60.0 is False → expired
        assert resp.json()["generated_by"] != "operator_override"

    @patch("empire_sniper_brain.time.time")
    def test_override_expires_after_ttl(self, mock_time, client):
        """After TTL has passed, override is no longer returned."""
        mock_time.return_value = self.T0
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        # Advance well past TTL
        mock_time.return_value = self.T0 + 300.0
        resp = client.get(self.BASE_CONFIG_URL)
        data = resp.json()
        assert data["generated_by"] != "operator_override"
        # Falls back to static mode
        assert data["generated_by"] in ("static", "agi")

    @patch("empire_sniper_brain.time.time")
    def test_override_with_multiple_ttl_windows(self, mock_time, client):
        """Set override, verify active → wait past TTL → verify gone."""
        mock_time.return_value = self.T0
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 30},
        )
        # Just before expiry — still active
        mock_time.return_value = self.T0 + 29.0
        resp1 = client.get(self.BASE_CONFIG_URL)
        assert resp1.json()["generated_by"] == "operator_override"

        # Just after expiry — gone
        mock_time.return_value = self.T0 + 31.0
        resp2 = client.get(self.BASE_CONFIG_URL)
        assert resp2.json()["generated_by"] != "operator_override"

        # The expired override should NOT reappear later
        mock_time.return_value = self.T0 + 999.0
        resp3 = client.get(self.BASE_CONFIG_URL)
        assert resp3.json()["generated_by"] != "operator_override"

    @patch("empire_sniper_brain.time.time")
    def test_override_ttl_defaults_to_300(self, mock_time, client):
        """When ttl_seconds is not provided, it defaults to 300s."""
        mock_time.return_value = self.T0
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5},
        )
        assert resp.json()["ttl_seconds"] == 300
        # At T0+299, still active
        mock_time.return_value = self.T0 + 299.0
        active_resp = client.get(self.BASE_CONFIG_URL)
        assert active_resp.json()["generated_by"] == "operator_override"
        # At T0+301, expired
        mock_time.return_value = self.T0 + 301.0
        expired_resp = client.get(self.BASE_CONFIG_URL)
        assert expired_resp.json()["generated_by"] != "operator_override"


# ═══════════════════════════════════════════════════════════════════════════
# OVERRIDE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestOverrideEdgeCases:
    """Error handling, clamping, boundary conditions."""

    OVERRIDE_URL = "/api/v1/sniper/brain/override"
    BASE_CONFIG_URL = "/api/v1/sniper/dynamic-config"

    def test_empty_body_returns_400(self, client):
        """POST with no body returns 400."""
        resp = client.post(
            self.OVERRIDE_URL,
            content=b"",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_no_valid_config_keys_returns_400(self, client):
        """POST with only ttl_seconds (not a config key) returns 400."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"ttl_seconds": 60},
        )
        assert resp.status_code == 400
        assert "valid config keys" in resp.json()["detail"].lower()

    def test_ttl_clamped_to_minimum_10(self, client):
        """ttl_seconds=1 is clamped to min 10."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 1},
        )
        assert resp.json()["ttl_seconds"] == 10

    def test_ttl_clamped_to_minimum_zero(self, client):
        """ttl_seconds=0 is clamped to min 10."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 0},
        )
        assert resp.json()["ttl_seconds"] == 10

    def test_ttl_clamped_to_minimum_negative(self, client):
        """ttl_seconds=-5 is clamped to min 10."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": -5},
        )
        assert resp.json()["ttl_seconds"] == 10

    def test_ttl_clamped_to_maximum_3600(self, client):
        """ttl_seconds=5000 is clamped to max 3600 (1 hour)."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 5000},
        )
        assert resp.json()["ttl_seconds"] == 3600

    def test_ttl_accepts_maximum_3600(self, client):
        """ttl_seconds=3600 is allowed (exact max)."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 3600},
        )
        assert resp.json()["ttl_seconds"] == 3600

    def test_partial_override_does_not_reset_unsent_keys(self, client):
        """Setting only buy_amount_sol should keep other keys at sent value.

        Note: the override dict is built from scratch each POST, so
        only keys sent in the body are set. Unset keys are absent
        from the override dict (but generated_at/reasoning are still
        overwritten in the dynamic-config handler).
        """
        resp = client.post(
            self.OVERRIDE_URL,
            json={"min_risk_score": 55, "ttl_seconds": 60},
        )
        assert resp.status_code == 200
        override = resp.json()["override"]
        assert override["min_risk_score"] == 55
        # buy_amount_sol was NOT sent, so it should NOT be in the override dict.
        # The GET /dynamic-config returns the override as-is (no merge with defaults),
        # so this key will be absent from the response.
        assert "buy_amount_sol" not in override

    def test_override_replaces_previous_override(self, client):
        """Setting a new override should replace the previous one entirely."""
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.1, "market_mode": "conservative", "ttl_seconds": 60},
        )
        client.post(
            self.OVERRIDE_URL,
            json={"market_mode": "aggressive", "ttl_seconds": 120},
        )
        # Only market_mode was sent in the second POST; buy_amount_sol is NOT in override
        resp = client.get(self.BASE_CONFIG_URL)
        data = resp.json()
        assert data["generated_by"] == "operator_override"
        assert data["market_mode"] == "aggressive"
        # buy_amount_sol was replaced in the override (not present). The GET response
        # returns the override dict as-is — buy_amount_sol will be absent.

    def test_malicious_body_handled_gracefully(self, client):
        """POST with non-dict body returns 400."""
        resp = client.post(
            self.OVERRIDE_URL,
            content=b"not json at all",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code in (400, 422)  # FastAPI may return 422 for malformed JSON

    def test_float_ttl_converted_to_int(self, client):
        """ttl_seconds=30.7 should be int(30.7)=30 (then no clamping)."""
        resp = client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 30.7},
        )
        # int(30.7) = 30, no clamping needed (30 >= 10 and <= 3600)
        assert resp.json()["ttl_seconds"] == 30

    def test_delete_without_set_returns_ok(self, client):
        """DELETE /override when none is set should still return 200 ok."""
        resp = client.delete(self.OVERRIDE_URL)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH CHECK INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthOverrideFlag:
    """The health endpoint should reflect override state accurately."""

    HEALTH_URL = "/api/v1/sniper/brain/health"
    OVERRIDE_URL = "/api/v1/sniper/brain/override"

    def test_health_shows_no_override_initially(self, client):
        """Before any override, operator_override_active is false."""
        resp = client.get(self.HEALTH_URL)
        assert resp.json()["operator_override_active"] is False

    def test_health_shows_override_after_set(self, client):
        """After setting override, health reports it as active."""
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        resp = client.get(self.HEALTH_URL)
        assert resp.json()["operator_override_active"] is True

    def test_health_shows_override_gone_after_clear(self, client):
        """After clearing override, health reports inactive."""
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 60},
        )
        client.delete(self.OVERRIDE_URL)
        resp = client.get(self.HEALTH_URL)
        assert resp.json()["operator_override_active"] is False

    @patch("empire_sniper_brain.time.time")
    def test_health_shows_override_expired(self, mock_time, client):
        """After TTL expires, health reports override as inactive."""
        t0 = 10_000.0
        mock_time.return_value = t0
        client.post(
            self.OVERRIDE_URL,
            json={"buy_amount_sol": 0.5, "ttl_seconds": 30},
        )
        # Before expiry — active
        mock_time.return_value = t0 + 20.0
        active_resp = client.get(self.HEALTH_URL)
        assert active_resp.json()["operator_override_active"] is True

        # After expiry — inactive
        mock_time.return_value = t0 + 31.0
        expired_resp = client.get(self.HEALTH_URL)
        assert expired_resp.json()["operator_override_active"] is False

    def test_health_always_has_expected_fields(self, client):
        """Health response always includes status, router_available, etc."""
        resp = client.get(self.HEALTH_URL)
        data = resp.json()
        assert data["status"] == "ok"
        assert "router_available" in data
        assert "db_available" in data
        assert "timestamp" in data
        assert "operator_override_active" in data
