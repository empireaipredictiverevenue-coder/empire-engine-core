"""
Unit tests for empire_ai_closer.AICloser.

Verifies the four routing paths the closer can take on a lead:
  1. High-confidence GO (>= 0.7) -> agi_stream_call (live Kokoro TTS)
  2. Medium-confidence GO (>= 0.4, < 0.7) -> static_call (Vonage NCCO)
  3. Low-confidence GO (< 0.4) -> nurture (SMS/Email drip)
  4. NO_GO -> no_go (skip, log only)

Plus edge cases: compliance blocks, no phone, strategy selection,
niche inference, score-only path, stream-failure fallback, and
the ai_closer_score_only helper.

All external dependencies are mocked:
  - BrainDecider (LLM-driven GO/NO-GO)
  - VoiceRouter.place_streaming_strike / place_strike_call
  - httpx.AsyncClient (register_stream call to synthetic_brain)
  - AGI Governor (strategy_for_niche, record_strategy_outcome)
  - SMSEngine.send_sms / EmailEngine.enroll
  - empire_outbound_dialer.compliance_check / ComplianceBlock

Run with:
  pytest tests/test_ai_closer.py -v
or:
  python3 -m pytest tests/test_ai_closer.py -v
"""
import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Make project root importable
ROOT = "/root/empire-v49"
sys.path.insert(0, ROOT)

# Env vars required at import time
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "placeholder")
os.environ.setdefault("SYNTHETIC_BRAIN_API_KEY", "test-key")
os.environ.setdefault("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")
os.environ.setdefault("EMPIRE_PUBLIC_BASE_URL", "")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

from empire_ai_closer import (  # noqa: E402
    AICloser,
    ai_closer_score_only,
    AGI_STREAM_THRESHOLD,
    STATIC_CALL_THRESHOLD,
)


# ── Test helpers ────────────────────────────────────────────────────
def _sample_lead(**overrides):
    base = {
        "warehouse_name": "Acme Logistics",
        "name": "Acme Logistics",
        "phone": "+13125551234",
        "phone2": "",
        "email": "contact@acme.example.com",
        "address": "123 Main St",
        "city": "Wichita",
        "state": "KS",
        "asset_value": 2500000,
        "damage_severity": "Severe",
    }
    base.update(overrides)
    return base


def _sample_alert(**overrides):
    base = {
        "event": "Severe Thunderstorm Warning",
        "severity": "Severe",
        "urgency": "Immediate",
        "area": "Wichita, KS",
    }
    base.update(overrides)
    return base


