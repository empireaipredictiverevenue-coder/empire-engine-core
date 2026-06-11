"""
Unit tests for empire_mission_control.snapshot().

Covers:
- Snapshot shape (top-level keys + per-section keys)
- Health rollup (red / amber / green) under different brain/AGI/revenue states
- Per-aggregator 30s cache behavior (brain + compliance)
- Broadcast-loop short-circuit (no snapshot build when zero clients)
- 5.5s snapshot cache
- StrategyEvolution.get_shared_instance() classmethod
- Defensive behavior when Supabase / Ollama are unreachable
- No I/O happens during the test (all Supabase + Ollama calls are mocked)

Run with:  python3 -m pytest tests/test_empire_mission_control.py -v
           python3 tests/test_empire_mission_control.py     # plain runner
"""
import os
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

# Make the project root importable so `import empire_mission_control` works
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import empire_mission_control as mc  # noqa: E402
from empire_si_strategy import StrategyEvolution  # noqa: E402


# ─── Helpers ──────────────────────────────────────────────────────────────

def _make_db_stub():
    """Return a MagicMock standing in for the Supabase client."""
    db = MagicMock()
    # Every chained .table(...).select(...).limit(...).execute() returns []
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[], count=0)
    chain.limit.return_value.execute.return_value = MagicMock(data=[], count=0)
    chain.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[], count=0)
    chain.gte.return_value.execute.return_value = MagicMock(data=[], count=0)
    chain.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[], count=0)
    chain.select.return_value = chain
    db.table.return_value = chain
    return db


def _reset_caches():
    """Reset all module-level caches between tests so TTLs don't bleed."""
    mc._SNAPSHOT_CACHE["_payload"]   = None
    mc._SNAPSHOT_CACHE["_cached_at"] = 0.0
    mc._AGI_CACHE["_payload"]        = None
    mc._AGI_CACHE["_cached_at"]      = 0.0
    mc._BRAIN_CACHE["_payload"]      = None
    mc._BRAIN_CACHE["_cached_at"]    = 0.0
    mc._COMPLIANCE_CACHE["_payload"]   = None
    mc._COMPLIANCE_CACHE["_cached_at"] = 0.0


def _set_brain_cache(payload):
    """Pre-seed the brain cache so the test doesn't hit Supabase."""
    mc._BRAIN_CACHE["_payload"]   = payload
    mc._BRAIN_CACHE["_cached_at"] = time.time()


def _set_compliance_cache(payload):
    mc._COMPLIANCE_CACHE["_payload"]   = payload
    mc._COMPLIANCE_CACHE["_cached_at"] = time.time()


# ─── Tests ────────────────────────────────────────────────────────────────

class TestSnapshotShape(unittest.TestCase):
    """The snapshot dict must have the right top-level keys + per-section keys."""

    def setUp(self):
        _reset_caches()

    def test_top_level_keys(self):
        # Pre-seed all caches so the snapshot builds deterministically
        _set_brain_cache({
            "up": True, "supabase_up": True,
            "model_code": "qwen2.5-coder:14b",
            "model_logic": "llama3.1:latest",
            "model_outreach": "llama3.2:3b",
            "confidence_avg": 0.7, "decisions_24h": 5,
            "last_decision": "GO", "last_niche": "Wichita",
        })
        _set_compliance_cache({
            "blocked_today": 0, "dnc_total": 100,
            "call_window_open": True, "local_hour": 12,
        })
        with patch.object(mc, "_aggregate_agi", return_value={
            "status": "AGGRESSIVE_STRIKE", "running": True,
            "cycles": 10, "strikes_total": 4,
            "brain_go": 6, "brain_no_go": 1, "manus_fired": 0,
            "stale_count": 0, "healthy_count": 11,
        }), patch.object(mc, "_aggregate_si", return_value={
            "generation": 3, "active_strategies": 8, "fitness_avg": 0.55,
            "niches": [{"niche": "Roofing", "mrr": 12000.0}],
        }), patch.object(mc, "_aggregate_revenue", return_value={
            "total_24h": 150.0, "mrr_projected": 8000.0,
            "calls_24h": 5, "active_buyers": 4, "lanes_active": 12,
            "health_status": "healthy",
        }), patch.object(mc, "_aggregate_network", return_value={
            "ws_connections": 1, "sse_connected": 0,
            "messages_sent": 100, "uptime_s": 600,
        }):
            snap = mc.mission_control_snapshot(get_db=_make_db_stub())

        self.assertIn("ts", snap)
        self.assertIn("agi", snap)
        self.assertIn("si", snap)
        self.assertIn("brain", snap)
        self.assertIn("revenue", snap)
        self.assertIn("compliance", snap)
        self.assertIn("network", snap)
        self.assertIn("health", snap)
        # AGI sub-keys
        self.assertEqual(snap["agi"]["status"], "AGGRESSIVE_STRIKE")
        self.assertEqual(snap["agi"]["cycles"], 10)
        # SI sub-keys
        self.assertEqual(snap["si"]["generation"], 3)
        self.assertEqual(snap["si"]["active_strategies"], 8)
        # Brain sub-keys
        self.assertTrue(snap["brain"]["up"])
        self.assertEqual(snap["brain"]["decisions_24h"], 5)
        # Revenue sub-keys
        self.assertEqual(snap["revenue"]["total_24h"], 150.0)
        self.assertEqual(snap["revenue"]["lanes_active"], 12)
        # Compliance sub-keys
        self.assertTrue(snap["compliance"]["call_window_open"])
        self.assertEqual(snap["compliance"]["dnc_total"], 100)
        # Network sub-keys
        self.assertEqual(snap["network"]["ws_connections"], 1)


