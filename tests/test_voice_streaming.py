"""
Unit tests for bots.voice_streaming_agent.

Verifies the three routing paths the agent can take on a strike:
  1. High-confidence GO (>= 0.7) -> streaming path (Kokoro TTS via WebSocket)
  2. Low-confidence GO  (<  0.7) -> static NCCO (Vonage built-in TTS)
  3. NO_GO                       -> skip (no call placed)

Plus the surrounding edge cases: no target, target w/o phone, register_stream
failure, threshold boundary, and trigger_strike operator path.

All external dependencies are mocked:
  - BrainDecider (LLM-driven GO/NO-GO)
  - VoiceRouter.place_streaming_strike (Vonage + WebSocket)
  - VoiceRouter.place_strike_call (Vonage + static NCCO)
  - _get_sb() (Supabase client) -> _next_target poll + heartbeat
  - _register_stream (HTTP POST to synthetic_brain)

Run with:
  pytest tests/test_voice_streaming.py -v
or:
  python3 -m pytest tests/test_voice_streaming.py -v
"""
import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Make project root importable
ROOT = "/root/empire-v49"
sys.path.insert(0, ROOT)

# Env vars required by the agent module at import time
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "placeholder")
os.environ.setdefault("SYNTHETIC_BRAIN_API_KEY", "test-key")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("EMPIRE_PUBLIC_BASE_URL", "")

from bots.voice_streaming_agent import (  # noqa: E402
    VoiceStreamingAgent,
    STREAM_CONFIDENCE_THRESHOLD,
    _script_for_target,
    _get_sb,
)


# ── Direct tests for the script-template selector (no mocks) ─────────
class TestScriptTemplates:
    """The script template is pure-function — test it directly."""

    def test_high_confidence_uses_predictive_cloud_template(self):
        script = _script_for_target(
            {"warehouse_name": "Acme", "city": "Wichita", "state": "KS"},
            {"decision": "GO", "confidence": 0.9},
        )
        assert "Predictive Cloud" in script
        assert "severe storm activity" in script
        assert "Wichita, KS" in script
        assert "Acme" in script

    def test_low_confidence_uses_soft_weather_template(self):
        script = _script_for_target(
            {"warehouse_name": "Acme", "city": "Wichita", "state": "KS"},
            {"decision": "GO", "confidence": 0.5},
        )
        assert "recent weather activity" in script
        assert "Predictive Cloud" not in script
        assert "Wichita, KS" in script

    def test_no_go_falls_back_to_generic_greeting(self):
        script = _script_for_target(
            {"warehouse_name": "Acme", "city": "Wichita", "state": "KS"},
            {"decision": "NO_GO", "confidence": 0.1},
        )
        assert "Thank you for calling Empire AI" in script
        assert "Predictive Cloud" not in script
        assert "severe storm activity" not in script

    def test_state_omitted_in_template_when_missing(self):
        script = _script_for_target(
            {"warehouse_name": "Acme", "city": "Wichita"},
            {"decision": "GO", "confidence": 0.9},
        )
        # Just "Wichita", not "Wichita, "
        assert "Wichita" in script
        assert "Wichita, ," not in script  # no dangling comma