# ── Test harness (shared mocks for routing tests) ───────────────────
class _CloserHarness:
    """Wraps AICloser with mocked external dependencies."""

    def __init__(self, **closer_overrides):
        self.agent = AICloser(
            brain_decider=MagicMock(),
            voice_router=MagicMock(),
            sms_engine=MagicMock(),
            email_engine=MagicMock(),
            get_db=MagicMock(),
            **closer_overrides,
        )
        # Default: BrainDecider.decide returns GO @ 0.9 (overridable per test)
        self.agent.brain_decider.decide = AsyncMock(return_value={
            "decision": "GO",
            "confidence": 0.9,
            "reasoning": "test: GO @ 0.9",
        })
        # Make VoiceRouter methods async
        self.agent.voice_router.place_streaming_strike = AsyncMock(
            return_value={"ok": True, "uuid": "stream-uuid-123"}
        )
        self.agent.voice_router.place_strike_call = AsyncMock(
            return_value={"ok": True, "uuid": "static-uuid-456"}
        )
        # Make SMS/Email engine methods async
        self.agent.sms_engine.send_sms = AsyncMock(
            return_value={"ok": True, "message_id": "sms-789"}
        )
        self.agent.email_engine.enroll = AsyncMock(
            return_value={"ok": True, "enrollment_id": "email-012"}
        )
        # Make the closer's DB logging a no-op (real DB not available)
        self.agent._log_decision = MagicMock()

        # Patches that need lifecycle management
        self._gov_patch = None

    def _brain_says(self, decision: str, confidence: float):
        """Mock BrainDecider to return a specific GO/NO_GO decision."""
        self.agent.brain_decider.decide.return_value = {
            "decision": decision,
            "confidence": confidence,
            "reasoning": f"test: {decision} @ {confidence}",
        }

    def _no_brain(self):
        """Simulate brain_decider unavailable (None)."""
        self.agent.brain_decider = None

    def _compliance_blocks(self, phone: str):
        """Make _run_compliance_check return a block dict for the given phone."""
        async def _blocked(p):
            if p == phone:
                return {"action": "compliance_blocked", "block_reason": "TCPA window", "lead_phone": phone}
            return None
        self.agent._run_compliance_check = _blocked

    def _compliance_passes(self):
        """Make _run_compliance_check always return None (not blocked)."""
        async def _pass(p):
            return None
        self.agent._run_compliance_check = _pass

    def _strategy_returns(self, strategy: str):
        """Make _select_strategy return a fixed strategy name."""
        async def _sel(niche, decision):
            return strategy
        self.agent._select_strategy = _sel

    def _governor_ok(self):
        """Patch the AGI Governor singleton so _ensure_governor works."""
        gov_mock = MagicMock()
        gov_mock.strategy_for_niche.return_value = "AGGRESSIVE_STRIKE"
        gov_mock.get_niche_win_rate.return_value = 0.07  # 0.05-0.10 = no shift, avoids threshold adaptation
        gov_mock.record_strategy_outcome = MagicMock()
        self._gov_patch = patch(
            "empire_ai_closer.AICloser._ensure_governor",
            new=lambda s: setattr(s, "_agi_governor", gov_mock),
        )
        self._gov_patch.start()
        return gov_mock

    def cleanup(self):
        if self._gov_patch:
            self._gov_patch.stop()
            self._gov_patch = None

    def _mock_stream_registration(self, ws_url="ws://127.0.0.1:8005/api/v1/synthetic/stream?voice_id=v-test&sig=abc"):
        """Patch httpx.AsyncClient so register_stream returns success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "voice_id": "v-test",
            "ws_url": ws_url,
            "signature": "abc",
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        return patch("httpx.AsyncClient", return_value=mock_client)

    def _mock_stream_registration_fails(self):
        """Patch httpx.AsyncClient so register_stream returns 500."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        return patch("httpx.AsyncClient", return_value=mock_client)


# ── NICHE INFERENCE TESTS (pure function, no mocks) ─────────────────
class TestNicheInference:
    """_infer_niche is a pure static method — test it directly."""

    def test_explicit_niche_in_meta(self):
        lead = {"meta": {"niche": "Custom Niche"}, "name": "Test"}
        result = AICloser._infer_niche(lead, None)
        assert result == "Custom Niche"

    def test_tornado_in_alert(self):
        result = AICloser._infer_niche({}, {"event": "Tornado Warning"})
        assert result == "Tornado Damage Repair"

    def test_hurricane_in_alert(self):
        result = AICloser._infer_niche({}, {"event": "Hurricane Watch"})
        assert result == "Hurricane Damage Restoration"

    def test_hail_in_alert(self):
        result = AICloser._infer_niche({}, {"event": "Hail storm warning"})
        assert result == "Hail Damage Repair"

    def test_flood_in_alert(self):
        result = AICloser._infer_niche({}, {"event": "Flash Flood Advisory"})
        assert result == "Flood Damage Restoration"

    def test_thunderstorm_in_alert(self):
        result = AICloser._infer_niche({}, {"event": "Severe Thunderstorm Warning"})
        assert result == "Storm Damage Restoration"

    def test_generic_storm_fallback(self):
        result = AICloser._infer_niche({}, {"event": "Winter Storm Watch"})
        assert result == "Storm Damage Restoration"

    def test_roofing_type_tag(self):
        lead = {"type_tags": {"types": ["roofing"]}}
        result = AICloser._infer_niche(lead, None)
        assert result == "Roofing Restoration"

    def test_no_clues_defaults_to_roofing(self):
        result = AICloser._infer_niche({}, None)
        assert result == "Roofing Restoration"