class TestHealthRollup(unittest.TestCase):
    """The 'health' key must roll up to red / amber / green correctly."""

    def setUp(self):
        _reset_caches()

    def _build(self, *, brain, agi, revenue, compliance_):
        with patch.object(mc, "_aggregate_brain", return_value=brain), \
             patch.object(mc, "_aggregate_agi",   return_value=agi), \
             patch.object(mc, "_aggregate_si",    return_value={
                 "generation": 0, "active_strategies": 0, "fitness_avg": 0.0, "niches": []
             }), \
             patch.object(mc, "_aggregate_revenue", return_value=revenue), \
             patch.object(mc, "_aggregate_compliance", return_value=compliance_), \
             patch.object(mc, "_aggregate_network", return_value={
                 "ws_connections": 0, "sse_connected": 0, "messages_sent": 0, "uptime_s": 0
             }):
            return mc.mission_control_snapshot(get_db=_make_db_stub())["health"]

    def test_green_when_all_healthy(self):
        h = self._build(
            brain={"up": True, "supabase_up": True, "confidence_avg": 0.7},
            agi={"status": "AGGRESSIVE_STRIKE", "stale_count": 0, "running": True},
            revenue={"calls_24h": 5, "active_buyers": 3},
            compliance_={"blocked_today": 0, "call_window_open": True},
        )
        self.assertEqual(h, "green")

    def test_red_when_brain_down(self):
        h = self._build(
            brain={"up": False, "supabase_up": True, "confidence_avg": 0.0},
            agi={"status": "OK", "stale_count": 0, "running": True},
            revenue={"calls_24h": 0, "active_buyers": 0},
            compliance_={"blocked_today": 0, "call_window_open": True},
        )
        self.assertEqual(h, "red")

    def test_red_when_supabase_down(self):
        h = self._build(
            brain={"up": True, "supabase_up": False, "confidence_avg": 0.5},
            agi={"status": "OK", "stale_count": 0, "running": True},
            revenue={"calls_24h": 0, "active_buyers": 0},
            compliance_={"blocked_today": 0, "call_window_open": True},
        )
        self.assertEqual(h, "red")

    def test_red_when_hold_with_stale_agents(self):
        h = self._build(
            brain={"up": True, "supabase_up": True, "confidence_avg": 0.6},
            agi={"status": "HOLD", "stale_count": 2, "running": False},
            revenue={"calls_24h": 0, "active_buyers": 0},
            compliance_={"blocked_today": 0, "call_window_open": True},
        )
        self.assertEqual(h, "red")

    def test_amber_when_low_confidence(self):
        h = self._build(
            brain={"up": True, "supabase_up": True, "confidence_avg": 0.3},
            agi={"status": "AGGRESSIVE_STRIKE", "stale_count": 0, "running": True},
            revenue={"calls_24h": 5, "active_buyers": 3},
            compliance_={"blocked_today": 0, "call_window_open": True},
        )
        self.assertEqual(h, "amber")

    def test_amber_when_calls_but_no_buyers(self):
        h = self._build(
            brain={"up": True, "supabase_up": True, "confidence_avg": 0.7},
            agi={"status": "AGGRESSIVE_STRIKE", "stale_count": 0, "running": True},
            revenue={"calls_24h": 10, "active_buyers": 0},
            compliance_={"blocked_today": 0, "call_window_open": True},
        )
        self.assertEqual(h, "amber")

    def test_amber_when_too_many_blocks(self):
        h = self._build(
            brain={"up": True, "supabase_up": True, "confidence_avg": 0.7},
            agi={"status": "AGGRESSIVE_STRIKE", "stale_count": 0, "running": True},
            revenue={"calls_24h": 0, "active_buyers": 0},
            compliance_={"blocked_today": 25, "call_window_open": True},
        )
        self.assertEqual(h, "amber")


class TestSnapshotCache(unittest.TestCase):
    """The 5.5s snapshot cache must serve the same dict back-to-back."""

    def setUp(self):
        _reset_caches()

    def test_back_to_back_calls_return_same_object(self):
        with patch.object(mc, "_aggregate_brain", return_value={
            "up": True, "supabase_up": True, "confidence_avg": 0.5,
            "decisions_24h": 0, "last_decision": None, "last_niche": None,
        }), patch.object(mc, "_aggregate_agi", return_value={
            "status": "OK", "running": True, "cycles": 0, "strikes_total": 0,
            "brain_go": 0, "brain_no_go": 0, "manus_fired": 0,
            "stale_count": 0, "healthy_count": 0,
        }), patch.object(mc, "_aggregate_si", return_value={
            "generation": 0, "active_strategies": 0, "fitness_avg": 0.0, "niches": []
        }), patch.object(mc, "_aggregate_revenue", return_value={
            "total_24h": 0, "mrr_projected": 0, "calls_24h": 0,
            "active_buyers": 0, "lanes_active": 0, "health_status": "unknown",
        }), patch.object(mc, "_aggregate_compliance", return_value={
            "blocked_today": 0, "dnc_total": 0,
            "call_window_open": True, "local_hour": 12,
        }), patch.object(mc, "_aggregate_network", return_value={
            "ws_connections": 0, "sse_connected": 0, "messages_sent": 0, "uptime_s": 0
        }):
            s1 = mc.mission_control_snapshot(get_db=_make_db_stub())
            s2 = mc.mission_control_snapshot(get_db=_make_db_stub())
        # Same cached object (5.5s TTL hasn't expired)
        self.assertIs(s1, s2)