# ── Test harness for the routing-logic tests (shared mocks) ─────────
class _AgentHarness:
    """
    Wraps VoiceStreamingAgent with the minimal mock injection needed to
    drive run_cycle() / trigger_strike() without touching the network or DB.

    Pattern: set the agent's lazy-loaded attributes (_brain_decider,
    _voice_router) directly to Mock objects, and patch the module-level
    _get_sb() + _register_stream() to return predictable values.
    """

    def __init__(self):
        self.agent = VoiceStreamingAgent()
        # Skip _ensure_dependencies by injecting mocks directly
        self.agent._brain_decider = MagicMock()
        self.agent._voice_router = MagicMock()
        # Make the router methods async-callable
        self.agent._voice_router.place_streaming_strike = AsyncMock(
            return_value={"ok": True, "uuid": "stream-uuid-123"}
        )
        self.agent._voice_router.place_strike_call = AsyncMock(
            return_value={"ok": True, "uuid": "static-uuid-456"}
        )

    def _supabase_with_targets(self, targets):
        """Return a patch that makes _get_sb() return a mock whose
        .table('radar_targets').select(...).execute().data == targets."""
        sb_mock = MagicMock()
        chain = (
            sb_mock.table.return_value
            .select.return_value
            .order.return_value
            .limit.return_value
            .execute.return_value
        )
        chain.data = targets
        return patch("bots.voice_streaming_agent._get_sb", return_value=sb_mock)

    def _register_stream_returns(self, payload=None):
        """Patch _register_stream on the agent instance to skip the HTTP call."""
        if payload is None:
            payload = {
                "voice_id": "v-abc",
                "signature": "s-def",
                "ws_url": "ws://127.0.0.1:8005/api/v1/synthetic/stream?voice_id=v-abc&sig=s-def",
                "voice": "am_michael",
                "script": "Test script. Second sentence.",
            }
        return patch.object(
            self.agent, "_register_stream",
            new=AsyncMock(return_value=payload),
        )

    def _register_stream_fails(self):
        return patch.object(
            self.agent, "_register_stream",
            new=AsyncMock(return_value=None),
        )

    def _brain_says(self, decision: str, confidence: float):
        """Patch the brain_decider to return a specific decision."""
        return patch.object(
            self.agent._brain_decider, "decide",
            new=AsyncMock(return_value={
                "decision": decision,
                "confidence": confidence,
                "reasoning": f"test: {decision} {confidence}",
            }),
        )

    @staticmethod
    def _target(**overrides):
        base = {
            "id": "target-1",
            "warehouse_name": "Acme Logistics",
            "address": "123 Main St",
            "city": "Wichita",
            "state": "KS",
            "phone": "+13125551234",
            "phone2": "",
            "asset_value": 2500000,
            "damage_severity": "Severe",
        }
        base.update(overrides)
        return base