# ── ROUTING PATH TESTS ──────────────────────────────────────────────
class TestRoutingPaths:
    """Core regression coverage — the four routing paths in close()."""

    def test_high_confidence_go_routes_to_agi_stream(self):
        """Brain says GO @ 0.9 -> closer calls place_streaming_strike."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            with h._mock_stream_registration():
                return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "agi_stream_call"
        assert result["strategy"] == "AGGRESSIVE_STRIKE"
        assert result["niche"] == "Storm Damage Restoration"
        assert h.agent.stats["agi_stream_calls"] == 1
        assert h.agent.stats["brain_go"] == 1
        assert h.agent.stats["static_calls"] == 0
        assert h.agent.stats["nurture_routed"] == 0
        assert h.agent.voice_router.place_streaming_strike.called
        assert not h.agent.voice_router.place_strike_call.called

    def test_medium_confidence_go_routes_to_static_call(self):
        """Brain says GO @ 0.5 -> closer calls place_strike_call."""
        h = _CloserHarness()
        h._brain_says("GO", 0.5)
        h._strategy_returns("RECALL_SNIPER")
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "static_call"
        assert result["strategy"] == "RECALL_SNIPER"
        assert h.agent.stats["static_calls"] == 1
        assert h.agent.stats["brain_go"] == 1
        assert h.agent.stats["agi_stream_calls"] == 0
        assert h.agent.voice_router.place_strike_call.called
        assert not h.agent.voice_router.place_streaming_strike.called

    def test_low_confidence_go_routes_to_nurture(self):
        """Brain says GO @ 0.3 -> closer sends SMS + Email nurture."""
        h = _CloserHarness()
        h._brain_says("GO", 0.3)
        h._strategy_returns("UGLY_BANNER")
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "nurture"
        assert result["strategy"] == "UGLY_BANNER"
        assert h.agent.stats["nurture_routed"] == 1
        assert h.agent.stats["brain_go"] == 1
        assert h.agent.stats["agi_stream_calls"] == 0
        assert h.agent.stats["static_calls"] == 0
        assert h.agent.sms_engine.send_sms.called
        assert h.agent.email_engine.enroll.called

    def test_no_go_skips_all_paths(self):
        """Brain says NO_GO -> no call placed, no nurture sent."""
        h = _CloserHarness()
        h._brain_says("NO_GO", 0.1)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "no_go"
        assert result["decision"] == "NO_GO"
        assert h.agent.stats["brain_no_go"] == 1
        assert h.agent.stats["brain_go"] == 0
        assert h.agent.stats["agi_stream_calls"] == 0
        assert h.agent.stats["static_calls"] == 0
        assert h.agent.stats["nurture_routed"] == 0
        assert not h.agent.voice_router.place_streaming_strike.called
        assert not h.agent.voice_router.place_strike_call.called
        assert not h.agent.sms_engine.send_sms.called
        assert not h.agent.email_engine.enroll.called

    def test_no_brain_decider_defaults_to_go(self):
        """Without a brain_decider, the closer defaults to GO @ 0.5 confidence."""
        h = _CloserHarness()
        h._no_brain()
        h._strategy_returns("STANDARD")
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        # 0.5 >= 0.4 -> static call
        assert result["action"] == "static_call"
        assert result["confidence"] == 0.5
        assert result["decision"] == "GO"


# ── COMPLIANCE BLOCK TESTS ──────────────────────────────────────────
class TestComplianceBlocks:
    """Compliance checks blocking calls in both streaming and static paths."""

    def test_compliance_blocks_static_call(self):
        """When compliance blocks, static_call returns compliance_blocked."""
        h = _CloserHarness()
        h._brain_says("GO", 0.5)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_blocks("+13125551234")
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "compliance_blocked"
        assert h.agent.stats["static_calls"] == 0

    def test_compliance_blocks_stream_call(self):
        """When compliance blocks a streaming call, return compliance_blocked
        before hitting synthetic_brain."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_blocks("+13125551234")
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        # 0.9 confidence -> would try agi_stream, but compliance blocks immediately
        assert result["action"] == "compliance_blocked"
        assert h.agent.stats["agi_stream_calls"] == 0