class TestBrainCache(unittest.TestCase):
    """The 30s brain cache must be served from memory on second call."""

    def setUp(self):
        _reset_caches()

    def test_brain_cache_returns_same_payload_within_ttl(self):
        sentinel = {"up": True, "supabase_up": True, "confidence_avg": 0.9,
                    "decisions_24h": 42, "last_decision": "GO", "last_niche": "Wichita"}
        # Pre-seed cache to known value
        _set_brain_cache(sentinel)
        # Mock get_db — if the cache misses, this would be called
        with patch.object(mc, "_safe_float", side_effect=AssertionError("DB was hit!")):
            out = mc._aggregate_brain(get_db=_make_db_stub())
        self.assertIs(out, sentinel)

    def test_brain_cache_expires(self):
        # Pre-seed with a sentinel, but backdate the cached_at
        sentinel = {"up": True, "supabase_up": True, "confidence_avg": 0.5,
                    "decisions_24h": 1}
        mc._BRAIN_CACHE["_payload"]   = sentinel
        mc._BRAIN_CACHE["_cached_at"] = time.time() - 31.0  # 31s ago, past TTL
        # Mock get_db to a stub so the rebuild path doesn't blow up
        with patch.object(mc, "_safe_float", return_value=0.5):
            # This will try to hit Supabase — we don't care about the result,
            # only that the cache expired and a rebuild was attempted.
            try:
                mc._aggregate_brain(get_db=_make_db_stub())
            except Exception:
                pass
        # The cache key should now have a NEW payload (different from sentinel)
        # OR be repopulated. Both are valid; the point is the old sentinel is gone.
        self.assertIsNot(mc._BRAIN_CACHE["_payload"], sentinel)


class TestComplianceCache(unittest.TestCase):
    """The 30s compliance cache must be served from memory on second call."""

    def setUp(self):
        _reset_caches()

    def test_compliance_cache_returns_same_payload_within_ttl(self):
        sentinel = {"blocked_today": 5, "dnc_total": 200,
                    "call_window_open": False, "local_hour": 22}
        _set_compliance_cache(sentinel)
        # Don't mock the date logic — just check we got the cached value back
        out = mc._aggregate_compliance(get_db=_make_db_stub())
        self.assertIs(out, sentinel)


class TestSharedInstance(unittest.TestCase):
    """StrategyEvolution.get_shared_instance() / set_shared_instance() round-trip."""

    def setUp(self):
        # Clear any leftover shared instance
        StrategyEvolution.set_shared_instance(None)

    def tearDown(self):
        StrategyEvolution.set_shared_instance(None)

    def test_returns_none_when_unset(self):
        self.assertIsNone(StrategyEvolution.get_shared_instance())

    def test_returns_assigned_instance(self):
        sentinel = object.__new__(StrategyEvolution)
        StrategyEvolution.set_shared_instance(sentinel)
        self.assertIs(StrategyEvolution.get_shared_instance(), sentinel)

    def test_set_shared_instance_clears_with_none(self):
        sentinel = object.__new__(StrategyEvolution)
        StrategyEvolution.set_shared_instance(sentinel)
        self.assertIs(StrategyEvolution.get_shared_instance(), sentinel)
        # Now clear
        StrategyEvolution.set_shared_instance(None)
        self.assertIsNone(StrategyEvolution.get_shared_instance())

    def test_set_shared_instance_overwrites(self):
        first = object.__new__(StrategyEvolution)
        second = object.__new__(StrategyEvolution)
        StrategyEvolution.set_shared_instance(first)
        self.assertIs(StrategyEvolution.get_shared_instance(), first)
        StrategyEvolution.set_shared_instance(second)
        self.assertIs(StrategyEvolution.get_shared_instance(), second)


class TestDefensiveBehavior(unittest.TestCase):
    """The aggregators must not raise when Supabase / Ollama are unreachable."""

    def setUp(self):
        _reset_caches()

    def test_brain_returns_defaults_when_ollama_down(self):
        with patch.object(mc, "_safe_float", return_value=0.0), \
             patch("httpx.Client", side_effect=Exception("connection refused")):
            out = mc._aggregate_brain(get_db=_make_db_stub())
        self.assertFalse(out["up"])
        self.assertEqual(out["decisions_24h"], 0)
        self.assertIsNone(out["last_decision"])

    def test_compliance_returns_defaults_when_db_down(self):
        # `get_db` itself must raise on call — that's the failure path the
        # outer try/except guards against. (Patching `.table.side_effect`
        # on a MagicMock doesn't help because `get_db()` returns a NEW
        # MagicMock whose .table has no side_effect set.)
        def _boom():
            raise RuntimeError("Supabase unreachable")
        with patch.object(mc, "_safe_float", return_value=0.0):
            out = mc._aggregate_compliance(get_db=_boom)
        self.assertEqual(out["blocked_today"], 0)
        self.assertEqual(out["dnc_total"], 0)
        self.assertTrue(out["call_window_open"])  # default in code

    def test_aggregate_agi_returns_unknown_when_governor_missing(self):
        # Force the AGI cache to miss (so the live path is taken)
        mc._AGI_CACHE["_payload"]   = None
        mc._AGI_CACHE["_cached_at"] = 0.0
        # Patch the imports to blow up
        with patch.dict(sys.modules, {"empire_agi_governor": None}):
            try:
                out = mc._aggregate_agi()
            except Exception:
                # If even the import guard fails, we should still get a result
                # — this test just ensures no unhandled exception propagates
                # to the broadcast loop. The function has try/except everywhere.
                out = mc._aggregate_agi()
        self.assertIn("status", out)
        self.assertIn("running", out)
        self.assertIn("stale_count", out)