# ── The three routing paths ─────────────────────────────────────────
class TestRoutingPaths:
    """The core regression coverage — agent's brain-decision routing."""

    def test_high_confidence_go_routes_to_streaming(self):
        """Brain says GO @ 0.9 -> agent calls place_streaming_strike, NOT
        place_strike_call. Stats increment streaming_strikes + brain_go."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([h._target()]), \
                 h._register_stream_returns(), \
                 h._brain_says("GO", 0.9):
                return await h.agent.run_cycle()
        result = asyncio.run(run())

        assert result["action"] == "streaming_strike"
        assert h.agent.stats["streaming_strikes"] == 1
        assert h.agent.stats["brain_go"] == 1
        assert h.agent.stats["static_strikes"] == 0
        assert h.agent.stats["brain_no_go"] == 0
        assert h.agent._voice_router.place_streaming_strike.called
        assert not h.agent._voice_router.place_strike_call.called

    def test_low_confidence_go_routes_to_static(self):
        """Brain says GO @ 0.5 (below 0.7 threshold) -> agent calls
        place_strike_call with the static NCCO, NOT streaming."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([h._target()]), \
                 h._register_stream_returns(), \
                 h._brain_says("GO", 0.5):
                return await h.agent.run_cycle()
        result = asyncio.run(run())

        assert result["action"] == "static_strike"
        assert h.agent.stats["static_strikes"] == 1
        assert h.agent.stats["brain_go"] == 1
        assert h.agent.stats["streaming_strikes"] == 0
        assert h.agent._voice_router.place_strike_call.called
        assert not h.agent._voice_router.place_streaming_strike.called
        # _register_stream is never called for the static path
        # (the patch is a no-op; we just verify the streaming router method isn't hit)

    def test_no_go_skips(self):
        """Brain says NO_GO -> agent skips both strike paths, increments
        brain_no_go. NO phone call placed."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([h._target()]), \
                 h._register_stream_returns(), \
                 h._brain_says("NO_GO", 0.1):
                return await h.agent.run_cycle()
        result = asyncio.run(run())

        assert result["action"] == "no_go"
        assert h.agent.stats["brain_no_go"] == 1
        assert h.agent.stats["brain_go"] == 0
        assert h.agent.stats["streaming_strikes"] == 0
        assert h.agent.stats["static_strikes"] == 0
        assert not h.agent._voice_router.place_streaming_strike.called
        assert not h.agent._voice_router.place_strike_call.called


# ── Edge cases ──────────────────────────────────────────────────────
class TestEdgeCases:

    def test_no_target_returns_no_target(self):
        """Supabase returns 0 targets -> action=no_target, brain never called."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([]):
                return await h.agent.run_cycle()
        result = asyncio.run(run())

        assert result["action"] == "no_target"
        assert h.agent.stats["cycles"] == 1
        assert h.agent.stats["targets_evaluated"] == 0
        assert not h.agent._brain_decider.decide.called

    def test_target_without_phone_is_filtered_by_next_target(self):
        """_next_target filters out targets with no phone/phone2 — the
        `if not phone` branch in run_cycle is defensive (dead in normal
        flow) so we test the actual filtering behavior at the poll layer."""
        h = _AgentHarness()
        # Phone-less target mixed in with a valid one
        valid = h._target(id="valid-1", phone="+13125551234")
        phoneless = h._target(id="phoneless-1", phone="", phone2="")
        with h._supabase_with_targets([phoneless, valid]):
            picked = h.agent._next_target()
        assert picked is not None
        assert picked["id"] == "valid-1", (
            f"_next_target should have skipped the phoneless target, got {picked}"
        )
        # When ALL targets are phoneless, _next_target returns None
        with h._supabase_with_targets([phoneless]):
            assert h.agent._next_target() is None

    def test_register_stream_failure_increments_errors(self):
        """synthetic_brain returns 4xx/5xx (None from _register_stream) ->
        action=register_failed, errors stat +1, no call placed."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([h._target()]), \
                 h._register_stream_fails(), \
                 h._brain_says("GO", 0.9):
                return await h.agent.run_cycle()
        result = asyncio.run(run())

        assert result["action"] == "register_failed"
        assert h.agent.stats["errors"] == 1
        assert h.agent.stats["streaming_strikes"] == 0
        assert not h.agent._voice_router.place_streaming_strike.called

    def test_threshold_boundary_at_0_7_routes_to_streaming(self):
        """Confidence exactly at 0.7 (the pinned business constant) should
        use streaming (>= threshold). Hardcoded 0.7 so this test catches
        both comparison-operator changes AND value regressions."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([h._target()]), \
                 h._register_stream_returns(), \
                 h._brain_says("GO", 0.7):
                return await h.agent.run_cycle()
        result = asyncio.run(run())
        assert result["action"] == "streaming_strike", (
            f"confidence 0.7 should hit streaming (>= threshold)"
        )

    def test_threshold_just_below_routes_to_static(self):
        """Confidence at 0.699 (just below 0.7) should use static path."""
        h = _AgentHarness()
        async def run():
            with h._supabase_with_targets([h._target()]), \
                 h._register_stream_returns(), \
                 h._brain_says("GO", 0.699):
                return await h.agent.run_cycle()
        result = asyncio.run(run())
        assert result["action"] == "static_strike"

    def test_trigger_strike_routes_to_streaming(self):
        """trigger_strike() (operator button) skips the poll + brain select
        and uses streaming directly when brain says GO."""
        h = _AgentHarness()
        async def run():
            with h._register_stream_returns(), \
                 h._brain_says("GO", 0.85):
                return await h.agent.trigger_strike(h._target())
        result = asyncio.run(run())

        assert result["action"] == "streaming_strike"
        assert h.agent._voice_router.place_streaming_strike.called
        assert not h.agent._voice_router.place_strike_call.called

    def test_trigger_strike_respects_no_go(self):
        """trigger_strike() with brain NO_GO -> action=no_go, no call placed."""
        h = _AgentHarness()
        async def run():
            with h._register_stream_returns(), \
                 h._brain_says("NO_GO", 0.2):
                return await h.agent.trigger_strike(h._target())
        result = asyncio.run(run())

        assert result["action"] == "no_go"
        assert not h.agent._voice_router.place_streaming_strike.called


# ── Module-level invariant ──────────────────────────────────────────
def test_stream_confidence_threshold_is_0_7():
    """The threshold is a business-rule constant. Pin it so accidental
    changes show up in test diffs."""
    assert STREAM_CONFIDENCE_THRESHOLD == 0.7