# ── EDGE CASE TESTS ─────────────────────────────────────────────────
class TestEdgeCases:
    """No phone, stream failure fallback, threshold boundaries."""

    def test_no_phone_returns_no_phone(self):
        """Lead without phone -> static_call returns no_phone."""
        h = _CloserHarness()
        h._brain_says("GO", 0.5)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        gov = h._governor_ok()

        lead = _sample_lead(phone="", phone2="")
        async def run():
            return await h.agent.close(lead, _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "no_phone"

    def test_stream_failure_falls_back_to_static(self):
        """When register_stream returns 500, closer falls back to static call."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            with h._mock_stream_registration_fails():
                return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        # Stream reg failed -> fallback to static call
        assert result["action"] == "static_call"
        assert h.agent.stats["static_calls"] == 1
        assert h.agent.stats["agi_stream_calls"] == 0
        assert h.agent.voice_router.place_strike_call.called

    def test_streaming_strike_failure_falls_back_to_static(self):
        """When place_streaming_strike returns ok=False, closer falls back to
        static. Only the actual outcome is counted (static), not the attempt."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_passes()
        gov = h._governor_ok()

        # Make the streaming call fail
        h.agent.voice_router.place_streaming_strike = AsyncMock(
            return_value={"ok": False, "error": "Vonage timeout"}
        )

        async def run():
            with h._mock_stream_registration():
                return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        # Streaming call ok=False -> fallback to static
        assert result["action"] == "static_call"
        # Stream wasn't completed successfully, so agi_stream_calls stays 0
        assert h.agent.stats["agi_stream_calls"] == 0
        assert h.agent.stats["static_calls"] == 1

    def test_threshold_boundary_at_0_7_routes_to_stream(self):
        """Confidence exactly at 0.7 -> agi_stream_call."""
        h = _CloserHarness(stream_confidence=0.7)
        h._brain_says("GO", 0.7)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            with h._mock_stream_registration():
                return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "agi_stream_call"

    def test_threshold_boundary_at_0_4_routes_to_static(self):
        """Confidence exactly at 0.4 -> static_call (not nurture)."""
        h = _CloserHarness(static_confidence=0.4)
        h._brain_says("GO", 0.4)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "static_call"

    def test_threshold_just_below_0_4_routes_to_nurture(self):
        """Confidence at 0.39 -> nurture."""
        h = _CloserHarness(static_confidence=0.4)
        h._brain_says("GO", 0.39)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        gov = h._governor_ok()

        async def run():
            return await h.agent.close(_sample_lead(), _sample_alert())
        result = asyncio.run(run())
        h.cleanup()

        assert result["action"] == "nurture"


# ── SCORE-ONLY PATH TESTS ───────────────────────────────────────────
class TestScoreOnly:
    """ai_closer_score_only scores without placing any calls."""

    def test_score_only_returns_route_without_placing_call(self):
        """Score a lead -> get route recommendation, no calls."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._strategy_returns("RECALL_SNIPER")
        gov = h._governor_ok()

        async def run():
            return await ai_closer_score_only(
                h.agent, _sample_lead(), _sample_alert()
            )
        result = asyncio.run(run())
        h.cleanup()

        assert result["lead_name"] == "Acme Logistics"
        assert result["route"] == "agi_stream_call"
        assert result["niche"] == "Storm Damage Restoration"
        assert "brain_confidence" in result
        # No calls were placed
        assert not h.agent.voice_router.place_streaming_strike.called
        assert not h.agent.voice_router.place_strike_call.called

    def test_score_only_when_go_high_confidence(self):
        """Score a lead with GO @ 0.9 -> route=agi_stream_call."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        gov = h._governor_ok()

        async def run():
            return await ai_closer_score_only(
                h.agent, _sample_lead(), _sample_alert()
            )
        result = asyncio.run(run())
        h.cleanup()

        assert result["route"] == "agi_stream_call"
        assert result["brain_confidence"] == 0.9
        assert result["brain_decision"] == "GO"

    def test_score_only_when_no_go(self):
        """Score a lead with NO_GO -> route=no_go."""
        h = _CloserHarness()
        h._brain_says("NO_GO", 0.2)
        h._strategy_returns("AGGRESSIVE_STRIKE")
        gov = h._governor_ok()

        async def run():
            return await ai_closer_score_only(
                h.agent, _sample_lead(), _sample_alert()
            )
        result = asyncio.run(run())
        h.cleanup()

        assert result["route"] == "no_go"
        assert result["brain_decision"] == "NO_GO"


# ── STRATEGY SELECTION TESTS ────────────────────────────────────────
class TestStrategySelection:
    """AGI Governor strategy_for_niche is called correctly."""

    def test_strategy_selected_via_governor(self):
        """_select_strategy passes niche to governor.strategy_for_niche."""
        h = _CloserHarness()
        h._brain_says("GO", 0.9)
        h._compliance_passes()
        gov = h._governor_ok()

        async def run():
            with h._mock_stream_registration():
                return await h.agent.close(
                    _sample_lead(),
                    {"event": "Hail storm warning"}
                )
        result = asyncio.run(run())
        h.cleanup()

        # Governor should have been called for the hail niche
        assert gov.strategy_for_niche.called
        assert result["niche"] == "Hail Damage Repair"


# ── SNAPSHOT TESTS ──────────────────────────────────────────────────
class TestSnapshot:
    """Stats snapshot returns expected keys."""

    def test_snapshot_has_all_keys(self):
        c = AICloser()
        snap = c.snapshot()
        required = [
            "leads_processed", "brain_go", "brain_no_go",
            "agi_stream_calls", "static_calls", "nurture_routed",
            "errors", "stream_confidence", "static_confidence",
            "voice_router_wired", "brain_decider_wired",
            "sms_engine_wired", "email_engine_wired",
            "synthetic_brain_url", "operator_number_configured",
        ]
        for key in required:
            assert key in snap, f"Missing snapshot key: {key}"

    def test_snapshot_defaults(self):
        c = AICloser()
        snap = c.snapshot()
        assert snap["leads_processed"] == 0
        assert snap["brain_go"] == 0
        assert snap["brain_decider_wired"] is False
        assert snap["voice_router_wired"] is False

    def test_snapshot_reflects_wired_deps(self):
        c = AICloser(
            brain_decider=MagicMock(),
            voice_router=MagicMock(),
            sms_engine=MagicMock(),
            email_engine=MagicMock(),
        )
        snap = c.snapshot()
        assert snap["brain_decider_wired"] is True
        assert snap["voice_router_wired"] is True
        assert snap["sms_engine_wired"] is True
        assert snap["email_engine_wired"] is True


# ── CONSTANT TESTS ──────────────────────────────────────────────────
class TestConstants:
    """Pin the business-rule thresholds so changes show up in test diffs."""

    def test_agi_stream_threshold_is_0_7(self):
        assert AGI_STREAM_THRESHOLD == 0.7

    def test_static_call_threshold_is_0_4(self):
        assert STATIC_CALL_THRESHOLD == 0.4