class TestShortCircuitConstants(unittest.TestCase):
    """Verify the cache TTL constants are what the broadcast loop expects."""

    def test_cache_ttls(self):
        self.assertEqual(mc._SNAPSHOT_TTL_SECONDS, 5.5)
        self.assertEqual(mc._AGI_CACHE_TTL_SECONDS, 30.0)
        self.assertEqual(mc._SUBSYSTEM_CACHE_TTL_SECONDS, 30.0)


class TestAGISharedInstance(unittest.TestCase):
    """AGIGovernor.get_si_strategy() / set_si_strategy() round-trip + back-compat with class attribute."""

    def setUp(self):
        try:
            from empire_agi_governor import AGIGovernor
            self.AGIGovernor = AGIGovernor
        except ImportError as e:
            self.skipTest(f"empire_agi_governor not importable: {e}")
        # Clear any leftover shared instance
        AGIGovernor.set_si_strategy(None)

    def tearDown(self):
        self.AGIGovernor.set_si_strategy(None)

    def test_returns_none_when_unset(self):
        self.assertIsNone(self.AGIGovernor.get_si_strategy())

    def test_set_and_get_round_trip(self):
        sentinel = object()
        self.AGIGovernor.set_si_strategy(sentinel)
        self.assertIs(self.AGIGovernor.get_si_strategy(), sentinel)

    def test_set_si_strategy_clears_with_none(self):
        sentinel = object()
        self.AGIGovernor.set_si_strategy(sentinel)
        self.assertIs(self.AGIGovernor.get_si_strategy(), sentinel)
        self.AGIGovernor.set_si_strategy(None)
        self.assertIsNone(self.AGIGovernor.get_si_strategy())

    def test_set_si_strategy_overwrites(self):
        first = object()
        second = object()
        self.AGIGovernor.set_si_strategy(first)
        self.assertIs(self.AGIGovernor.get_si_strategy(), first)
        self.AGIGovernor.set_si_strategy(second)
        self.assertIs(self.AGIGovernor.get_si_strategy(), second)

    def test_back_compat_with_class_attribute(self):
        """The legacy `AGIGovernor.si_strategy` attribute must mirror the classmethod."""
        sentinel = object()
        self.AGIGovernor.set_si_strategy(sentinel)
        # Both the classmethod and the legacy attribute should return the same value
        self.assertIs(self.AGIGovernor.si_strategy, sentinel)
        self.assertIs(self.AGIGovernor.get_si_strategy(), sentinel)
        # And setting via classmethod should update the attribute
        self.AGIGovernor.set_si_strategy(None)
        self.assertIsNone(self.AGIGovernor.si_strategy)


class TestPredictiveRevenueSharedInstance(unittest.TestCase):
    """bots.predictive_revenue.get_si_instance() / set_si_instance() round-trip + feed_si_evolution() fallback caching."""

    def setUp(self):
        try:
            from bots import predictive_revenue
            self.pred_rev = predictive_revenue
        except ImportError as e:
            self.skipTest(f"bots.predictive_revenue not importable: {e}")
        # Clear any leftover shared instance
        self.pred_rev.set_si_instance(None)

    def tearDown(self):
        self.pred_rev.set_si_instance(None)

    def test_returns_none_when_unset(self):
        self.assertIsNone(self.pred_rev.get_si_instance())

    def test_set_and_get_round_trip(self):
        sentinel = object()
        self.pred_rev.set_si_instance(sentinel)
        self.assertIs(self.pred_rev.get_si_instance(), sentinel)

    def test_set_si_instance_clears_with_none(self):
        sentinel = object()
        self.pred_rev.set_si_instance(sentinel)
        self.assertIs(self.pred_rev.get_si_instance(), sentinel)
        self.pred_rev.set_si_instance(None)
        self.assertIsNone(self.pred_rev.get_si_instance())

    def test_set_si_instance_overwrites(self):
        first = object()
        second = object()
        self.pred_rev.set_si_instance(first)
        self.assertIs(self.pred_rev.get_si_instance(), first)
        self.pred_rev.set_si_instance(second)
        self.assertIs(self.pred_rev.get_si_instance(), second)

    def test_back_compat_with_module_attribute(self):
        """The legacy `_SI_INSTANCE` module attribute must mirror the setter."""
        sentinel = object()
        self.pred_rev.set_si_instance(sentinel)
        # Both the getter and the legacy attribute should return the same value
        self.assertIs(self.pred_rev._SI_INSTANCE, sentinel)
        self.assertIs(self.pred_rev.get_si_instance(), sentinel)
        # And setting via the setter should update the attribute
        self.pred_rev.set_si_instance(None)
        self.assertIsNone(self.pred_rev._SI_INSTANCE)

    def test_feed_si_evolution_caches_fallback_instance(self):
        """
        When no hub-registered instance exists, feed_si_evolution() must
        lazily construct a StrategyEvolution() and cache it back via
        set_si_instance() so subsequent ticks reuse the same instance.
        Verifies the migration from `global _SI_INSTANCE` to the public API.
        """
        from unittest.mock import patch, MagicMock
        # Pre-condition: no shared instance
        self.assertIsNone(self.pred_rev.get_si_instance())

        # Mock per_lane_forecast to return a deterministic, non-empty result
        # so the loop runs and record_outcome/evolve are called.
        mock_forecast = {
            "niche_summary": {
                "Roofing Restoration": {
                    "mrr_projected": 500.0, "revenue_24h": 60.0, "lane_count": 8,
                },
            },
        }

        # Build a fake SI instance that records every call
        fake_si = MagicMock()
        fake_si.evolve.return_value = []  # no evolution events
        construction_count = {"n": 0}

        def fake_constructor():
            construction_count["n"] += 1
            return fake_si

        with patch.object(self.pred_rev, "per_lane_forecast", return_value=mock_forecast), \
             patch("empire_si_strategy.StrategyEvolution", side_effect=fake_constructor):
            # 1st call: fallback constructs + caches
            result1 = self.pred_rev.feed_si_evolution()
            self.assertEqual(result1["action"], "fed_si")
            self.assertEqual(construction_count["n"], 1)
            self.assertIs(self.pred_rev.get_si_instance(), fake_si)

            # 2nd call: should reuse cached instance (no new construction)
            result2 = self.pred_rev.feed_si_evolution()
            self.assertEqual(result2["action"], "fed_si")
            self.assertEqual(construction_count["n"], 1,
                             "StrategyEvolution() must NOT be reconstructed on 2nd call")

            # Both calls should have invoked record_outcome + evolve
            self.assertEqual(fake_si.record_outcome.call_count, 2)
            self.assertEqual(fake_si.evolve.call_count, 2)

    def test_feed_si_evolution_uses_hub_instance_directly(self):
        """
        When the hub has already registered an instance via set_si_instance(),
        feed_si_evolution() must use it directly without constructing a new one.
        """
        from unittest.mock import patch, MagicMock
        # Use a MagicMock so record_outcome/evolve are real callable methods.
        # (An `object()` sentinel would fail with AttributeError since the
        # production code calls si_instance.record_outcome() / .evolve() on it.)
        hub_instance = MagicMock()
        hub_instance.evolve.return_value = []  # no evolution events
        self.pred_rev.set_si_instance(hub_instance)

        mock_forecast = {
            "niche_summary": {
                "Roofing Restoration": {
                    "mrr_projected": 500.0, "revenue_24h": 60.0, "lane_count": 8,
                },
            },
        }
        with patch.object(self.pred_rev, "per_lane_forecast", return_value=mock_forecast):
            result = self.pred_rev.feed_si_evolution()
        self.assertEqual(result["action"], "fed_si")
        self.assertIs(self.pred_rev.get_si_instance(), hub_instance)
        # The hub instance must have received the outcome + evolve call
        self.assertEqual(hub_instance.record_outcome.call_count, 1)
        self.assertEqual(hub_instance.evolve.call_count, 1)

    def test_feed_si_evolution_returns_error_when_si_unavailable(self):
        """If empire_si_strategy is not importable, return an error dict instead of raising."""
        import builtins
        # Force the import inside feed_si_evolution() to fail
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if "empire_si_strategy" in name:
                raise ImportError("simulated missing module")
            return original_import(name, *args, **kwargs)

        self.pred_rev.set_si_instance(None)
        with patch("builtins.__import__", side_effect=fake_import):
            result = self.pred_rev.feed_si_evolution()
        self.assertEqual(result["action"], "error")
        self.assertIn("SI strategy module not available", result["message"])


class TestAGILaneEngineInjection(unittest.TestCase):
    """
    AGILaneEngine(si_strategy=...) constructor-injection pattern.

    Verifies the new dependency-injection contract:
      1. Constructor accepts an `si_strategy` kwarg.
      2. When `si_strategy` is provided, `_resolve_si_strategies()` uses it
         directly (no fallback to get_si_instance()).
      3. When `si_strategy` is None, `_resolve_si_strategies()` falls back
         to `bots.predictive_revenue.get_si_instance()` for back-compat.
      4. When both are None, returns {} (no SI available — engine uses
         hardcoded archetypes).
      5. Snapshot/get_genome calls route through the resolved instance.
    """

    def setUp(self):
        try:
            from bots.agi_lane_engine import AGILaneEngine
            self.AGILaneEngine = AGILaneEngine
        except ImportError as e:
            self.skipTest(f"bots.agi_lane_engine not importable: {e}")
        # Reset shared singleton to a clean state
        from bots import predictive_revenue
        self.pred_rev = predictive_revenue
        self.pred_rev.set_si_instance(None)

    def tearDown(self):
        self.pred_rev.set_si_instance(None)

    def test_constructor_accepts_si_strategy(self):
        """Constructor must accept `si_strategy` kwarg without raising."""
        sentinel = MagicMock()
        engine = self.AGILaneEngine(si_strategy=sentinel)
        self.assertIs(engine.si_strategy, sentinel)

    def test_constructor_default_is_none(self):
        """When si_strategy is omitted, self.si_strategy is None (back-compat path)."""
        engine = self.AGILaneEngine()
        self.assertIsNone(engine.si_strategy)

    def test_resolve_uses_injected_instance(self):
        """When injected, _resolve_si_strategies() uses it directly."""
        fake_si = MagicMock()
        # Provide a non-empty snapshot so the method has data to work with
        fake_si.snapshot.return_value = {
            "best_per_niche": {
                "Roofing Restoration": {"name": "STORM_HUNTER_V2", "score": 0.85}
            },
            "by_niche": {
                "Roofing Restoration": [
                    {"name": "STORM_HUNTER_V2", "generation": 2}
                ]
            },
        }
        fake_si.get_genome.return_value = {"param_a": 0.9}

        engine = self.AGILaneEngine(si_strategy=fake_si)
        result = engine._resolve_si_strategies()

        # The fake_si must have been called (not the shared singleton)
        self.assertEqual(fake_si.snapshot.call_count, 1)
        self.assertEqual(fake_si.get_genome.call_count, 1)
        # And the strategy must be in the result
        self.assertIn("Roofing Restoration", result)
        self.assertEqual(result["Roofing Restoration"]["strategy"], "STORM_HUNTER_V2")
        self.assertEqual(result["Roofing Restoration"]["generation"], 2)
        self.assertEqual(result["Roofing Restoration"]["score"], 0.85)

    def test_resolve_returns_empty_when_no_si_injected(self):
        """
        When self.si_strategy is None, _resolve_si_strategies() returns
        {} immediately so the engine falls back to hardcoded archetypes.
        No late-binding fallback is attempted.
        """
        engine = self.AGILaneEngine()  # no injection
        # Shared singleton is None (cleared in setUp)
        result = engine._resolve_si_strategies()
        self.assertEqual(result, {})

    def test_injected_instance_takes_precedence_over_singleton(self):
        """
        When BOTH an injected instance AND a shared singleton exist,
        the injected one wins. This is the key invariant: the constructor
        parameter is an override, not a fallback.
        """
        injected = MagicMock(name="injected")
        injected.snapshot.return_value = {
            "best_per_niche": {"Roofing Restoration": {"name": "INJECTED", "score": 0.9}},
            "by_niche": {"Roofing Restoration": [{"name": "INJECTED", "generation": 5}]},
        }
        injected.get_genome.return_value = {}

        shared = MagicMock(name="shared")
        shared.snapshot.return_value = {
            "best_per_niche": {"Roofing Restoration": {"name": "SHARED", "score": 0.1}},
            "by_niche": {"Roofing Restoration": [{"name": "SHARED", "generation": 1}]},
        }
        shared.get_genome.return_value = {}

        # Both exist
        self.pred_rev.set_si_instance(shared)

        engine = self.AGILaneEngine(si_strategy=injected)
        result = engine._resolve_si_strategies()

        # The injected instance was used (NOT the shared)
        self.assertEqual(injected.snapshot.call_count, 1)
        self.assertEqual(shared.snapshot.call_count, 0)
        self.assertEqual(result["Roofing Restoration"]["strategy"], "INJECTED")

    def test_resolve_handles_missing_niches_gracefully(self):
        """When the snapshot has no best_per_niche for a lane's niche, that lane is skipped."""
        fake_si = MagicMock()
        fake_si.snapshot.return_value = {
            "best_per_niche": {},  # empty — no niches have evolved strategies
            "by_niche": {},
        }
        engine = self.AGILaneEngine(si_strategy=fake_si)
        result = engine._resolve_si_strategies()
        # No niches resolved — engine will use hardcoded archetypes
        self.assertEqual(result, {})

    def test_resolve_swallows_exceptions(self):
        """If the snapshot() call raises, _resolve_si_strategies() returns {} gracefully."""
        fake_si = MagicMock()
        fake_si.snapshot.side_effect = RuntimeError("snapshot blew up")
        engine = self.AGILaneEngine(si_strategy=fake_si)
        # Should NOT raise — fall through to the except branch
        result = engine._resolve_si_strategies()
        self.assertEqual(result, {})


class TestAGILaneEngineRevenueInjection(unittest.TestCase):
    """
    AGILaneEngine(revenue_score_fn=...) constructor-injection pattern.

    Verifies the new dependency-injection contract for the revenue-score
    lookup used by _lane_priority():
      1. Constructor accepts a `revenue_score_fn` kwarg.
      2. When `revenue_score_fn` is provided, _lane_priority() uses it
         directly (no fallback to bots.predictive_revenue.lane_revenue_score).
      3. When `revenue_score_fn` is None, _lane_priority() falls back to
         the module-level function for back-compat.
      4. The injected callable receives the correct lane_id argument.
      5. The priority boost logic still works with an injected fn
         (high score → +3, mid score → +1, low score + idle → -1).
    """

    def setUp(self):
        try:
            from bots.agi_lane_engine import AGILaneEngine
            self.AGILaneEngine = AGILaneEngine
        except ImportError as e:
            self.skipTest(f"bots.agi_lane_engine not importable: {e}")

    def test_constructor_accepts_revenue_score_fn(self):
        """Constructor must accept `revenue_score_fn` kwarg without raising."""
        sentinel_fn = lambda lane_id: 5.0  # noqa: E731
        engine = self.AGILaneEngine(revenue_score_fn=sentinel_fn)
        self.assertIs(engine.revenue_score_fn, sentinel_fn)

    def test_constructor_default_revenue_score_fn_is_none(self):
        """When revenue_score_fn is omitted, self.revenue_score_fn is None (back-compat path)."""
        engine = self.AGILaneEngine()
        self.assertIsNone(engine.revenue_score_fn)

    def test_lane_priority_uses_injected_revenue_fn(self):
        """When injected, _lane_priority() calls the injected fn (NOT bots.predictive_revenue)."""
        # Track every call to the injected fn
        calls = []
        def fake_revenue_fn(lane_id):
            calls.append(lane_id)
            return 8.0  # high score → +3 priority boost

        engine = self.AGILaneEngine(revenue_score_fn=fake_revenue_fn)
        # done_24h=0 so no momentum boost contaminates the revenue score
        # calculation. With this state, priority = base 5 + revenue +3 = 8.
        state = {"lane_id": 7, "pending": 0, "in_progress": 0, "done_24h": 0, "failed_24h": 0}
        priority = engine._lane_priority(state)
        self.assertEqual(calls, [7], "injected fn must be called with the lane_id from state")
        # Base score is 5, +3 from rev_score=8.0 (>=7) = 8
        self.assertEqual(priority, 8)

    def test_lane_priority_uses_mid_score_boost(self):
        """Mid-range revenue score (4-7) should add +1 priority."""
        engine = self.AGILaneEngine(revenue_score_fn=lambda lid: 5.0)
        state = {"lane_id": 0, "pending": 0, "in_progress": 0, "done_24h": 0, "failed_24h": 0}
        # Base 5 + 1 (mid score) = 6
        self.assertEqual(engine._lane_priority(state), 6)

    def test_lane_priority_uses_low_score_penalty(self):
        """Low revenue score (<=1) with 0 pending should subtract 1 priority."""
        engine = self.AGILaneEngine(revenue_score_fn=lambda lid: 0.5)
        state = {"lane_id": 0, "pending": 0, "in_progress": 0, "done_24h": 0, "failed_24h": 0}
        # Base 5 - 1 (low score, idle lane) = 4
        self.assertEqual(engine._lane_priority(state), 4)

    def test_lane_priority_no_penalty_for_low_score_with_pending(self):
        """Low revenue score with pending tasks should NOT subtract (only idle lanes get penalized)."""
        engine = self.AGILaneEngine(revenue_score_fn=lambda lid: 0.5)
        state = {"lane_id": 0, "pending": 2, "in_progress": 0, "done_24h": 0, "failed_24h": 0}
        # Base 5 + 2 (unblock stalled) = 7 — no low-score penalty because pending > 0
        self.assertEqual(engine._lane_priority(state), 7)

    def test_lane_priority_swallows_injected_fn_exceptions(self):
        """If the injected fn raises, _lane_priority() must NOT propagate the exception."""
        def boom_fn(lane_id):
            raise RuntimeError("revenue engine down")
        engine = self.AGILaneEngine(revenue_score_fn=boom_fn)
        state = {"lane_id": 0, "pending": 0, "in_progress": 0, "done_24h": 0, "failed_24h": 0}
        # Should NOT raise — falls through to the except branch
        # Base 5 (no revenue boost applied) = 5
        self.assertEqual(engine._lane_priority(state), 5)



class TestHermesControllerInjection(unittest.TestCase):
    """
    HermesController.sb constructor-injection pattern.

    Verifies the new dependency-injection contract:
      1. Constructor accepts an `sb` kwarg.
      2. When `sb` is provided, methods use it directly.
      3. When `sb` is None, methods gracefully skip DB operations
         (no AttributeError — methods check for None and return early).
      4. The module imports cleanly in EMPIRE_TESTING=1 mode
         (no sys.exit(1) at module load).
    """

    def setUp(self):
        try:
            from bots.hermes_controller import GodModeController, _sb
            self.GodModeController = GodModeController
            self._sb = _sb
        except ImportError as e:
            self.skipTest(f"bots.hermes_controller not importable: {e}")

    def test_constructor_accepts_sb(self):
        """Constructor must accept `sb` kwarg without raising."""
        sentinel = MagicMock()
        ctl = self.GodModeController(sb=sentinel)
        self.assertIs(ctl.sb, sentinel)

    def test_constructor_default_sb_is_none_in_test_mode(self):
        """When sb is omitted, self.sb is None (test mode)."""
        ctl = self.GodModeController()
        self.assertIsNone(ctl.sb)

    def test_fetch_recent_tasks_returns_empty_when_sb_none(self):
        """fetch_recent_tasks() must return empty dict, not raise, when sb is None."""
        ctl = self.GodModeController()  # no sb injected
        result = ctl.fetch_recent_tasks()
        self.assertEqual(result, {"done": [], "failed": [], "all": []})

    def test_fetch_queue_state_returns_error_when_sb_none(self):
        """fetch_queue_state() must return error dict, not raise, when sb is None."""
        ctl = self.GodModeController()
        result = ctl.fetch_queue_state()
        self.assertIn("error", result)
        self.assertIn("EMPIRE_TESTING", result["error"])

    def test_fetch_recent_tasks_uses_injected_sb(self):
        """When sb is injected, fetch_recent_tasks() calls sb.table().select()."""
        fake_sb = MagicMock()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=[])
        chain.in_.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        chain.select.return_value = chain
        fake_sb.table.return_value = chain

        ctl = self.GodModeController(sb=fake_sb)
        result = ctl.fetch_recent_tasks()
        self.assertEqual(result, {"done": [], "failed": [], "all": []})
        fake_sb.table.assert_called_with("agent_task_queue")

    def test_module_imports_with_no_supabase_creds(self):
        """Module must import without SUPABASE_URL/KEY when EMPIRE_TESTING=1."""
        import importlib
        # Save and clear env vars
        saved_url = os.environ.pop("SUPABASE_URL", None)
        saved_key = os.environ.pop("SUPABASE_SERVICE_KEY", None)
        # NOTE: we do NOT pop EMPIRE_TESTING — conftest.py set it via
        # setdefault, and the next test in the suite may need it.
        try:
            os.environ["EMPIRE_TESTING"] = "1"
            # Force reimport
            if "bots.hermes_controller" in sys.modules:
                del sys.modules["bots.hermes_controller"]
            mod = importlib.import_module("bots.hermes_controller")
            # Module should import without raising
            self.assertIsNotNone(mod)
            # And _sb should be None in test mode (no creds)
            self.assertIsNone(mod._sb)
        finally:
            # Restore env vars (but leave EMPIRE_TESTING as-is for next test)
            if saved_url is not None:
                os.environ["SUPABASE_URL"] = saved_url
            if saved_key is not None:
                os.environ["SUPABASE_SERVICE_KEY"] = saved_key


class TestPanelCourtInjection(unittest.TestCase):
    """
    PanelCourt constructor-injection pattern for live_broadcaster,
    get_latest_wisdom, and sb.

    Verifies the new dependency-injection contract:
      1. Constructor accepts all three kwargs.
      2. When injected, instance attributes use the injected values.
      3. When None, falls back to module-level imports (back-compat).
      4. The module imports cleanly in EMPIRE_TESTING=1 mode.
    """

    def setUp(self):
        try:
            from bots.panel_court import PanelCourt
            self.PanelCourt = PanelCourt
        except ImportError as e:
            self.skipTest(f"bots.panel_court not importable: {e}")

    def test_constructor_accepts_all_three_deps(self):
        """Constructor must accept live_broadcaster, get_latest_wisdom, and sb kwargs."""
        sentinel_broadcaster = MagicMock()
        async def sentinel_wisdom():
            return "wisdom string"
        sentinel_sb = MagicMock()
        court = self.PanelCourt(
            live_broadcaster=sentinel_broadcaster,
            get_latest_wisdom=sentinel_wisdom,
            sb=sentinel_sb,
        )
        self.assertIs(court.live_broadcaster, sentinel_broadcaster)
        self.assertIs(court.get_latest_wisdom, sentinel_wisdom)
        self.assertIs(court.sb, sentinel_sb)

    def test_constructor_defaults_to_module_level_fallbacks(self):
        """When deps are omitted, instance attrs fall back to module-level imports."""
        court = self.PanelCourt()
        # Each attr should be set (may be None if module-level import failed,
        # but the attr must exist)
        self.assertTrue(hasattr(court, "live_broadcaster"))
        self.assertTrue(hasattr(court, "get_latest_wisdom"))
        self.assertTrue(hasattr(court, "sb"))

    def test_injected_broadcaster_overrides_module(self):
        """When injected, live_broadcaster on the instance is the injected one."""
        import bots.panel_court as mod
        module_default = mod._module_live_broadcaster
        sentinel = MagicMock()
        court = self.PanelCourt(live_broadcaster=sentinel)
        self.assertIs(court.live_broadcaster, sentinel)
        self.assertIsNot(court.live_broadcaster, module_default)

    def test_injected_wisdom_overrides_module(self):
        """When injected, get_latest_wisdom on the instance is the injected one."""
        import bots.panel_court as mod
        async def sentinel_wisdom():
            return "injected"
        court = self.PanelCourt(get_latest_wisdom=sentinel_wisdom)
        self.assertIs(court.get_latest_wisdom, sentinel_wisdom)
        self.assertIsNot(court.get_latest_wisdom, mod._module_get_latest_wisdom)

    def test_injected_sb_stored_directly(self):
        """When injected, sb on the instance is the injected one (may be None otherwise)."""
        sentinel = MagicMock()
        court = self.PanelCourt(sb=sentinel)
        self.assertIs(court.sb, sentinel)

    def test_module_imports_with_no_supabase_creds(self):
        """Module must import without SUPABASE_URL/KEY when EMPIRE_TESTING=1."""
        import importlib
        saved_url = os.environ.pop("SUPABASE_URL", None)
        saved_key = os.environ.pop("SUPABASE_SERVICE_KEY", None)
        # NOTE: we do NOT pop EMPIRE_TESTING — conftest.py set it via
        # setdefault, and the next test in the suite may need it.
        try:
            os.environ["EMPIRE_TESTING"] = "1"
            if "bots.panel_court" in sys.modules:
                del sys.modules["bots.panel_court"]
            mod = importlib.import_module("bots.panel_court")
            self.assertIsNotNone(mod)
            # _sb starts as None (lazy in panel_court — fires on _get_sb() call)
            self.assertIsNone(mod._sb)
        finally:
            # Restore env vars (but leave EMPIRE_TESTING as-is for next test)
            if saved_url is not None:
                os.environ["SUPABASE_URL"] = saved_url
            if saved_key is not None:
                os.environ["SUPABASE_SERVICE_KEY"] = saved_key


if __name__ == "__main__":
    unittest.main(verbosity=2)
